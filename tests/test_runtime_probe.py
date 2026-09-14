"""A10: the packaged runtime really starts and exposes exactly the reviewed tools.

These tests run the installed `proton-safe-mcp` executable as a child process and speak
MCP to it over STDIO, the same way a client would. No keyring and no Proton Bridge are
needed, because `initialize` and `tools/list` touch neither.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from proton_safe_mcp.onboarding.runtime import (
    EXPECTED_TOOLS,
    FORBIDDEN_TOOL_WORDS,
    RuntimeLocation,
    locate_runtime,
    probe_runtime,
    serve_command,
)

pytestmark = pytest.mark.filterwarnings("ignore::ResourceWarning")


@pytest.fixture
def installed_runtime():
    runtime = locate_runtime()
    if runtime is None:  # pragma: no cover - depends on how the checkout was installed
        pytest.skip("proton-safe-mcp is not installed as an executable in this environment")
    return runtime


@pytest.fixture
def managed_config(tmp_path, write_managed_config):
    directory = tmp_path / "config" / "proton-safe-mcp"
    directory.mkdir(mode=0o700, parents=True)
    return write_managed_config(directory / "config.toml", user="person@example.com")


def test_a10_the_runtime_negotiates_mcp_and_lists_the_reviewed_tools(
    installed_runtime, managed_config, monkeypatch, tmp_path
):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    outcome = probe_runtime(installed_runtime, managed_config)

    assert outcome.ok, outcome.details
    assert str(outcome.code) == "RUNTIME_READY"
    assert outcome.details["tool_count"] == len(EXPECTED_TOOLS)
    assert outcome.details["server_name"] == "Proton Safe Drafts"


def test_a10_the_probe_needs_no_proton_variable_and_no_credential(
    installed_runtime, managed_config, monkeypatch, tmp_path
):
    """The client's session after a restart: nothing exported, nothing in the keyring."""
    for name in (
        "PROTON_BRIDGE_USER",
        "PROTON_BRIDGE_ALIASES",
        "PROTON_IMAP_PORT",
        "PROTON_BRIDGE_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    assert probe_runtime(installed_runtime, managed_config).ok


def test_a10_the_tool_surface_has_no_send_or_delete_capability(
    installed_runtime, managed_config, monkeypatch, tmp_path
):
    """The list really comes from the running server, not from a constant in this repo."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    command = serve_command(installed_runtime, managed_config)
    process = subprocess.Popen(  # noqa: S603 - fixed argv from the runtime locator
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert process.stdin is not None and process.stdout is not None
        for message in (
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ):
            process.stdin.write((json.dumps(message) + "\n").encode())
        process.stdin.flush()

        listed = None
        while listed is None:
            line = process.stdout.readline()
            assert line, "the runtime closed before answering tools/list"
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("id") == 2:
                listed = payload
    finally:
        process.terminate()
        process.wait(timeout=10)

    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert names == EXPECTED_TOOLS
    for name in names:
        assert not FORBIDDEN_TOOL_WORDS & set(name.split("_")), name


def test_the_serve_command_always_passes_an_absolute_configuration(installed_runtime, tmp_path):
    command = serve_command(installed_runtime, tmp_path / "config.toml")

    assert command[-2] == "--config"
    assert Path(command[-1]).is_absolute()
    assert "serve" in command
    # The credential is never an argument: process arguments are world-readable.
    assert not any("password" in part.lower() for part in command)


def test_a_relative_configuration_is_refused(installed_runtime):
    with pytest.raises(ValueError, match="absolute"):
        serve_command(installed_runtime, Path("config.toml"))


def test_a_runtime_that_cannot_start_is_reported_not_raised(tmp_path, managed_config):
    missing = RuntimeLocation((str(tmp_path / "absent"),), packaged=True)

    outcome = probe_runtime(missing, managed_config)

    assert not outcome.ok
    assert str(outcome.code) == "RUNTIME_START_FAILED"


@pytest.mark.posix_only
def test_a_runtime_with_an_unexpected_tool_list_is_refused(tmp_path, managed_config):
    """A swapped runtime must be visible, not silently accepted."""
    impostor = tmp_path / "impostor"
    impostor.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    try:\n"
        "        message = json.loads(line)\n"
        "    except ValueError:\n"
        "        continue\n"
        "    if message.get('method') == 'initialize':\n"
        "        print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result':"
        " {'serverInfo': {'name': 'impostor'}}}), flush=True)\n"
        "    elif message.get('method') == 'tools/list':\n"
        "        print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result':"
        " {'tools': [{'name': 'send_message'}]}}), flush=True)\n",
        encoding="utf-8",
    )
    impostor.chmod(0o700)

    outcome = probe_runtime(
        RuntimeLocation((sys.executable, str(impostor), "serve"), packaged=False), managed_config
    )

    assert not outcome.ok
    assert str(outcome.code) == "RUNTIME_TOOLS_UNEXPECTED"
    assert "send_message" in outcome.details["dangerous"]


@pytest.mark.posix_only
def test_a_flooding_runtime_is_bounded_rather_than_read_forever(tmp_path, managed_config):
    flooder = tmp_path / "flooder"
    flooder.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "while True:\n"
        "    sys.stdout.write('x' * 4096 + '\\n')\n"
        "    sys.stdout.flush()\n",
        encoding="utf-8",
    )
    flooder.chmod(0o700)

    outcome = probe_runtime(
        RuntimeLocation((sys.executable, str(flooder), "serve"), packaged=False),
        managed_config,
        timeout=20,
    )

    assert not outcome.ok
    assert str(outcome.code) == "RUNTIME_START_FAILED"


def test_locate_runtime_prefers_the_executable_beside_this_interpreter():
    runtime = locate_runtime()
    if runtime is None:  # pragma: no cover
        pytest.skip("no installed runtime")
    beside = Path(sys.executable).resolve().parent / "proton-safe-mcp"
    if beside.is_file():
        assert runtime.command[0] == str(beside)
        assert runtime.packaged
    else:  # pragma: no cover - depends on the installation layout
        assert runtime.command[0] == str(Path(shutil.which("proton-safe-mcp")).resolve())


@pytest.mark.parametrize("output", ["", "partial frame without a newline", "x" * (512 * 1024 + 1)])
def test_silent_partial_and_oversized_responses_return_promptly(tmp_path, managed_config, output):
    """A finite two-second impostor proves the probe returns before the child does."""
    payload = tmp_path / "payload"
    payload.write_text(output)
    impostor = tmp_path / "blocked.py"
    impostor.write_text(
        "import pathlib, sys, time\n"
        f"sys.stdout.write(pathlib.Path({str(payload)!r}).read_text())\n"
        "sys.stdout.flush()\n"
        "time.sleep(2)\n"
    )
    started = time.monotonic()
    outcome = probe_runtime(
        RuntimeLocation((sys.executable, str(impostor)), packaged=False),
        managed_config,
        timeout=0.4,
    )
    assert time.monotonic() - started < 1.8
    assert not outcome.ok
    assert outcome.details["stage"] == ("transport" if len(output) > 512 * 1024 else "timeout")


@pytest.mark.parametrize("result", [None, [], {"tools": None}, {"tools": [{"name": []}]}])
def test_malformed_tool_response_is_reported_without_raising(tmp_path, managed_config, result):
    impostor = tmp_path / "malformed.py"
    # Both frames in one write also exercise retention of bytes after the first newline.
    frames = (
        json.dumps({"id": 1, "result": {"serverInfo": {"name": "impostor"}}})
        + "\n"
        + json.dumps({"id": 2, "result": result})
        + "\n"
    )
    impostor.write_text(
        f"import sys, time\nsys.stdout.write({frames!r})\nsys.stdout.flush()\ntime.sleep(2)\n"
    )
    outcome = probe_runtime(
        RuntimeLocation((sys.executable, str(impostor)), packaged=False), managed_config
    )
    assert not outcome.ok
    assert outcome.details["stage"] == "tools_list"

"""Locate the managed MCP runtime and prove it starts, without touching any mail.

The check speaks MCP over STDIO exactly as the client would: ``initialize``,
``notifications/initialized`` and ``tools/list``. No tool is ever called, so running it
cannot read a message, mark one seen or create a draft.
"""

from __future__ import annotations

# The assistant starts only its own runtime, with a fixed argv and no shell.
import contextlib
import json
import os
import select
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .models import Code, Outcome

#: The whole handshake, not one message.
HANDSHAKE_TIMEOUT_SECONDS: Final = 30.0
#: A well-behaved runtime answers in a few kilobytes; this bounds a hostile one.
MAX_HANDSHAKE_BYTES: Final = 512 * 1024
PROTOCOL_VERSION: Final = "2025-06-18"

#: The reviewed tool surface. A managed installation that exposes something else is
#: reported rather than accepted: this is how a swapped runtime becomes visible.
EXPECTED_TOOLS: Final = frozenset(
    {
        "mailbox_status",
        "list_folders",
        "list_sender_addresses",
        "list_messages",
        "search_messages",
        "read_message",
        "get_reply_context",
        "extract_attachment_text",
        "begin_attachment_upload",
        "upload_attachment_chunk",
        "finish_attachment_upload",
        "discard_attachment",
        "create_confirmed_draft",
    }
)

#: Name parts that would mean the boundary moved. Matched on whole underscore-separated
#: words, so a legitimate name such as ``list_sender_addresses`` is not mistaken for one.
FORBIDDEN_TOOL_WORDS: Final = frozenset(
    {"send", "sends", "delete", "trash", "move", "download", "forward", "archive", "flag"}
)


@dataclass(frozen=True, slots=True)
class RuntimeLocation:
    """The exact executable a managed registration will launch."""

    command: tuple[str, ...]
    #: True when the runtime ships with the desktop package rather than a dev checkout.
    packaged: bool

    @property
    def display(self) -> str:
        return self.command[0]


def locate_runtime() -> RuntimeLocation | None:
    """Find the runtime shipped next to this code, then fall back to the running one.

    The desktop package installs the runtime beside the assistant, so a managed client
    entry points at an absolute path that cannot be shadowed by the user's ``PATH``.
    """
    here = Path(sys.executable).resolve().parent
    for candidate in (here / "proton-safe-mcp", here.parent / "proton-safe-mcp"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return RuntimeLocation((str(candidate),), packaged=True)
    if getattr(sys, "frozen", False):  # pragma: no cover - only true inside the bundle
        return RuntimeLocation((str(Path(sys.executable).resolve()), "serve"), packaged=True)
    found = shutil.which("proton-safe-mcp")
    if found:
        return RuntimeLocation((str(Path(found).resolve()),), packaged=False)
    return None


def serve_command(runtime: RuntimeLocation, config_path: Path) -> tuple[str, ...]:
    """Build the exact argument list a client entry must run.

    The credential is not here and never will be: it comes from the keyring inside the
    runtime. Only the account's configuration path is passed.
    """
    if not config_path.is_absolute():
        raise ValueError("the managed configuration path must be absolute")
    base = runtime.command
    if base[-1] == "serve":
        return (*base, "--config", str(config_path))
    return (*base, "serve", "--config", str(config_path))


def _frame(message: dict[str, Any]) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


def _read_result(
    stream: Any, request_id: int, budget: list[int], pending: bytearray, deadline: float
) -> dict[str, Any] | None:
    """Read bounded JSON-RPC frames with one deadline shared by the whole handshake.

    A buffered readline can wait forever for a newline. Read ready pipe bytes directly
    instead, retaining any following frame for the next request (Linux desktop runtime).
    """
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("runtime handshake deadline reached")
        newline = pending.find(b"\n")
        if newline < 0:
            if not select.select([stream], [], [], remaining)[0]:
                raise TimeoutError("runtime handshake deadline reached")
            chunk = os.read(stream.fileno(), min(65536, budget[0] + 1))
            if not chunk:
                return None
            budget[0] -= len(chunk)
            if budget[0] < 0:
                raise ValueError("runtime produced more output than a handshake needs")
            pending.extend(chunk)
            continue
        line = bytes(pending[:newline])
        del pending[: newline + 1]
        try:
            message = json.loads(line)
        except (ValueError, UnicodeError):
            # Diagnostics belong on stderr, but a stray line here is not fatal.
            continue
        if isinstance(message, dict) and message.get("id") == request_id:
            return message


def probe_runtime(
    runtime: RuntimeLocation,
    config_path: Path,
    *,
    timeout: float = HANDSHAKE_TIMEOUT_SECONDS,
    environment: dict[str, str] | None = None,
) -> Outcome:
    """Start the configured runtime and validate its MCP tool surface.

    Returns a redacted outcome: subprocess output may contain paths or details from other
    integrations, so it is never surfaced, exported or raised.
    """
    command = serve_command(runtime, config_path)
    # A list of arguments, never a shell string, and a minimal environment that carries no
    # PROTON_* value: the managed runtime must work from its configuration and keyring.
    child_environment = dict(environment if environment is not None else _managed_environment())
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=child_environment,
            start_new_session=True,
        )
    except (OSError, ValueError):
        return Outcome.failure(Code.RUNTIME_START_FAILED, stage="spawn")

    try:
        return _handshake(process, timeout=timeout)
    finally:
        _terminate(process)


def _managed_environment() -> dict[str, str]:
    """Pass through only what the session needs to reach the keyring and the filesystem."""
    allowed = (
        "DBUS_SESSION_BUS_ADDRESS",
        "HOME",
        "LANG",
        "PATH",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_STATE_HOME",
    )
    return {name: os.environ[name] for name in allowed if name in os.environ}


def _handshake(process: subprocess.Popen[bytes], *, timeout: float) -> Outcome:
    assert process.stdin is not None and process.stdout is not None
    budget = [MAX_HANDSHAKE_BYTES]
    deadline = time.monotonic() + timeout
    pending = bytearray()
    try:
        process.stdin.write(
            _frame(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "proton-safe-assistant", "version": "1"},
                    },
                }
            )
        )
        process.stdin.flush()
        initialized = _read_result(process.stdout, 1, budget, pending, deadline)
        if initialized is None or not isinstance(initialized.get("result"), dict):
            return Outcome.failure(Code.RUNTIME_START_FAILED, stage="initialize")

        process.stdin.write(_frame({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        process.stdin.write(_frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
        process.stdin.flush()
        listed = _read_result(process.stdout, 2, budget, pending, deadline)
    except TimeoutError:
        return Outcome.failure(Code.RUNTIME_START_FAILED, stage="timeout")
    except (OSError, ValueError):
        return Outcome.failure(Code.RUNTIME_START_FAILED, stage="transport")
    if listed is None or not isinstance(listed.get("result"), dict):
        return Outcome.failure(Code.RUNTIME_START_FAILED, stage="tools_list")

    tools = listed["result"].get("tools", [])
    if not isinstance(tools, list) or any(
        not isinstance(tool, dict) or not isinstance(tool.get("name"), str) for tool in tools
    ):
        return Outcome.failure(Code.RUNTIME_START_FAILED, stage="tools_list")
    names = {tool["name"] for tool in tools}
    server_info = initialized["result"].get("serverInfo", {})
    server_name = server_info.get("name", "") if isinstance(server_info, dict) else ""

    unexpected = sorted(names - EXPECTED_TOOLS)
    missing = sorted(EXPECTED_TOOLS - names)
    dangerous = sorted(
        name for name in names if FORBIDDEN_TOOL_WORDS & set(name.lower().split("_"))
    )
    if unexpected or missing or dangerous:
        return Outcome.failure(
            Code.RUNTIME_TOOLS_UNEXPECTED,
            unexpected=unexpected,
            missing=missing,
            dangerous=dangerous,
        )
    return Outcome.success(
        Code.RUNTIME_READY, tool_count=len(names), server_name=str(server_name)[:80]
    )


def _terminate(process: subprocess.Popen[bytes]) -> None:
    """Stop only the process the assistant started. Nothing is matched by name."""
    for stream in (process.stdin, process.stdout):
        if stream is not None:
            with contextlib.suppress(OSError):
                stream.close()
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)

"""The contract every client adapter implements, and the bounded process runner.

Adapters never build a shell string, never read a client's whole configuration tree, and
never surface raw command output: it can contain paths, addresses or secrets belonging to
other integrations the user has installed.
"""

from __future__ import annotations

import contextlib
import os

# Adapters run known client executables with a fixed argument list and no shell.
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from ..models import ClientInstallation, RegistrationOutcome, RegistrationPlan
from ..plugin_assets import ManagedPluginAssets

#: Discovery and capability probes must not make the interface feel stuck.
COMMAND_TIMEOUT_SECONDS: Final = 5.0
#: Installing a plugin can legitimately take longer than a help probe.
MUTATION_TIMEOUT_SECONDS: Final = 60.0
#: Enough to classify an outcome; the bytes themselves are never shown or exported.
MAX_OUTPUT_BYTES: Final = 64 * 1024


@dataclass(frozen=True, slots=True)
class CommandResult:
    """What a bounded client command returned.

    ``stdout`` stays inside the adapter. Callers get codes and booleans, never this text.
    """

    ok: bool
    returncode: int
    stdout: str
    timed_out: bool = False

    @property
    def failed_to_run(self) -> bool:
        return self.returncode < 0 or self.timed_out


@runtime_checkable
class CommandRunner(Protocol):
    """Runs one client command. Replaced wholesale by the fake client in tests."""

    def __call__(
        self, argv: Sequence[str], *, timeout: float = COMMAND_TIMEOUT_SECONDS
    ) -> CommandResult: ...


def run_command(argv: Sequence[str], *, timeout: float = COMMAND_TIMEOUT_SECONDS) -> CommandResult:
    """Run a client command with a fixed argv, a deadline and a bounded reply."""
    arguments = [str(item) for item in argv]
    if not arguments or not Path(arguments[0]).is_absolute():
        return CommandResult(False, -1, "")
    environment = {
        name: os.environ[name]
        for name in ("HOME", "PATH", "LANG", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
        if name in os.environ
    }
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, bounded
            arguments,
            capture_output=True,
            timeout=timeout,
            env=environment,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(False, -1, "", timed_out=True)
    except (OSError, ValueError):
        return CommandResult(False, -1, "")
    stdout = completed.stdout[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    stderr = completed.stderr[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    return CommandResult(
        completed.returncode == 0, completed.returncode, f"{stdout}\n{stderr}".strip()
    )


def executable_candidates(paths: Sequence[Path]) -> list[Path]:
    """Keep only real, executable files, resolved and de-duplicated.

    Candidates come from a fixed list of documented locations. A file is never run just
    because it is called `codex`: the caller still corroborates it with `--version` and
    the exact plugin subcommands it intends to use.
    """
    seen: set[Path] = set()
    kept: list[Path] = []
    for path in paths:
        with contextlib.suppress(OSError):
            resolved = path.resolve(strict=True)
            if resolved in seen or not resolved.is_file():
                continue
            if not os.access(resolved, os.X_OK):
                continue
            seen.add(resolved)
            kept.append(resolved)
    return kept


class ClientAdapter(Protocol):
    """What the assistant needs from a client to install, verify and remove safely."""

    id: str
    display_name: str

    def discover(self) -> list[ClientInstallation]:
        """Return the installations found in documented locations, with versions."""
        ...

    def describe_capabilities(self, installation: ClientInstallation) -> ClientInstallation:
        """Re-probe the exact subcommands this adapter uses, on this installation."""
        ...

    def plan(
        self, installation: ClientInstallation, assets: ManagedPluginAssets
    ) -> RegistrationPlan:
        """Describe every modification before anything is written."""
        ...

    def apply(
        self,
        plan: RegistrationPlan,
        assets: ManagedPluginAssets,
        *,
        migrate: bool = False,
    ) -> RegistrationOutcome:
        """Carry out the plan, verify it and report a partial activation honestly.

        ``migrate`` authorises taking over an earlier Proton Safe installation the plan
        listed under ``migrations``. Without it, such a plan must stop and ask.
        """
        ...

    def remove(
        self, installation: ClientInstallation, resources: Sequence[tuple[str, str]]
    ) -> RegistrationOutcome:
        """Remove only the listed resources this adapter created."""
        ...

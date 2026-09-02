"""Privacy-safe installation diagnostics for Proton Safe MCP."""

from __future__ import annotations

import os
import platform
import stat
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Literal

import keyring.errors

from .config import Settings
from .errors import ProtonMCPError
from .mail import ProtonBridgeClient
from .secrets import get_bridge_password

Status = Literal["PASS", "WARN", "FAIL", "SKIP"]


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One diagnostic result that is safe to print or paste into an issue."""

    name: str
    status: Status
    detail: str


def _package_version() -> str:
    try:
        return version("proton-safe-mcp")
    except PackageNotFoundError:
        return "development checkout"


def run_checks() -> list[CheckResult]:
    """Run non-destructive checks without returning credentials or mailbox data."""

    results: list[CheckResult] = []
    python_ok = sys.version_info >= (3, 11)
    python_detail = "supported" if python_ok else "3.11 or newer required"
    results.append(
        CheckResult(
            "Python",
            "PASS" if python_ok else "FAIL",
            f"{platform.python_version()} ({python_detail})",
        )
    )
    results.append(CheckResult("Package", "PASS", _package_version()))

    operating_system = platform.system() or "unknown"
    linux_supported = operating_system == "Linux"
    platform_detail = "supported" if linux_supported else "Linux required"
    results.append(
        CheckResult(
            "Platform",
            "PASS" if linux_supported else "FAIL",
            f"{operating_system} ({platform_detail})",
        )
    )
    if not linux_supported:
        return results

    settings: Settings | None = None
    try:
        settings = Settings.from_env(create_directories=False)
    except OSError as exc:
        results.append(
            CheckResult(
                "Configuration",
                "FAIL",
                f"could not read local configuration ({type(exc).__name__})",
            )
        )
    except ProtonMCPError as exc:
        results.append(CheckResult("Configuration", "FAIL", str(exc)))
    else:
        results.append(
            CheckResult(
                "Configuration",
                "PASS",
                "Bridge account and loopback IMAP port are configured",
            )
        )
        alias_count = len(settings.sender_addresses) - 1
        results.append(
            CheckResult(
                "Sender addresses",
                "PASS",
                (
                    f"primary address plus {alias_count} alias(es) from PROTON_BRIDGE_ALIASES"
                    if alias_count
                    else "primary address only; set PROTON_BRIDGE_ALIASES to draft as an alias"
                ),
            )
        )
        try:
            state_metadata = settings.state_dir.stat()
        except FileNotFoundError:
            results.append(
                CheckResult(
                    "State directory",
                    "WARN",
                    "not created yet; first use will create it with private permissions",
                )
            )
        except OSError as exc:
            results.append(
                CheckResult(
                    "State directory",
                    "FAIL",
                    f"could not inspect permissions ({type(exc).__name__})",
                )
            )
        else:
            mode = stat.S_IMODE(state_metadata.st_mode)
            private = (
                stat.S_ISDIR(state_metadata.st_mode) and mode & 0o700 == 0o700 and mode & 0o077 == 0
            )
            results.append(
                CheckResult(
                    "State directory",
                    "PASS" if private else "FAIL",
                    (
                        "private permissions"
                        if private
                        else ("must grant rwx to the owner and be inaccessible to group and others")
                    ),
                )
            )

    credential_available = False
    if settings is None:
        results.append(CheckResult("Credential", "SKIP", "configuration must pass first"))
    else:
        try:
            get_bridge_password(settings.bridge_user)
        except keyring.errors.KeyringError as exc:
            results.append(
                CheckResult(
                    "Credential",
                    "FAIL",
                    f"OS keyring lookup failed ({type(exc).__name__})",
                )
            )
        except ProtonMCPError as exc:
            results.append(CheckResult("Credential", "FAIL", str(exc)))
        else:
            credential_available = True
            environment_fallback = bool(os.environ.get("PROTON_BRIDGE_PASSWORD"))
            results.append(
                CheckResult(
                    "Credential",
                    "WARN" if environment_fallback else "PASS",
                    (
                        "PROTON_BRIDGE_PASSWORD is set; unset it to use the OS keyring "
                        "(run `proton-safe-mcp setup`)"
                        if environment_fallback
                        else "available from the OS keyring"
                    ),
                )
            )

    if settings is None or not credential_available:
        results.append(
            CheckResult("Bridge", "SKIP", "configuration and credential must pass first")
        )
    else:
        try:
            status = ProtonBridgeClient(settings).status()
            connected = status.get("connected") is True
        except ProtonMCPError as exc:
            results.append(CheckResult("Bridge", "FAIL", str(exc)))
        else:
            results.append(
                CheckResult(
                    "Bridge",
                    "PASS" if connected else "FAIL",
                    "authenticated IMAP connection succeeded" if connected else "not connected",
                )
            )

    return results


def print_report(results: list[CheckResult]) -> int:
    """Print results and return a process exit code suitable for scripts."""

    print("Proton Safe MCP doctor")
    print("No credentials, email addresses, or mailbox contents are shown.")
    print()
    for result in results:
        print(f"[{result.status}] {result.name}: {result.detail}")

    failures = sum(result.status == "FAIL" for result in results)
    warnings = sum(result.status == "WARN" for result in results)
    print()
    if failures:
        print(f"Doctor found {failures} blocking problem(s).")
        return 1
    if warnings:
        print(f"All required checks passed with {warnings} warning(s).")
    else:
        print("All checks passed.")
    return 0


def run() -> int:
    """Run and print the diagnostic report."""

    return print_report(run_checks())

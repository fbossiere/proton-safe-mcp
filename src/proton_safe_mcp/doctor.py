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


def _python_check() -> CheckResult:
    supported = sys.version_info >= (3, 11)
    detail = "supported" if supported else "3.11 or newer required"
    return CheckResult(
        "Python", "PASS" if supported else "FAIL", f"{platform.python_version()} ({detail})"
    )


def _package_check() -> CheckResult:
    try:
        installed = version("proton-safe-mcp")
    except PackageNotFoundError:
        installed = "development checkout"
    return CheckResult("Package", "PASS", installed)


def _platform_check() -> CheckResult:
    operating_system = platform.system() or "unknown"
    supported = operating_system == "Linux"
    detail = "supported" if supported else "Linux required"
    return CheckResult(
        "Platform", "PASS" if supported else "FAIL", f"{operating_system} ({detail})"
    )


def _configuration_check() -> tuple[Settings | None, CheckResult]:
    """Read the configuration without creating directories, hiding any private path."""
    try:
        settings = Settings.from_env(create_directories=False)
    except OSError as exc:
        return None, CheckResult(
            "Configuration", "FAIL", f"could not read local configuration ({type(exc).__name__})"
        )
    except ProtonMCPError as exc:
        return None, CheckResult("Configuration", "FAIL", str(exc))
    return settings, CheckResult(
        "Configuration", "PASS", "Bridge account and loopback IMAP port are configured"
    )


def _sender_addresses_check(settings: Settings) -> CheckResult:
    alias_count = len(settings.sender_addresses) - 1
    return CheckResult(
        "Sender addresses",
        "PASS",
        (
            f"primary address plus {alias_count} alias(es) from PROTON_BRIDGE_ALIASES"
            if alias_count
            else "primary address only; set PROTON_BRIDGE_ALIASES to draft as an alias"
        ),
    )


def _state_directory_check(settings: Settings) -> CheckResult:
    try:
        metadata = settings.state_dir.stat()
    except FileNotFoundError:
        return CheckResult(
            "State directory",
            "WARN",
            "not created yet; first use will create it with private permissions",
        )
    except OSError as exc:
        return CheckResult(
            "State directory", "FAIL", f"could not inspect permissions ({type(exc).__name__})"
        )
    mode = stat.S_IMODE(metadata.st_mode)
    private = stat.S_ISDIR(metadata.st_mode) and mode & 0o700 == 0o700 and mode & 0o077 == 0
    return CheckResult(
        "State directory",
        "PASS" if private else "FAIL",
        (
            "private permissions"
            if private
            else "must grant rwx to the owner and be inaccessible to group and others"
        ),
    )


def _credential_check(settings: Settings | None) -> CheckResult:
    if settings is None:
        return CheckResult("Credential", "SKIP", "configuration must pass first")
    try:
        get_bridge_password(settings.bridge_user)
    except keyring.errors.KeyringError as exc:
        return CheckResult("Credential", "FAIL", f"OS keyring lookup failed ({type(exc).__name__})")
    except ProtonMCPError as exc:
        return CheckResult("Credential", "FAIL", str(exc))
    if os.environ.get("PROTON_BRIDGE_PASSWORD"):
        return CheckResult(
            "Credential",
            "WARN",
            "PROTON_BRIDGE_PASSWORD is set; unset it to use the OS keyring "
            "(run `proton-safe-mcp setup`)",
        )
    return CheckResult("Credential", "PASS", "available from the OS keyring")


def _bridge_check(settings: Settings) -> CheckResult:
    try:
        ProtonBridgeClient(settings).status()
    except ProtonMCPError as exc:
        return CheckResult("Bridge", "FAIL", str(exc))
    return CheckResult("Bridge", "PASS", "authenticated IMAP connection succeeded")


def run_checks() -> list[CheckResult]:
    """Run non-destructive checks without returning credentials or mailbox data."""

    results = [_python_check(), _package_check(), _platform_check()]
    if results[-1].status == "FAIL":
        # Nothing below is meaningful off Linux, and it must not touch credentials.
        return results

    settings, configuration = _configuration_check()
    results.append(configuration)
    if settings is not None:
        results.append(_sender_addresses_check(settings))
        results.append(_state_directory_check(settings))

    credential = _credential_check(settings)
    results.append(credential)
    if settings is None or credential.status == "FAIL":
        results.append(
            CheckResult("Bridge", "SKIP", "configuration and credential must pass first")
        )
    else:
        results.append(_bridge_check(settings))
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

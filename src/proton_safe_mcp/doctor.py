"""Privacy-safe installation diagnostics for Proton Safe MCP."""

from __future__ import annotations

import os
import platform
import stat
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Final, Literal

import keyring.errors

from .config import Settings
from .errors import ProtonMCPError
from .mail import ProtonBridgeClient
from .secrets import get_bridge_password, keyring_status, secret_service_backend_available

Status = Literal["PASS", "WARN", "FAIL", "SKIP"]

REPORT_SCHEMA_VERSION: Final = 1


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One diagnostic result that is safe to print or paste into an issue.

    ``id`` and ``code`` are stable machine values: the desktop assistant translates from
    the code and never parses ``detail``.
    """

    id: str
    name: str
    status: Status
    detail: str
    code: str


def _python_check() -> CheckResult:
    supported = sys.version_info >= (3, 11)
    detail = "supported" if supported else "3.11 or newer required"
    return CheckResult(
        "python",
        "Python",
        "PASS" if supported else "FAIL",
        f"{platform.python_version()} ({detail})",
        "PYTHON_SUPPORTED" if supported else "PYTHON_TOO_OLD",
    )


def _installed_version() -> str:
    try:
        return version("proton-safe-mcp")
    except PackageNotFoundError:
        return "development checkout"


def _package_check() -> CheckResult:
    return CheckResult("package", "Package", "PASS", _installed_version(), "PACKAGE_PRESENT")


def _platform_check() -> CheckResult:
    operating_system = platform.system() or "unknown"
    supported = operating_system == "Linux"
    detail = "supported" if supported else "Linux required"
    return CheckResult(
        "platform",
        "Platform",
        "PASS" if supported else "FAIL",
        f"{operating_system} ({detail})",
        "PLATFORM_SUPPORTED" if supported else "PLATFORM_UNSUPPORTED",
    )


def _configuration_check(config_path: Path | None) -> tuple[Settings | None, CheckResult]:
    """Read the configuration without creating directories, hiding any private path."""
    try:
        if config_path is None:
            settings = Settings.from_env(create_directories=False)
        else:
            settings = Settings.from_config_file(config_path, create_directories=False)
    except OSError as exc:
        return None, CheckResult(
            "configuration",
            "Configuration",
            "FAIL",
            f"could not read local configuration ({type(exc).__name__})",
            "CONFIG_INVALID",
        )
    except ProtonMCPError as exc:
        return None, CheckResult(
            "configuration", "Configuration", "FAIL", str(exc), exc.code or "CONFIG_INVALID"
        )
    source = (
        "managed configuration file"
        if settings.config_source == "file"
        else "environment variables"
    )
    return settings, CheckResult(
        "configuration",
        "Configuration",
        "PASS",
        f"Bridge account and loopback IMAP port are configured from {source}",
        "CONFIG_LOADED",
    )


def _sender_addresses_check(settings: Settings) -> CheckResult:
    alias_count = len(settings.sender_addresses) - 1
    managed = settings.config_source == "file"
    if alias_count:
        detail = (
            f"primary address plus {alias_count} alias(es) from the managed configuration"
            if managed
            else f"primary address plus {alias_count} alias(es) from PROTON_BRIDGE_ALIASES"
        )
    else:
        detail = (
            "primary address only; add aliases in the setup assistant"
            if managed
            else "primary address only; set PROTON_BRIDGE_ALIASES to draft as an alias"
        )
    return CheckResult("sender_addresses", "Sender addresses", "PASS", detail, "SENDERS_CONFIGURED")


def _state_directory_check(settings: Settings) -> CheckResult:
    try:
        metadata = settings.state_dir.stat()
    except FileNotFoundError:
        return CheckResult(
            "state_directory",
            "State directory",
            "WARN",
            "not created yet; first use will create it with private permissions",
            "STATE_DIR_MISSING",
        )
    except OSError as exc:
        return CheckResult(
            "state_directory",
            "State directory",
            "FAIL",
            f"could not inspect permissions ({type(exc).__name__})",
            "STATE_DIR_UNREADABLE",
        )
    mode = stat.S_IMODE(metadata.st_mode)
    private = stat.S_ISDIR(metadata.st_mode) and mode & 0o700 == 0o700 and mode & 0o077 == 0
    return CheckResult(
        "state_directory",
        "State directory",
        "PASS" if private else "FAIL",
        (
            "private permissions"
            if private
            else "must grant rwx to the owner and be inaccessible to group and others"
        ),
        "STATE_DIR_PRIVATE" if private else "STATE_DIR_PERMISSIONS",
    )


def _keyring_detail(state: str) -> str:
    if state == "available":
        return "Secret Service is available for this session"
    if not secret_service_backend_available():
        # A build that forgot the dynamic backend modules must not look like a user's
        # locked session: this sentence is what the packaging check looks for.
        return "the Secret Service backend is missing from this installation"
    if state == "locked":
        return "the session keyring is locked"
    return "Secret Service is installed but not reachable in this session"


def _keyring_check() -> CheckResult:
    """Classify the session keyring. Managed setups have no other place for the secret."""
    status = keyring_status()
    passing = status.usable_for_managed_setup
    return CheckResult(
        "keyring",
        "Keyring",
        "PASS" if passing else "FAIL",
        _keyring_detail(status.state),
        status.code,
    )


def _credential_check(settings: Settings | None) -> CheckResult:
    if settings is None:
        return CheckResult(
            "credential", "Credential", "SKIP", "configuration must pass first", "CHECK_SKIPPED"
        )
    managed = settings.config_source == "file"
    try:
        get_bridge_password(settings.bridge_user, allow_environment=not managed)
    except keyring.errors.KeyringError as exc:
        return CheckResult(
            "credential",
            "Credential",
            "FAIL",
            f"OS keyring lookup failed ({type(exc).__name__})",
            "KEYRING_UNAVAILABLE",
        )
    except ProtonMCPError as exc:
        return CheckResult(
            "credential", "Credential", "FAIL", str(exc), exc.code or "CREDENTIAL_MISSING"
        )
    if not os.environ.get("PROTON_BRIDGE_PASSWORD"):
        return CheckResult(
            "credential", "Credential", "PASS", "available from the OS keyring", "CREDENTIAL_STORED"
        )
    if managed:
        return CheckResult(
            "credential",
            "Credential",
            "PASS",
            "available from the OS keyring; PROTON_BRIDGE_PASSWORD is set but ignored "
            "by a managed configuration",
            "CREDENTIAL_STORED",
        )
    return CheckResult(
        "credential",
        "Credential",
        "WARN",
        "PROTON_BRIDGE_PASSWORD is set; unset it to use the OS keyring "
        "(run `proton-safe-mcp setup`)",
        "CREDENTIAL_FROM_ENVIRONMENT",
    )


def _bridge_check(settings: Settings) -> CheckResult:
    """Authenticate and log out. No mailbox is selected and no counter is read."""
    try:
        ProtonBridgeClient(settings).probe()
    except ProtonMCPError as exc:
        return CheckResult(
            "bridge", "Bridge", "FAIL", str(exc), exc.code or "BRIDGE_CONNECTION_FAILED"
        )
    return CheckResult(
        "bridge",
        "Bridge",
        "PASS",
        "authenticated IMAP connection succeeded",
        "BRIDGE_AUTHENTICATED",
    )


def run_checks(*, config_path: Path | None = None) -> list[CheckResult]:
    """Run non-destructive checks without returning credentials or mailbox data."""

    results = [_python_check(), _package_check(), _platform_check()]
    if results[-1].status == "FAIL":
        # Nothing below is meaningful off Linux, and it must not touch credentials.
        return results

    settings, configuration = _configuration_check(config_path)
    results.append(configuration)
    if settings is not None:
        results.append(_sender_addresses_check(settings))
        results.append(_state_directory_check(settings))

    if config_path is not None:
        # A managed setup keeps the credential in the keyring and nowhere else, so the
        # backend itself is part of the diagnosis. The historic mode keeps its own
        # fallbacks and its report unchanged.
        results.append(_keyring_check())

    credential = _credential_check(settings)
    results.append(credential)
    if settings is None or credential.status == "FAIL":
        results.append(
            CheckResult(
                "bridge",
                "Bridge",
                "SKIP",
                "configuration and credential must pass first",
                "CHECK_SKIPPED",
            )
        )
    else:
        results.append(_bridge_check(settings))
    return results


def json_report(results: list[CheckResult]) -> dict[str, Any]:
    """Build a machine-readable report that carries no private value.

    Only stable identifiers and codes are emitted: no address, folder name, mailbox
    statistic, filesystem path, configuration value or raw subprocess output. Versions sit
    in their own section because they are the part a bug report legitimately needs.
    """
    failed = any(result.status == "FAIL" for result in results)
    warned = any(result.status == "WARN" for result in results)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "overall": "action_required" if failed else ("warning" if warned else "ok"),
        "versions": {
            "proton_safe_mcp": _installed_version(),
            "python": platform.python_version(),
            "system": platform.system() or "unknown",
            "system_release": platform.release() or "unknown",
        },
        "checks": [
            {"id": result.id, "status": result.status.lower(), "code": result.code}
            for result in results
        ],
    }


def exit_code(results: list[CheckResult]) -> int:
    return 1 if any(result.status == "FAIL" for result in results) else 0


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


def run(*, config_path: Path | None = None, as_json: bool = False) -> int:
    """Run and render the diagnostic report."""

    results = run_checks(config_path=config_path)
    if not as_json:
        return print_report(results)
    import json

    print(json.dumps(json_report(results), indent=2, sort_keys=True))
    return exit_code(results)

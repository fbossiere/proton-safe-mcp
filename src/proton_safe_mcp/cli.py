"""Local administration CLI.

``--config`` selects the managed mode: settings come from that file only, and the Bridge
credential from the OS keyring only. Without it, every command behaves exactly as before
and never looks for a configuration file.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from .config import Settings, set_startup_settings
from .errors import ConfigurationError, ProtonMCPError
from .secrets import require_managed_keyring, store_bridge_password


def _resolve_config(raw: str | None) -> Path | None:
    if raw is None:
        return None
    path = Path(raw)
    if not path.is_absolute():
        raise ConfigurationError("--config requires an absolute path", code="CONFIG_INVALID")
    return path


def _settings_for(config_path: Path | None) -> Settings:
    if config_path is None:
        return Settings.from_env()
    return Settings.from_config_file(config_path)


def _cmd_setup(settings: Settings) -> int:
    if settings.config_source == "file":
        # A managed setup has no environment fallback, so an unusable keyring must stop
        # here rather than store the credential somewhere weaker.
        require_managed_keyring()
    password = getpass.getpass("Proton Bridge generated IMAP password: ")
    confirmation = getpass.getpass("Repeat Bridge password: ")
    if password != confirmation:
        raise ProtonMCPError("Passwords do not match")
    store_bridge_password(settings.bridge_user, password)
    print(f"Bridge credential stored in the OS keyring for {settings.bridge_user}.")
    return 0


def _cmd_serve(settings: Settings) -> int:
    # Pinned before the tool surface is imported: the server binds its tools at import time.
    set_startup_settings(settings if settings.config_source == "file" else None)
    from .server import run

    run()
    return 0


def _cmd_doctor(config_path: Path | None, as_json: bool) -> int:
    from .doctor import run

    return run(config_path=config_path, as_json=as_json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proton-safe-mcp",
        description="Draft-only Proton Mail MCP server with secure attachment staging.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    config_help = (
        "Absolute path to a managed configuration file. It becomes the only source of "
        "settings, and the OS keyring the only source of the Bridge credential."
    )
    doctor = sub.add_parser("doctor", help="Check the local setup without showing private data")
    doctor.add_argument("--config", help=config_help)
    doctor.add_argument(
        "--json", action="store_true", help="Print a redacted machine-readable report"
    )
    setup = sub.add_parser(
        "setup", help="Store the Bridge-generated IMAP password in the OS keyring"
    )
    setup.add_argument("--config", help=config_help)
    serve = sub.add_parser("serve", help="Run the MCP server over STDIO")
    serve.add_argument("--config", help=config_help)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config_path = _resolve_config(args.config)
        if args.command == "doctor":
            return _cmd_doctor(config_path, args.json)
        settings = _settings_for(config_path)
        if args.command == "setup":
            return _cmd_setup(settings)
        # argparse restricts `command` to the three registered choices.
        return _cmd_serve(settings)
    except (ProtonMCPError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

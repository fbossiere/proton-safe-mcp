"""Local administration CLI."""

from __future__ import annotations

import argparse
import getpass
import json
import sys

from .config import Settings
from .errors import ProtonMCPError
from .secrets import store_bridge_password


def _cmd_setup(settings: Settings) -> int:
    password = getpass.getpass("Proton Bridge generated IMAP password: ")
    confirmation = getpass.getpass("Repeat Bridge password: ")
    if password != confirmation:
        raise ProtonMCPError("Passwords do not match")
    store_bridge_password(settings.bridge_user, password)
    print(f"Bridge credential stored in the OS keyring for {settings.bridge_user}.")
    return 0


def _cmd_serve() -> int:
    from .server import run

    run()
    return 0


def _cmd_doctor() -> int:
    from .doctor import run

    return run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proton-safe-mcp",
        description="Draft-only Proton Mail MCP server with secure attachment staging.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check the local setup without showing private data")
    sub.add_parser("setup", help="Store the Bridge-generated IMAP password in the OS keyring")
    sub.add_parser("serve", help="Run the MCP server over STDIO")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return _cmd_doctor()
        settings = Settings.from_env()
        if args.command == "setup":
            return _cmd_setup(settings)
        if args.command == "serve":
            return _cmd_serve()
        return 2
    except (ProtonMCPError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

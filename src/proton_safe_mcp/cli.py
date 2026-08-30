"""Local administration and human approval CLI."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Any

from .config import Settings
from .drafts import DraftApprovalStore, approve_request, reject_request
from .errors import ProtonMCPError
from .secrets import store_bridge_password


def _load_request(settings: Settings, draft_id: str) -> dict[str, Any]:
    DraftApprovalStore._validate_id(draft_id)
    path = settings.approvals_dir / f"{draft_id}.request.json"
    if not path.is_file() or path.is_symlink():
        raise ProtonMCPError("Unknown or expired draft request")
    request = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise ProtonMCPError("Draft request file is malformed")
    return request


def _print_request(request: dict[str, Any]) -> None:
    print(f"Draft ID: {request['draft_id']}")
    print(f"To: {', '.join(request['to'])}")
    if request.get("cc"):
        print(f"Cc: {', '.join(request['cc'])}")
    if request.get("bcc"):
        print(f"Bcc: {', '.join(request['bcc'])}")
    print(f"Subject: {request['subject']}")
    print("Attachments:")
    if request.get("attachments"):
        for item in request["attachments"]:
            print(f"  - {item['filename']} ({item['size_bytes']} bytes, sha256 {item['sha256']})")
    else:
        print("  (none)")
    preview = request.get("body_preview", "").replace("\n", " ")
    print(f"Body preview: {preview}")
    print(f"Proposal digest: {request['digest']}")


def _cmd_setup(settings: Settings) -> int:
    password = getpass.getpass("Proton Bridge generated IMAP password: ")
    confirmation = getpass.getpass("Repeat Bridge password: ")
    if password != confirmation:
        raise ProtonMCPError("Passwords do not match")
    store_bridge_password(settings.bridge_user, password)
    print(f"Bridge credential stored in the OS keyring for {settings.bridge_user}.")
    return 0


def _cmd_approve(settings: Settings, draft_id: str) -> int:
    request = _load_request(settings, draft_id)
    _print_request(request)
    expected = f"APPROVE {draft_id[-8:]}"
    entered = input(f"Type {expected!r} to authorize creation of this Proton draft: ")
    if entered != expected:
        raise ProtonMCPError("Approval cancelled")
    approve_request(settings, draft_id)
    print("Approved. The MCP client may now call commit_approved_draft.")
    return 0


def _cmd_reject(settings: Settings, draft_id: str) -> int:
    request = _load_request(settings, draft_id)
    _print_request(request)
    reject_request(settings, draft_id)
    print("Rejected.")
    return 0


def _cmd_show(settings: Settings, draft_id: str) -> int:
    _print_request(_load_request(settings, draft_id))
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
    for name, help_text in (
        ("approve", "Approve one pending draft after inspecting its exact summary"),
        ("reject", "Reject one pending draft"),
        ("show", "Show one pending draft without approving it"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("draft_id")
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
        if args.command == "approve":
            return _cmd_approve(settings, args.draft_id)
        if args.command == "reject":
            return _cmd_reject(settings, args.draft_id)
        if args.command == "show":
            return _cmd_show(settings, args.draft_id)
        return 2
    except (ProtonMCPError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

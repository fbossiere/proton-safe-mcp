"""Install the pinned Inno Setup compiler, or say plainly why it cannot be installed.

The compiler is a build input like any other, so it is pinned by version and by digest
and verified before it runs. An unpinned digest is not treated as "verify later": the
download is refused, because a build that ran an unverified compiler and then signed its
output would have verified nothing.

    python packaging/windows/fetch_innosetup.py --check-pin   # is the digest recorded?
    python packaging/windows/fetch_innosetup.py --install     # download, verify, install
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

LOCK = Path(__file__).resolve().parent / "innosetup.lock"
#: A compiler download is a few tens of megabytes; anything far larger is not one.
MAX_BYTES = 200 * 1024 * 1024


def read_lock() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip()
    return values


def pinned(lock: dict[str, str]) -> bool:
    digest = lock.get("sha256", "")
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", digest))


def download(url: str) -> bytes:
    if not re.fullmatch(
        r"https://github\.com/jrsoftware/issrc/releases/download/is-[0-9_]+/"
        r"innosetup-[0-9.]+-x64\.exe",
        url,
    ):
        raise SystemExit("the compiler is only ever fetched from its publisher's own host")
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - host checked
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SystemExit("the download is larger than a compiler installer should be")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-pin", action="store_true", help="report whether the digest is set")
    parser.add_argument("--install", action="store_true", help="download, verify and install")
    arguments = parser.parse_args(argv)

    lock = read_lock()
    version = lock.get("version", "unknown")
    ready = pinned(lock)

    if arguments.check_pin:
        # Written for a CI step to read, so the job can report the state instead of
        # failing on something nobody has been asked to do yet.
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with Path(output).open("a", encoding="utf-8") as handle:
                handle.write(f"ready={'true' if ready else 'false'}\n")
                handle.write(f"version={version}\n")
        print(
            f"Inno Setup {version}: digest {'pinned' if ready else 'NOT pinned'}",
            file=sys.stdout if ready else sys.stderr,
        )
        return 0 if ready else 1

    if not arguments.install:
        parser.print_help()
        return 2

    if not ready:
        print(
            f"Inno Setup {version} has no pinned digest in {LOCK.name}.\n"
            "Record the SHA-256 of the publisher's own download first; this build will "
            "not run an unverified compiler.",
            file=sys.stderr,
        )
        return 1

    print(f"Downloading Inno Setup {version}…")
    payload = download(lock["url"])
    digest = hashlib.sha256(payload).hexdigest()
    if digest != lock["sha256"].lower():
        print(
            f"the download does not match the pinned digest\n  expected {lock['sha256']}\n"
            f"  received {digest}",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory() as workspace:
        installer = Path(workspace) / f"innosetup-{version}.exe"
        installer.write_bytes(payload)
        print(f"Verified {digest}; installing…")
        # Windows validates the certificate chain and the publisher, not merely a
        # digest obtained from the same download location.
        verification = subprocess.run(  # noqa: S603 - fixed script and argv
            [
                shutil.which("pwsh") or "pwsh",
                "-NoProfile",
                "-File",
                str(LOCK.with_name("verify_publisher.ps1")),
                "-Path",
                str(installer),
            ],
            check=False,
            timeout=120,
        )
        if verification.returncode != 0:
            return 1
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"],
            check=False,
            timeout=180,
        )
    if completed.returncode != 0:
        print(f"the compiler installer exited with {completed.returncode}", file=sys.stderr)
        return completed.returncode
    print(f"Inno Setup {version} installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

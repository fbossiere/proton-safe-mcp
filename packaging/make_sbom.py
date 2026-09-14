"""Inventory what a built bundle actually contains, as CycloneDX JSON.

Two sources, because neither alone is the truth:

* the Python distributions installed in the environment the bundle was frozen from,
  which is where names, versions and licences come from;
* the binaries inside the bundle directory, which is what actually ships — a native
  library pulled in by a wheel appears here even though it is not a distribution.

Nothing is downloaded and no network call is made: an inventory that asked a registry
what a package contains would not be describing this build.

Usage::

    python packaging/make_sbom.py <bundle-dir> <output.json> --platform windows-x64
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import distributions
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from version import ROOT, engine_version

#: Files that are code, and therefore belong in an inventory of what runs.
BINARY_SUFFIXES = frozenset({".exe", ".dll", ".pyd", ".so", ".dylib", ".com"})


def _commit() -> str:
    for name in ("GITHUB_SHA", "SOURCE_COMMIT"):
        value = os.environ.get(name)
        if value:
            return value
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _licence(metadata: Any) -> str:
    declared = metadata.get("License-Expression") or metadata.get("License")
    if declared and "\n" not in declared:
        return declared.strip()
    for classifier in metadata.get_all("Classifier") or []:
        if classifier.startswith("License :: "):
            return classifier.rsplit(" :: ", 1)[-1]
    return ""


def python_components() -> list[dict[str, Any]]:
    """Every Python distribution importable in the environment that froze the bundle."""
    components: list[dict[str, Any]] = []
    ordered = sorted(distributions(), key=lambda item: str(item.metadata["Name"]).lower())
    for distribution in ordered:
        name = distribution.metadata["Name"]
        if not name:
            continue
        component: dict[str, Any] = {
            "type": "library",
            "name": str(name),
            "version": str(distribution.version),
            "purl": f"pkg:pypi/{str(name).lower()}@{distribution.version}",
            "scope": "required",
        }
        licence = _licence(distribution.metadata)
        if licence:
            component["licenses"] = [{"license": {"name": licence}}]
        components.append(component)
    return components


def binary_components(bundle: Path) -> list[dict[str, Any]]:
    """Every executable and native library actually present in the bundle."""
    components: list[dict[str, Any]] = []
    for path in sorted(bundle.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in BINARY_SUFFIXES:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        components.append(
            {
                "type": "file",
                "name": path.relative_to(bundle).as_posix(),
                "version": "",
                "hashes": [{"alg": "SHA-256", "content": digest}],
            }
        )
    return components


def build(bundle: Path, platform: str) -> dict[str, Any]:
    version = engine_version()
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": {
                "type": "application",
                "name": "proton-safe-mcp",
                "version": version,
                "purl": f"pkg:pypi/proton-safe-mcp@{version}",
            },
            "properties": [
                {"name": "proton-safe:platform", "value": platform},
                {"name": "proton-safe:commit", "value": _commit()},
                {"name": "proton-safe:python", "value": sys.version.split()[0]},
            ],
        },
        "components": python_components() + binary_components(bundle),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="the built bundle directory")
    parser.add_argument("output", type=Path, help="where to write the CycloneDX document")
    parser.add_argument("--platform", required=True, help="e.g. windows-x64")
    arguments = parser.parse_args(argv)

    if not arguments.bundle.is_dir():
        print(f"no bundle directory at {arguments.bundle}", file=sys.stderr)
        return 1
    document = build(arguments.bundle, arguments.platform)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"SBOM written to {arguments.output} ({len(document['components'])} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

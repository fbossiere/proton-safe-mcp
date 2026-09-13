"""Render the managed plugin from resources shipped inside this package.

Nothing is downloaded during an installation: the manifest, the three canonical skills and
the MCP configuration all come from the revision this build was made from, so the runtime
and the workflows it packages can never drift apart.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from .. import __version__
from ..errors import ProtonMCPError
from .models import Code

#: A marketplace of the assistant's own, so the managed entry cannot collide with the
#: generic `personal` marketplace a manual installation may already have registered.
MANAGED_MARKETPLACE: Final = "proton-safe-desktop"
MANAGED_PLUGIN: Final = "proton-safe"
MANAGED_SERVER_NAME: Final = "proton-safe"

CANONICAL_SKILLS: Final = (
    "extract-proton-attachment",
    "prepare-proton-draft",
    "review-proton-mail",
)

_PROVENANCE_FILE: Final = "provenance.json"


class PluginAssetError(ProtonMCPError):
    """The canonical plugin resources are missing or unusable."""


def default_plugin_dir() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg_data_home) if xdg_data_home.startswith("/") else Path.home() / ".local/share"
    return base / "proton-safe-mcp" / "desktop-plugin"


def canonical_root() -> Path:
    """Return the canonical plugin resources bundled with this package.

    The wheel and the desktop bundle carry them as package data. A development checkout
    falls back to the repository copy, which is the same tree the build force-includes.
    """
    packaged = Path(__file__).resolve().parent.parent / "plugin_resources"
    if (packaged / ".codex-plugin" / "plugin.json").is_file():
        return packaged
    checkout = Path(__file__).resolve().parents[3] / "plugins" / "proton-safe"
    if (checkout / ".codex-plugin" / "plugin.json").is_file():
        return checkout
    raise PluginAssetError(
        "The packaged plugin resources are missing from this installation.",
        code=Code.PLUGIN_ASSETS_INVALID,
    )


def _resource_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def resource_digest(root: Path) -> str:
    """Digest the canonical tree so a rendered plugin records what it was built from."""
    digest = hashlib.sha256()
    for path in _resource_files(root):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ManagedPluginAssets:
    """A rendered, self-contained local marketplace the client can install from."""

    marketplace_dir: Path
    plugin_dir: Path
    marketplace_name: str
    plugin_name: str
    plugin_version: str
    engine_version: str
    resource_digest: str

    @property
    def plugin_reference(self) -> str:
        """The `plugin@marketplace` reference the client's install command takes."""
        return f"{self.plugin_name}@{self.marketplace_name}"


def _plugin_version(base_version: str, digest: str) -> str:
    """Build a version that changes whenever the package or the resources change.

    Clients cache plugin resources by version, so a package update that left the version
    untouched could keep serving the previous skills.
    """
    engine = __version__.replace("+", ".")
    return f"{base_version}+codex.{engine}.{digest[:12]}"


def _load_manifest(root: Path) -> dict[str, Any]:
    try:
        manifest = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginAssetError(
            "The packaged plugin manifest cannot be read.", code=Code.PLUGIN_ASSETS_INVALID
        ) from exc
    if not isinstance(manifest, dict) or manifest.get("name") != MANAGED_PLUGIN:
        raise PluginAssetError(
            "The packaged plugin manifest is not the expected one.",
            code=Code.PLUGIN_ASSETS_INVALID,
        )
    return manifest


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def render(
    *,
    serve_command: tuple[str, ...],
    destination: Path | None = None,
) -> ManagedPluginAssets:
    """Write a local marketplace whose MCP entry launches exactly ``serve_command``.

    The command is an absolute runtime path plus ``--config``. It needs neither ``uvx`` nor
    any ``PROTON_*`` variable, and it carries no credential: the runtime reads the account
    from its configuration file and the password from the OS keyring.
    """
    if not serve_command or not Path(serve_command[0]).is_absolute():
        raise PluginAssetError(
            "The managed runtime must be referenced by an absolute path.",
            code=Code.PLUGIN_ASSETS_INVALID,
        )
    root = canonical_root()
    digest = resource_digest(root)
    manifest = _load_manifest(root)

    marketplace_dir = (destination or default_plugin_dir()).resolve()
    plugin_dir = marketplace_dir / "plugins" / MANAGED_PLUGIN

    marketplace_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Replacing the managed tree wholesale keeps an interrupted previous render from
    # leaving a stale skill behind. Only this directory is ever removed.
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
    plugin_dir.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    shutil.copytree(root, plugin_dir)
    for path in _resource_files(plugin_dir):
        path.chmod(0o600)
    for directory in [plugin_dir, *(p for p in plugin_dir.rglob("*") if p.is_dir())]:
        directory.chmod(0o700)

    missing = [
        name
        for name in CANONICAL_SKILLS
        if not (plugin_dir / "skills" / name / "SKILL.md").is_file()
    ]
    if missing:
        raise PluginAssetError(
            "The packaged plugin is missing its canonical skills.",
            code=Code.PLUGIN_ASSETS_INVALID,
        )

    base_version = str(manifest.get("version", "0.1.0")).partition("+")[0]
    plugin_version = _plugin_version(base_version, digest)
    manifest["version"] = plugin_version
    _write_json(plugin_dir / ".codex-plugin" / "plugin.json", manifest)

    # The managed server replaces the published uvx entry: same server name, absolute
    # runtime, explicit configuration, and no environment passthrough for PROTON_* values.
    _write_json(
        plugin_dir / ".mcp.json",
        {
            "mcpServers": {
                MANAGED_SERVER_NAME: {
                    "command": serve_command[0],
                    "args": list(serve_command[1:]),
                    "env_vars": ["DBUS_SESSION_BUS_ADDRESS", "HOME", "XDG_RUNTIME_DIR"],
                    "startup_timeout_sec": 30,
                    "tool_timeout_sec": 120,
                }
            }
        },
    )
    _write_json(
        marketplace_dir / ".agents" / "plugins" / "marketplace.json",
        {
            "name": MANAGED_MARKETPLACE,
            "interface": {"displayName": "Proton Safe (desktop)"},
            "plugins": [
                {
                    "name": MANAGED_PLUGIN,
                    "source": {"source": "local", "path": f"./plugins/{MANAGED_PLUGIN}"},
                    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    "category": manifest.get("interface", {}).get("category", "Communication"),
                }
            ],
        },
    )
    _write_json(
        marketplace_dir / _PROVENANCE_FILE,
        {
            "engine_version": __version__,
            "plugin_version": plugin_version,
            "resource_digest": digest,
            "marketplace": MANAGED_MARKETPLACE,
            "plugin": MANAGED_PLUGIN,
        },
    )
    return ManagedPluginAssets(
        marketplace_dir=marketplace_dir,
        plugin_dir=plugin_dir,
        marketplace_name=MANAGED_MARKETPLACE,
        plugin_name=MANAGED_PLUGIN,
        plugin_version=plugin_version,
        engine_version=__version__,
        resource_digest=digest,
    )


def read_provenance(destination: Path | None = None) -> dict[str, Any] | None:
    """Return what a previously rendered plugin was built from, or None."""
    path = (destination or default_plugin_dir()) / _PROVENANCE_FILE
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def is_current(destination: Path | None = None) -> bool:
    """Whether the rendered plugin matches the resources this build ships."""
    provenance = read_provenance(destination)
    if provenance is None:
        return False
    try:
        digest = resource_digest(canonical_root())
    except PluginAssetError:
        return False
    return (
        provenance.get("engine_version") == __version__
        and provenance.get("resource_digest") == digest
    )

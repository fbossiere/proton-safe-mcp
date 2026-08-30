from __future__ import annotations

import json
from pathlib import Path

from proton_safe_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "proton-safe"


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_plugin_manifest_and_marketplace_are_consistent():
    manifest = _load_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
    marketplace = _load_json(ROOT / ".agents" / "plugins" / "marketplace.json")

    assert manifest["name"] == "proton-safe"
    base_version, separator, cachebuster = manifest["version"].partition("+")
    assert base_version == "0.1.0"
    assert separator == "+"
    assert cachebuster.startswith("codex.")
    assert manifest["skills"] == "./skills/"
    assert manifest["mcpServers"] == "./.mcp.json"
    assert "apps" not in manifest

    entries = marketplace["plugins"]
    entry = next(item for item in entries if item["name"] == manifest["name"])
    assert entry["source"] == {"source": "local", "path": "./plugins/proton-safe"}
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert entry["category"] == manifest["interface"]["category"]


def test_plugin_launches_pinned_stdio_server_without_credentials_or_remote_bridge():
    config = _load_json(PLUGIN_ROOT / ".mcp.json")
    server = config["mcpServers"]["proton-safe"]

    assert server["command"] == "uvx"
    assert server["args"] == [
        "--from",
        f"proton-safe-mcp=={__version__}",
        "proton-safe-mcp",
        "serve",
    ]

    env_vars = set(server["env_vars"])
    assert "PROTON_BRIDGE_USER" in env_vars
    assert "PROTON_IMAP_PORT" in env_vars
    assert "PROTON_BRIDGE_PASSWORD" not in env_vars
    assert "PROTON_BRIDGE_HOST" not in env_vars

    serialized = json.dumps(config)
    assert "plugin_asdk_app" not in serialized
    assert "http://" not in serialized
    assert "https://" not in serialized


def test_plugin_skills_preserve_untrusted_mail_and_out_of_band_approval_boundaries():
    skill_files = sorted((PLUGIN_ROOT / "skills").glob("*/SKILL.md"))
    assert [path.parent.name for path in skill_files] == [
        "prepare-proton-draft",
        "review-proton-mail",
    ]

    text = "\n".join(path.read_text(encoding="utf-8") for path in skill_files).lower()
    assert "attacker-controlled" in text
    assert "explicit user authorization" in text
    assert "do not run the approval command" in text
    assert "cannot send" in text
    assert "never attempt to send, delete, move" in text
    assert "proton_bridge_password" not in text
    assert "plugin_asdk_app_" not in text


def test_plugin_docs_are_local_first_and_tunnel_optional():
    guide = (ROOT / "docs" / "openai-plugin.md").read_text(encoding="utf-8").lower()

    assert "chatgpt desktop and codex on the bridge machine" in guide
    assert "settings → mcp servers" in guide
    assert "direct mcp registration without the plugin" in guide
    assert "no tunnel or dedicated server is required" in guide
    assert "optional: connect chatgpt web or a remote bridge host" in guide


def test_account_specific_app_mappings_are_ignored_repo_wide():
    patterns = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".app.json" in patterns
    assert not (ROOT / "plugins" / "proton-safe" / ".app.json").exists()

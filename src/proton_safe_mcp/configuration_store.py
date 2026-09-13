"""Persistent TOML configuration for the managed desktop setup.

This file is only ever read when a command is given an explicit ``--config`` path. The
historic environment-driven mode never looks for it, so creating one cannot change an
existing installation that has not been migrated.

Nothing secret is stored here: the Bridge credential lives in the OS keyring only.
"""

from __future__ import annotations

import os
import stat
import tempfile
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final

from .addresses import validate_address
from .errors import ConfigurationError

SCHEMA_VERSION: Final = 1
CONFIG_FILE_NAME: Final = "config.toml"
APPLICATION_DIR_NAME: Final = "proton-safe-mcp"

# Reading a configuration must never be able to pull in a file of arbitrary size.
MAX_CONFIG_BYTES: Final = 64 * 1024
MAX_ALIASES: Final = 24

_PRIVATE_DIR_MODE: Final = 0o700
_PRIVATE_FILE_MODE: Final = 0o600

# name -> (default, maximum). Same values and bounds as the historic environment variables.
LIMIT_BOUNDS: Final[dict[str, tuple[int, int]]] = {
    "max_attachment_bytes": (20 * 1024 * 1024, 25 * 1024 * 1024),
    "max_received_attachment_bytes": (10 * 1024 * 1024, 25 * 1024 * 1024),
    "max_chunk_bytes": (384 * 1024, 1024 * 1024),
    "upload_ttl_seconds": (1800, 86400),
    "max_body_chars": (100_000, 500_000),
}


def default_config_path() -> Path:
    """Return the XDG location of the managed configuration without creating anything."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(xdg_config_home) if xdg_config_home.startswith("/") else Path.home() / ".config"
    return base / APPLICATION_DIR_NAME / CONFIG_FILE_NAME


@dataclass(frozen=True, slots=True)
class StoredConfiguration:
    """The closed set of settings the managed setup persists."""

    bridge_user: str
    imap_port: int = 1143
    aliases: tuple[str, ...] = ()
    state_dir: Path | None = None
    limits: dict[str, int] = field(default_factory=dict)

    def with_limits(self, **values: int) -> StoredConfiguration:
        merged = dict(self.limits)
        merged.update(values)
        return replace(self, limits=merged)


def _fail(message: str, code: str) -> ConfigurationError:
    return ConfigurationError(message, code=code)


def _require_no_extra_keys(table: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise _fail(
            f"Unknown key(s) in {where}: {', '.join(unknown)}",
            "CONFIG_INVALID",
        )


def _require_int(table: dict[str, Any], key: str, where: str) -> int:
    value = table[key]
    # bool is an int subclass; a boolean port is a mistake worth refusing.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(f"{where}.{key} must be an integer", "CONFIG_INVALID")
    return value


def _parse_limits(table: dict[str, Any]) -> dict[str, int]:
    _require_no_extra_keys(table, set(LIMIT_BOUNDS), "[limits]")
    limits: dict[str, int] = {}
    for key in table:
        _, maximum = LIMIT_BOUNDS[key]
        parsed = _require_int(table, key, "[limits]")
        if not 1 <= parsed <= maximum:
            raise _fail(f"[limits].{key} must be between 1 and {maximum}", "CONFIG_INVALID")
        limits[key] = parsed
    return limits


def _parse_paths(table: dict[str, Any]) -> Path | None:
    _require_no_extra_keys(table, {"state_dir"}, "[paths]")
    raw = table.get("state_dir")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise _fail("[paths].state_dir must be a non-empty string", "CONFIG_INVALID")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise _fail("[paths].state_dir must be an absolute path", "CONFIG_INVALID")
    # Validated as a path only. Attachments are never walked or moved to check it.
    return candidate


def _parse_bridge(table: dict[str, Any]) -> tuple[str, int, tuple[str, ...]]:
    _require_no_extra_keys(table, {"user", "imap_port", "aliases"}, "[bridge]")
    raw_user = table.get("user")
    if not isinstance(raw_user, str) or not raw_user.strip():
        raise _fail("[bridge].user is required", "CONFIG_INVALID")
    try:
        user = validate_address(raw_user.strip(), error=ConfigurationError)
    except ConfigurationError as exc:
        raise _fail(f"[bridge].user is not a valid address ({exc})", "CONFIG_INVALID") from exc

    port = _require_int(table, "imap_port", "[bridge]") if "imap_port" in table else 1143
    if not 1 <= port <= 65535:
        raise _fail("[bridge].imap_port must be between 1 and 65535", "CONFIG_INVALID")

    raw_aliases = table.get("aliases", [])
    if not isinstance(raw_aliases, list):
        raise _fail("[bridge].aliases must be a list of addresses", "CONFIG_INVALID")
    if len(raw_aliases) > MAX_ALIASES:
        raise _fail(f"[bridge].aliases may list at most {MAX_ALIASES} addresses", "CONFIG_INVALID")
    seen = {user.casefold()}
    aliases: list[str] = []
    for item in raw_aliases:
        if not isinstance(item, str):
            raise _fail("[bridge].aliases must be a list of addresses", "CONFIG_INVALID")
        try:
            address = validate_address(item.strip(), error=ConfigurationError)
        except ConfigurationError as exc:
            raise _fail(
                f"[bridge].aliases contains an invalid address ({exc})", "CONFIG_INVALID"
            ) from exc
        if address.casefold() in seen:
            continue
        seen.add(address.casefold())
        aliases.append(address)
    return user, port, tuple(aliases)


def parse(text: str) -> StoredConfiguration:
    """Parse configuration text under the closed schema, without touching the filesystem."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise _fail(f"The configuration file is not valid TOML ({exc})", "CONFIG_INVALID") from exc

    _require_no_extra_keys(document, {"schema_version", "bridge", "limits", "paths"}, "the file")

    if "schema_version" not in document:
        raise _fail("schema_version is required", "CONFIG_INVALID")
    schema_version = _require_int(document, "schema_version", "the file")
    if schema_version > SCHEMA_VERSION:
        raise _fail(
            f"This configuration uses schema version {schema_version}, which this version of "
            f"Proton Safe does not understand (it supports {SCHEMA_VERSION}).",
            "CONFIG_SCHEMA_UNSUPPORTED",
        )
    if schema_version < 1:
        raise _fail("schema_version must be 1 or greater", "CONFIG_INVALID")

    for name in ("bridge", "limits", "paths"):
        if name in document and not isinstance(document[name], dict):
            raise _fail(f"[{name}] must be a table", "CONFIG_INVALID")

    bridge = document.get("bridge")
    if not isinstance(bridge, dict):
        raise _fail("[bridge] is required", "CONFIG_INVALID")
    user, port, aliases = _parse_bridge(bridge)

    return StoredConfiguration(
        bridge_user=user,
        imap_port=port,
        aliases=aliases,
        state_dir=_parse_paths(document.get("paths", {})),
        limits=_parse_limits(document.get("limits", {})),
    )


def _check_private_mode(mode: int, path_kind: str) -> None:
    if stat.S_IMODE(mode) & 0o077:
        raise _fail(
            f"The configuration {path_kind} is readable by other accounts on this computer.",
            "CONFIG_PERMISSIONS",
        )


def _check_directory(directory: Path) -> None:
    try:
        info = os.stat(directory, follow_symlinks=True)
    except FileNotFoundError as exc:
        raise _fail("The configuration directory does not exist.", "CONFIG_MISSING") from exc
    except OSError as exc:
        raise _fail(
            f"The configuration directory cannot be inspected ({type(exc).__name__}).",
            "CONFIG_INVALID",
        ) from exc
    if info.st_uid != os.getuid():
        raise _fail("The configuration directory belongs to another account.", "CONFIG_PERMISSIONS")
    _check_private_mode(info.st_mode, "directory")


def read(path: Path) -> StoredConfiguration:
    """Load an explicit configuration file, refusing anything unsafe.

    A missing, malformed, symlinked or world-readable file fails the call. There is no
    silent repair and no fallback to another source: the caller asked for this file.
    """
    path = Path(path)
    if not path.is_absolute():
        raise _fail("The configuration path must be absolute.", "CONFIG_INVALID")

    _check_directory(path.parent)
    try:
        # O_NOFOLLOW refuses a symlink at the final component, and the checks below run
        # against the descriptor actually opened rather than a path re-resolved afterwards.
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError as exc:
        raise _fail("No configuration file was found at that path.", "CONFIG_MISSING") from exc
    except OSError as exc:
        # ELOOP lands here when the path is a symlink.
        raise _fail(
            f"The configuration file cannot be opened ({type(exc).__name__}).",
            "CONFIG_PERMISSIONS" if isinstance(exc, PermissionError) else "CONFIG_INVALID",
        ) from exc

    try:
        # Inspect the descriptor that was actually opened, before wrapping it in a file
        # object: O_RDONLY succeeds on a directory, which fdopen would then reject noisily.
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _fail("The configuration path is not a regular file.", "CONFIG_INVALID")
        if info.st_uid != os.getuid():
            raise _fail("The configuration file belongs to another account.", "CONFIG_PERMISSIONS")
        _check_private_mode(info.st_mode, "file")
        if info.st_size > MAX_CONFIG_BYTES:
            raise _fail("The configuration file is unexpectedly large.", "CONFIG_INVALID")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(MAX_CONFIG_BYTES + 1)
    finally:
        os.close(descriptor)

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _fail("The configuration file is not valid UTF-8.", "CONFIG_INVALID") from exc
    return parse(text)


def _toml_string(value: str) -> str:
    if any(character < " " or character == "\x7f" for character in value):
        raise _fail("A configuration value contains a control character.", "CONFIG_INVALID")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render(configuration: StoredConfiguration) -> str:
    """Serialise the closed schema. Hand-written so the package needs no TOML writer."""
    aliases = ", ".join(_toml_string(alias) for alias in configuration.aliases)
    lines = [
        "# Proton Safe managed configuration. Written by the setup assistant.",
        "# It holds no password: the Bridge credential stays in the OS keyring.",
        f"schema_version = {SCHEMA_VERSION}",
        "",
        "[bridge]",
        f"user = {_toml_string(configuration.bridge_user)}",
        f"imap_port = {configuration.imap_port}",
        f"aliases = [{aliases}]",
    ]
    if configuration.limits:
        lines += ["", "[limits]"]
        lines += [f"{key} = {configuration.limits[key]}" for key in sorted(configuration.limits)]
    if configuration.state_dir is not None:
        lines += ["", "[paths]", f"state_dir = {_toml_string(str(configuration.state_dir))}"]
    return "\n".join(lines) + "\n"


def ensure_private_directory(directory: Path) -> None:
    """Create the product's own configuration directory, private to this account.

    Only the leaf is tightened: parents such as ``~/.config`` keep the permissions the
    user chose, and nothing is changed recursively.
    """
    directory.mkdir(mode=_PRIVATE_DIR_MODE, parents=True, exist_ok=True)
    try:
        info = os.stat(directory, follow_symlinks=False)
    except OSError as exc:
        raise _fail(
            f"The configuration directory cannot be inspected ({type(exc).__name__}).",
            "CONFIG_PERMISSIONS",
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise _fail("The configuration directory is not a directory.", "CONFIG_PERMISSIONS")
    if stat.S_IMODE(info.st_mode) & 0o077:
        directory.chmod(_PRIVATE_DIR_MODE)


def write(configuration: StoredConfiguration, path: Path) -> None:
    """Write the configuration atomically, private to this account."""
    path = Path(path)
    if not path.is_absolute():
        raise _fail("The configuration path must be absolute.", "CONFIG_INVALID")
    directory = path.parent
    ensure_private_directory(directory)

    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".config-", suffix=".toml")
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, _PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(render(configuration))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    directory_descriptor = os.open(directory, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def repair_permissions(path: Path) -> None:
    """Tighten only the product's own configuration file and directory."""
    ensure_private_directory(path.parent)
    if path.exists() and not path.is_symlink():
        path.chmod(_PRIVATE_FILE_MODE)

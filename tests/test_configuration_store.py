"""A04 and the closed-schema rules: the managed file is trusted only when it is safe."""

from __future__ import annotations

import os
import stat

import pytest

from proton_safe_mcp import configuration_store as store
from proton_safe_mcp.errors import ConfigurationError
from proton_safe_mcp.platform_services import posix as posix_services


def _read_code(path):
    with pytest.raises(ConfigurationError) as caught:
        store.read(path)
    return caught.value.code


def test_a_valid_file_round_trips_through_render_and_read(
    write_managed_config, managed_config_path
):
    write_managed_config(
        managed_config_path,
        user="person@example.com",
        port=1144,
        aliases=("billing@example.com",),
    )
    loaded = store.read(managed_config_path)

    assert loaded.bridge_user == "person@example.com"
    assert loaded.imap_port == 1144
    assert loaded.aliases == ("billing@example.com",)
    assert loaded.limits == {}


@pytest.mark.posix_only
def test_the_file_and_its_directory_are_written_private(write_managed_config, managed_config_path):
    write_managed_config(managed_config_path)

    assert stat.S_IMODE(managed_config_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(managed_config_path.parent.stat().st_mode) == 0o700


def test_no_credential_or_host_is_ever_rendered(write_managed_config, managed_config_path):
    write_managed_config(managed_config_path)
    text = managed_config_path.read_text(encoding="utf-8")

    assert "127.0.0.1" not in text
    assert "secret" not in text.lower()
    # The only occurrence of the word is the comment saying none is stored.
    assert text.lower().count("password") == 1
    assert "no password" in text.lower()


def test_a_missing_file_is_refused_without_creating_anything(tmp_path):
    directory = tmp_path / "config" / "proton-safe-mcp"
    directory.mkdir(mode=0o700, parents=True)
    target = directory / "config.toml"

    assert _read_code(target) == "CONFIG_MISSING"
    assert not target.exists()


def test_a_relative_path_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigurationError) as caught:
        store.read("config.toml")
    assert caught.value.code == "CONFIG_INVALID"


@pytest.mark.posix_only
def test_a_symlinked_configuration_is_refused(managed_config_path, tmp_path):
    real = tmp_path / "elsewhere.toml"
    real.write_text("schema_version = 1\n[bridge]\nuser = 'person@example.com'\n")
    real.chmod(0o600)
    managed_config_path.symlink_to(real)

    # O_NOFOLLOW refuses the link itself, so the target is never opened.
    assert _read_code(managed_config_path) in {"CONFIG_INVALID", "CONFIG_PERMISSIONS"}


@pytest.mark.posix_only
def test_a_world_readable_file_is_refused(write_managed_config, managed_config_path):
    write_managed_config(managed_config_path)
    managed_config_path.chmod(0o644)

    assert _read_code(managed_config_path) == "CONFIG_PERMISSIONS"


@pytest.mark.posix_only
def test_a_world_readable_directory_is_refused(write_managed_config, managed_config_path):
    write_managed_config(managed_config_path)
    managed_config_path.parent.chmod(0o755)
    try:
        assert _read_code(managed_config_path) == "CONFIG_PERMISSIONS"
    finally:
        managed_config_path.parent.chmod(0o700)


def test_a_directory_in_place_of_the_file_is_refused(tmp_path):
    directory = tmp_path / "config" / "proton-safe-mcp"
    directory.mkdir(mode=0o700, parents=True)
    target = directory / "config.toml"
    target.mkdir(mode=0o700)

    assert _read_code(target) == "CONFIG_INVALID"


def test_a_future_schema_version_is_refused_without_rewriting(managed_config_path):
    managed_config_path.write_text(
        "schema_version = 99\n[bridge]\nuser = 'person@example.com'\n", encoding="utf-8"
    )
    managed_config_path.chmod(0o600)
    before = managed_config_path.read_bytes()

    assert _read_code(managed_config_path) == "CONFIG_SCHEMA_UNSUPPORTED"
    assert managed_config_path.read_bytes() == before


@pytest.mark.parametrize(
    "body",
    [
        "schema_version = 1\n[bridge]\nuser = 'person@example.com'\nextra = 1\n",
        "schema_version = 1\n[unknown]\nx = 1\n",
        "schema_version = 1\n",
        "[bridge]\nuser = 'person@example.com'\n",
        "schema_version = 1\n[bridge]\nuser = 'not-an-address'\n",
        "schema_version = 1\n[bridge]\nuser = 'person@example.com'\nimap_port = 0\n",
        "schema_version = 1\n[bridge]\nuser = 'p@example.com'\n[limits]\nunknown = 1\n",
        (
            "schema_version = 1\n[bridge]\nuser = 'p@example.com'\n"
            "[limits]\nmax_body_chars = 9999999\n"
        ),
        "schema_version = 1\n[bridge]\nuser = 'p@example.com'\n[paths]\nstate_dir = 'rel'\n",
        "schema_version = 1\n[bridge]\nuser = 'p@example.com'\nhost = '1.2.3.4'\n",
        "schema_version = 1\n[bridge]\nuser = 'p@example.com'\npassword = 'secret'\n",
        "schema_version = 1\n[bridge]\nimap_port = 1143\n",
        "not toml at all {{{",
    ],
)
def test_the_schema_is_closed(managed_config_path, body):
    managed_config_path.write_text(body, encoding="utf-8")
    managed_config_path.chmod(0o600)

    assert _read_code(managed_config_path) is not None


def test_an_oversized_file_is_refused(managed_config_path):
    managed_config_path.write_text("# " + "x" * store.MAX_CONFIG_BYTES + "\n", encoding="utf-8")
    managed_config_path.chmod(0o600)

    assert _read_code(managed_config_path) == "CONFIG_INVALID"


def test_writing_is_atomic_and_leaves_no_temporary(write_managed_config, managed_config_path):
    write_managed_config(managed_config_path)
    write_managed_config(managed_config_path, user="other@example.com")

    leftovers = [item.name for item in managed_config_path.parent.iterdir()]
    assert leftovers == ["config.toml"]
    assert store.read(managed_config_path).bridge_user == "other@example.com"


@pytest.mark.posix_only
def test_a_failed_write_keeps_the_previous_file_and_removes_its_temporary(
    write_managed_config, managed_config_path, monkeypatch
):
    write_managed_config(managed_config_path)
    original = managed_config_path.read_bytes()

    def explode(*_args, **_kwargs):
        raise OSError("disk full")

    # The atomic replacement is the platform layer's job now, so that is where the
    # failure is injected. What is asserted is unchanged: the previous file survives.
    monkeypatch.setattr(posix_services.os, "replace", explode)
    with pytest.raises(OSError):
        store.write(store.StoredConfiguration(bridge_user="new@example.com"), managed_config_path)

    assert managed_config_path.read_bytes() == original
    assert [item.name for item in managed_config_path.parent.iterdir()] == ["config.toml"]


def test_limits_and_state_dir_survive_a_round_trip(managed_config_path, tmp_path):
    configuration = store.StoredConfiguration(
        bridge_user="person@example.com",
        state_dir=tmp_path / "state",
        limits={"max_body_chars": 50_000},
    )
    store.write(configuration, managed_config_path)
    loaded = store.read(managed_config_path)

    assert loaded.limits == {"max_body_chars": 50_000}
    assert loaded.state_dir == tmp_path / "state"
    # Validating the path must not walk it or move anything under it.
    assert not (tmp_path / "state").exists()


@pytest.mark.posix_only
def test_ensure_private_directory_does_not_touch_its_parents(tmp_path):
    parent = tmp_path / "home-like"
    parent.mkdir(mode=0o755)
    target = parent / "proton-safe-mcp"
    store.ensure_private_directory(target)

    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    assert stat.S_IMODE(parent.stat().st_mode) == 0o755


def test_a_control_character_cannot_be_rendered():
    with pytest.raises(ConfigurationError):
        store.render(store.StoredConfiguration(bridge_user="a\tb@example.com"))


@pytest.mark.posix_only
def test_a_file_owned_by_another_account_is_refused(
    write_managed_config, managed_config_path, monkeypatch
):
    write_managed_config(managed_config_path)
    other_uid = os.getuid() + 1
    monkeypatch.setattr(os, "getuid", lambda: other_uid)

    assert _read_code(managed_config_path) == "CONFIG_PERMISSIONS"

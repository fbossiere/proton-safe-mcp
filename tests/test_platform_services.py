"""The platform seam, and the Windows behaviour that can be proved from anywhere.

Two kinds of test live here.

The first exercises logic that decides something security-relevant and does not need
the operating system to answer: whether an access control list leaves a file open to
another account, whether a launcher may be executed, which credential-store entries a
self-test must clean up. That logic runs here on every platform, because a rule only
checked on the machine where it is hard to reproduce is a rule nobody checks.

The second runs the real Windows file sequencing — atomic replacement, the refusal to
read through a redirection, the identity check that stands in for ``O_NOFOLLOW`` — with
only the Win32 calls replaced. The sequence is the part that can be wrong; the calls
themselves are exercised by the Windows job in CI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path, PureWindowsPath
from typing import ClassVar

import pytest

from proton_safe_mcp.platform_services import PrivacyError, services, use_services
from proton_safe_mcp.platform_services import windows as windows_services
from proton_safe_mcp.platform_services.posix import PosixServices
from proton_safe_mcp.platform_services.winacl import (
    ADMINISTRATORS_SID,
    SYSTEM_SID,
    allowed_sids_for,
    foreign_grants,
    inherits_from_parent,
    normalise_sid,
    parse_rights,
    parse_security_descriptor,
    private_sddl,
    split_sections,
)
from proton_safe_mcp.platform_services.windows import WindowsServices

USER_SID = "S-1-5-21-1004336348-1177238915-682003330-1001"
ALLOWED = allowed_sids_for(USER_SID)


# -- access control lists ---------------------------------------------------------


def test_the_dacl_this_product_writes_grants_nobody_else_and_blocks_inheritance():
    descriptor = f"O:{USER_SID}" + private_sddl(USER_SID, directory=True)

    owner, aces, protected = parse_security_descriptor(descriptor)

    assert owner == USER_SID
    assert protected, "an inheritable parent must not be able to widen this directory"
    assert {ace.sid for ace in aces} == {USER_SID, SYSTEM_SID, ADMINISTRATORS_SID}
    assert foreign_grants(descriptor, allowed_sids=ALLOWED) == []


def test_a_directory_dacl_is_inheritable_and_a_file_dacl_is_not():
    """Files created inside a managed directory must start out private themselves."""
    _, directory_aces, _ = parse_security_descriptor(private_sddl(USER_SID, directory=True))
    _, file_aces, _ = parse_security_descriptor(private_sddl(USER_SID, directory=False))

    assert all("OI" in ace.flags and "CI" in ace.flags for ace in directory_aces)
    assert all(ace.flags == "" for ace in file_aces)


def test_a_dacl_is_never_built_without_a_real_account_sid():
    with pytest.raises(ValueError):
        private_sddl("SY", directory=False)


@pytest.mark.parametrize(
    "account",
    ["WD", "BU", "AU", "IU", "S-1-5-21-1004336348-1177238915-682003330-1002"],
    ids=["everyone", "users", "authenticated", "interactive", "another-account"],
)
def test_an_entry_granting_another_account_is_reported(account):
    descriptor = f"O:{USER_SID}D:P(A;;FA;;;{USER_SID})(A;;FR;;;{account})"

    assert foreign_grants(descriptor, allowed_sids=ALLOWED) == [normalise_sid(account)]


def test_an_inherited_profile_dacl_is_reported_as_not_established():
    """The shape a folder has before this product tightens it: inherited, and shared."""
    descriptor = (
        f"O:{USER_SID}D:AI(A;OICIID;FA;;;SY)(A;OICIID;FA;;;BA)"
        f"(A;OICIID;0x1200a9;;;BU)(A;OICIID;FA;;;{USER_SID})"
    )

    assert inherits_from_parent(descriptor)
    assert foreign_grants(descriptor, allowed_sids=ALLOWED) == ["S-1-5-32-545"]


def test_an_entry_limited_to_harmless_rights_is_not_reported():
    """Reading a name or a timestamp is not reading the file; flagging it would be noise."""
    descriptor = f"O:{USER_SID}D:P(A;;FA;;;{USER_SID})(A;;0x80;;;WD)"

    assert foreign_grants(descriptor, allowed_sids=ALLOWED) == []


def test_a_deny_entry_never_counts_as_a_grant():
    descriptor = f"O:{USER_SID}D:P(D;;FA;;;WD)(A;;FA;;;{USER_SID})"

    assert foreign_grants(descriptor, allowed_sids=ALLOWED) == []


def test_rights_are_read_in_both_spellings_and_an_unknown_one_is_assumed_total():
    assert parse_rights("FA") == 0x001F01FF
    assert parse_rights("0x1f01ff") == 0x001F01FF
    assert parse_rights("FRFW") == 0x00120089 | 0x00120116
    # Guessing low would silently approve an entry this code does not understand.
    assert parse_rights("QQ") == 0xFFFFFFFF
    assert parse_rights("FAX") == 0xFFFFFFFF


def test_an_account_sid_is_never_mistaken_for_the_audit_section():
    """`S-1-5-18` begins with the letter that also introduces the SACL."""
    descriptor = f"O:S-1-5-18G:BAD:P(A;;FA;;;{USER_SID})S:AI(AU;SAFA;FA;;;WD)"

    sections = split_sections(descriptor)

    assert sections["O"] == "S-1-5-18"
    assert sections["G"] == "BA"
    assert sections["D"] == f"P(A;;FA;;;{USER_SID})"
    assert foreign_grants(descriptor, allowed_sids=ALLOWED) == []


def test_a_descriptor_without_a_dacl_is_treated_as_not_established():
    owner, aces, protected = parse_security_descriptor(f"O:{USER_SID}")

    assert (owner, aces, protected) == (USER_SID, [], False)
    assert inherits_from_parent(f"O:{USER_SID}")


# -- what each platform will launch ------------------------------------------------


def test_windows_refuses_the_launcher_scripts_a_package_manager_creates(tmp_path):
    """Driving a `.cmd` would mean quoting user-controlled paths into a command line."""
    platform = WindowsServices()
    real = tmp_path / "codex.exe"
    real.write_bytes(b"")
    for name in ("codex.cmd", "codex.bat", "codex.ps1", "codex"):
        (tmp_path / name).write_bytes(b"")

    assert platform.is_executable_file(real)
    for name in ("codex.cmd", "codex.bat", "codex.ps1", "codex"):
        assert not platform.is_executable_file(tmp_path / name), name


def test_each_platform_names_this_product_executables_its_own_way():
    assert PosixServices().executable_name("proton-safe-mcp") == "proton-safe-mcp"
    assert WindowsServices().executable_name("proton-safe-mcp") == "proton-safe-mcp.exe"


def test_an_absolute_path_is_judged_by_the_platform_it_belongs_to():
    """A Windows CODEX_HOME is absolute for Windows, whichever machine is asking."""
    windows, posix = WindowsServices(), PosixServices()

    assert windows.is_absolute_path(r"C:\Users\somebody\.codex")
    assert not windows.is_absolute_path(r".codex")
    assert posix.is_absolute_path("/home/somebody/.codex")
    assert not posix.is_absolute_path("C:/Users/somebody/.codex")
    assert not windows.is_absolute_path("")


# -- the environment a child process receives --------------------------------------


@pytest.mark.parametrize("platform", [PosixServices(), WindowsServices()], ids=["posix", "windows"])
def test_no_platform_ever_hands_a_proton_variable_to_a_child(platform, monkeypatch):
    monkeypatch.setenv("PROTON_BRIDGE_PASSWORD", "must-not-travel")
    monkeypatch.setenv("PROTON_BRIDGE_USER", "person@example.com")

    inherited = platform.managed_environment()

    assert not [name for name in inherited if name.startswith("PROTON_")]
    with pytest.raises(ValueError):
        platform.managed_environment({"PROTON_BRIDGE_PASSWORD": "smuggled"})


def test_the_windows_child_environment_carries_what_windows_actually_needs(monkeypatch):
    for name in ("SystemRoot", "LOCALAPPDATA", "APPDATA", "TEMP", "USERPROFILE"):
        monkeypatch.setenv(name, f"C:\\fake\\{name}")
    monkeypatch.setenv("CODEX_HOME", r"D:\profiles\codex")

    inherited = WindowsServices().managed_environment()

    # SystemRoot in particular: without it Windows sockets do not initialise.
    assert inherited["SystemRoot"] == "C:\\fake\\SystemRoot"
    # Passed through so the assistant and the client agree on one profile; the adapter
    # reads this variable and never writes it.
    assert inherited["CODEX_HOME"] == r"D:\profiles\codex"


def test_a_windows_child_is_started_without_a_console_window():
    options = WindowsServices().spawn_options()

    assert options["creationflags"] & 0x08000000, "CREATE_NO_WINDOW"
    assert options["creationflags"] & 0x00000200, "CREATE_NEW_PROCESS_GROUP"


# -- the credential store ----------------------------------------------------------


def test_the_windows_self_test_cleans_up_the_compound_entry_too():
    """Credential Manager may hold a second entry when two accounts collide."""
    targets = WindowsServices().keyring_probe_targets("svc-selftest", "probe-abc")

    assert targets == ("svc-selftest", "probe-abc@svc-selftest")


def test_the_windows_backend_is_pinned_to_this_computer_rather_than_roaming():
    """keyring 25.7 defaults to CRED_PERSIST_ENTERPRISE, which asks Windows to roam it."""

    class FakeWinVault:
        persist = "enterprise"

    FakeWinVault.__module__ = "keyring.backends.Windows"
    backend = FakeWinVault()

    WindowsServices().configure_keyring(backend)

    assert backend.persist == "local machine"


def test_a_backend_from_another_module_is_left_alone():
    class SomethingElse:
        persist = "enterprise"

    SomethingElse.__module__ = "keyring.backends.SecretService"
    backend = SomethingElse()

    WindowsServices().configure_keyring(backend)

    assert backend.persist == "enterprise"


def test_a_chained_backend_is_configured_through_its_members():
    class FakeWinVault:
        persist = "enterprise"

    FakeWinVault.__module__ = "keyring.backends.Windows"
    inner = FakeWinVault()

    class Chainer:
        backends: ClassVar[list[object]] = [inner]

    WindowsServices().configure_keyring(Chainer())

    assert inner.persist == "local machine"


def test_each_platform_approves_only_its_own_credential_store():
    assert WindowsServices().approved_keyring_modules == {"keyring.backends.Windows"}
    assert PosixServices().approved_keyring_modules == {"keyring.backends.SecretService"}


# -- Windows private storage, with only the Win32 calls replaced --------------------


@pytest.fixture
def windows_platform(monkeypatch, tmp_path):
    """Run the real Windows file sequencing, with the Win32 calls stubbed.

    What is under test is the order of operations: create exclusively, tighten, replace
    atomically, and refuse anything that changed underneath. The calls that ask Windows
    for a security descriptor are replaced because this machine has none; they are
    exercised for real by the Windows job in CI.
    """
    tightened: list[tuple[Path, bool]] = []
    descriptors: dict[Path, str] = {}
    private = f"O:{USER_SID}" + private_sddl(USER_SID, directory=True)

    def apply(path, *, directory):
        tightened.append((Path(path), directory))
        descriptors[Path(path)] = private

    monkeypatch.setattr(windows_services, "current_user_sid", lambda: USER_SID)
    monkeypatch.setattr(windows_services, "is_elevated", lambda: False)
    monkeypatch.setattr(windows_services, "known_folder", lambda *_a, **_k: tmp_path / "AppData")
    monkeypatch.setattr(windows_services, "apply_private_dacl", apply)
    monkeypatch.setattr(
        windows_services, "describe_security", lambda path: descriptors.get(Path(path), private)
    )
    platform = WindowsServices()
    with use_services(platform):
        platform.tightened = tightened  # type: ignore[attr-defined]
        platform.descriptors = descriptors  # type: ignore[attr-defined]
        yield platform


def test_windows_folders_come_from_the_shell_not_from_a_built_user_path(windows_platform, tmp_path):
    root = tmp_path / "AppData" / "Proton Safe"

    assert windows_platform.config_dir() == root / "config"
    assert windows_platform.state_dir() == root / "state"
    assert windows_platform.data_dir() == root / "data"
    assert windows_platform.programs_dir() == tmp_path / "AppData" / "Programs" / "Proton Safe"


def test_a_private_file_is_tightened_before_it_ever_appears_at_its_final_name(
    windows_platform, tmp_path
):
    """The DACL is set on the temporary file, which then carries it through the rename.

    That order matters: tightening after the rename would leave a moment where the
    configuration exists at its real path with whatever permissions it was created
    with. A file's security descriptor travels with it, so there is no such window.
    """
    target = tmp_path / "config" / "config.toml"

    windows_platform.write_private_file(target, b"first")

    assert target.read_bytes() == b"first"
    assert (target.parent, True) in windows_platform.tightened
    files = [path for path, directory in windows_platform.tightened if not directory]
    assert len(files) == 1
    assert files[0].parent == target.parent and files[0] != target
    # Nothing is left behind by a successful replacement.
    assert [item.name for item in target.parent.iterdir()] == ["config.toml"]


def test_a_failed_replacement_keeps_the_previous_file_and_removes_its_temporary(
    windows_platform, tmp_path, monkeypatch
):
    target = tmp_path / "config" / "config.toml"
    windows_platform.write_private_file(target, b"the one that works")

    def explode(*_args, **_kwargs):
        raise OSError("the file is locked by another process")

    monkeypatch.setattr(windows_services.os, "replace", explode)
    with pytest.raises(OSError):
        windows_platform.write_private_file(target, b"the replacement")

    assert target.read_bytes() == b"the one that works"
    assert [item.name for item in target.parent.iterdir()] == ["config.toml"]


def test_a_file_larger_than_the_bound_is_refused_without_being_read(windows_platform, tmp_path):
    target = tmp_path / "config" / "config.toml"
    windows_platform.write_private_file(target, b"x" * 5000)

    with pytest.raises(PrivacyError) as caught:
        windows_platform.read_private_file(target, max_bytes=1024)

    assert caught.value.code == "CONFIG_INVALID"


def test_a_missing_file_is_reported_as_missing_rather_than_unsafe(windows_platform, tmp_path):
    with pytest.raises(PrivacyError) as caught:
        windows_platform.read_private_file(tmp_path / "absent.toml", max_bytes=1024)

    assert caught.value.code == "CONFIG_MISSING"


def test_a_file_other_accounts_can_open_is_refused(windows_platform, tmp_path):
    target = tmp_path / "config" / "config.toml"
    windows_platform.write_private_file(target, b"private")
    windows_platform.descriptors[target] = f"O:{USER_SID}D:AI(A;;FA;;;{USER_SID})(A;;FR;;;BU)"

    with pytest.raises(PrivacyError) as caught:
        windows_platform.read_private_file(target, max_bytes=1024)

    assert caught.value.code == "CONFIG_PERMISSIONS"


def test_a_shared_directory_is_refused_and_reported_in_windows_terms(windows_platform, tmp_path):
    directory = tmp_path / "state"
    directory.mkdir()
    windows_platform.descriptors[directory] = f"O:{USER_SID}D:AI(A;;FA;;;{USER_SID})(A;;FA;;;WD)"

    state, detail = windows_platform.directory_privacy(directory)

    assert state == "not_private"
    assert "other users" in detail
    with pytest.raises(PrivacyError):
        windows_platform.verify_private_directory(directory)


def test_an_absent_directory_is_missing_rather_than_shared(windows_platform, tmp_path):
    assert windows_platform.directory_privacy(tmp_path / "never-created") == ("missing", "")


def test_an_existing_private_directory_is_not_tightened_again(windows_platform, tmp_path):
    directory = tmp_path / "state"
    windows_platform.ensure_private_directory(directory)
    windows_platform.tightened.clear()

    windows_platform.ensure_private_directory(directory)

    assert windows_platform.tightened == [], "a protected DACL is not rewritten on every call"


def test_creating_a_private_file_refuses_to_write_through_an_existing_one(
    windows_platform, tmp_path
):
    target = tmp_path / "blob.part"
    windows_platform.create_private_file(target, b"first")

    with pytest.raises(FileExistsError):
        windows_platform.create_private_file(target, b"second")

    assert target.read_bytes() == b"first"


def test_appending_reaches_the_same_file_and_nothing_else(windows_platform, tmp_path):
    target = tmp_path / "blob.part"
    windows_platform.create_private_file(target, b"one")

    windows_platform.append_to_private_file(target, b"-two")

    assert target.read_bytes() == b"one-two"


@pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX symlink to stand in")
def test_a_redirected_file_is_refused_rather_than_followed(windows_platform, tmp_path, monkeypatch):
    """Windows has no O_NOFOLLOW, so a reparse point is refused outright.

    A symlink stands in for the junction here; what is under test is that the refusal
    happens before the file is opened, whatever the link is made of.
    """
    real = tmp_path / "somewhere-else.toml"
    real.write_bytes(b"another account's file")
    link = tmp_path / "config.toml"
    link.symlink_to(real)
    monkeypatch.setattr(windows_services, "_is_reparse_point", lambda path: Path(path) == link)

    with pytest.raises(PrivacyError) as caught:
        windows_platform.read_private_file(link, max_bytes=1024)

    assert caught.value.code == "CONFIG_PERMISSIONS"
    with pytest.raises(PrivacyError):
        windows_platform.append_to_private_file(link, b"x")
    assert real.read_bytes() == b"another account's file"


def test_an_elevated_windows_session_is_reported_so_the_setup_can_refuse(
    windows_platform, monkeypatch
):
    monkeypatch.setattr(windows_services, "is_elevated", lambda: True)

    facts = windows_platform.session_facts()

    assert facts.elevated
    assert facts.kind == "Windows"


# -- selection --------------------------------------------------------------------


def test_this_process_resolves_the_services_for_the_system_it_runs_on():
    expected = "windows" if sys.platform == "win32" else "posix"

    assert services().name == expected


def test_the_windows_module_imports_and_refuses_plainly_off_windows():
    """It is developed and type-checked on Linux, so importing it must never fail."""
    if sys.platform == "win32":  # pragma: no cover - exercised by the Windows job
        pytest.skip("this machine has the Windows API")
    from proton_safe_mcp.platform_services.base import UnsupportedPlatformError

    with pytest.raises(UnsupportedPlatformError):
        windows_services.known_folder()


def test_the_managed_state_override_must_be_absolute(tmp_path):
    from proton_safe_mcp.platform_services import resolve_state_directory

    default = tmp_path / "default"

    assert resolve_state_directory("", default) == default
    assert resolve_state_directory("relative/path", default) == default
    assert resolve_state_directory(str(tmp_path / "chosen"), default) == tmp_path / "chosen"


def test_pure_windows_paths_are_used_for_windows_path_questions():
    assert WindowsServices().path_flavour is PureWindowsPath
    assert os.name != "nt" or services().path_flavour is PureWindowsPath


@pytest.mark.parametrize(
    "descriptor",
    [
        "",
        f"O:{USER_SID}",
        f"O:{USER_SID}D:NO_ACCESS_CONTROL",
        f"O:{USER_SID}D:P",
        f"O:{USER_SID}D:P(garbage)",
        f"O:{USER_SID}D:P(A;;FA;;;WD)",
        "O:S-1-5-21-1-2-3-1002" + private_sddl(USER_SID, directory=True),
        f"O:{USER_SID}D:P(XA;;FA;;;{USER_SID};(@User.flag == 1))",
    ],
)
def test_incomplete_or_foreign_descriptors_never_pass_privacy(
    windows_platform, tmp_path, descriptor
):
    windows_platform.descriptors[tmp_path] = descriptor
    assert windows_platform.directory_privacy(tmp_path)[0] == "not_private"
    with pytest.raises(PrivacyError):
        windows_platform.verify_private_directory(tmp_path)


def test_a_protected_shared_directory_is_repaired_before_writing(windows_platform, tmp_path):
    windows_platform.descriptors[tmp_path] = f"O:{USER_SID}D:P(A;OICI;FA;;;WD)"
    windows_platform.ensure_private_directory(tmp_path)
    assert (tmp_path, True) in windows_platform.tightened
    windows_platform.create_private_file(tmp_path / "attachment", b"private contents")
    assert (tmp_path / "attachment", False) in windows_platform.tightened


def test_a_failed_acl_change_prevents_the_first_data_write(windows_platform, tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise PrivacyError("ACL refused", code="CONFIG_PERMISSIONS")

    monkeypatch.setattr(windows_services, "apply_private_dacl", refuse)
    target = tmp_path / "attachment"
    with pytest.raises(PrivacyError):
        windows_platform.create_private_file(target, b"must never be written")
    assert not target.read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL integration")
def test_native_identity_and_private_storage(tmp_path):
    platform = WindowsServices()
    sid = windows_services.current_user_sid()
    assert sid.startswith("S-1-5-")
    assert isinstance(windows_services.is_elevated(), bool)
    target = tmp_path / "private" / "config.toml"
    platform.write_private_file(target, b"native private file")
    assert platform.read_private_file(target, max_bytes=100) == b"native private file"
    assert platform.directory_privacy(target.parent)[0] == "private"
    # A null DACL really means unrestricted access on Windows, not an empty list.
    api = windows_services._require_windows()
    assert api.advapi32.SetNamedSecurityInfoW(str(target.parent), 1, 4, None, None, None, None) == 0
    assert platform.directory_privacy(target.parent)[0] == "not_private"
    platform.ensure_private_directory(target.parent)
    assert platform.directory_privacy(target.parent)[0] == "private"


def test_windows_pipe_buffer_respects_the_budget_before_consumption():
    import subprocess
    import time

    process = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'x' * (8 * 1024 * 1024))"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdout is not None
    reader = windows_services.WindowsLineReader(process.stdout, budget=64)
    try:
        with pytest.raises(ValueError):
            reader.read_line(time.monotonic() + 5)
        assert reader._producer_budget == 65
        assert reader._queue.maxsize == 2
    finally:
        process.terminate()
        process.wait(timeout=5)
        reader.close()
    assert not reader._thread.is_alive()

"""The compiler trust gate must fail before executing an unverified download."""

import runpy
from pathlib import Path

import pytest

FETCH = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "packaging/windows/fetch_innosetup.py")
)


@pytest.mark.parametrize(
    "digest, valid",
    [("a" * 64, True), ("A" * 64, True), ("", False), ("a" * 63, False), ("g" * 64, False)],
)
def test_digest_validation_accepts_both_cases_but_not_missing_or_invalid_values(digest, valid):
    assert FETCH["pinned"]({"sha256": digest}) is valid


def test_an_unpinned_compiler_is_a_failed_check(monkeypatch):
    main = FETCH["main"]
    monkeypatch.setitem(main.__globals__, "read_lock", lambda: {"version": "7.1.0", "sha256": ""})
    assert main(["--check-pin"]) == 1


def test_a_different_download_cannot_be_executed(monkeypatch):
    main = FETCH["main"]
    monkeypatch.setitem(
        main.__globals__,
        "read_lock",
        lambda: {"version": "7.1.0", "sha256": "a" * 64, "size": "6", "url": "unused"},
    )
    monkeypatch.setitem(main.__globals__, "download", lambda _url: b"wrong!")

    def forbidden(*args, **kwargs):
        pytest.fail("the unverified compiler must never run")

    monkeypatch.setattr(main.__globals__["subprocess"], "run", forbidden)
    assert main(["--install"]) == 1


@pytest.mark.parametrize("size", ["", "0", "invalid", "100"])
def test_bad_compiler_sizes_fail_with_a_diagnostic(monkeypatch, capsys, size):
    main = FETCH["main"]
    monkeypatch.setitem(
        main.__globals__,
        "read_lock",
        lambda: {"version": "7.1.0", "sha256": "a" * 64, "size": size, "url": "unused"},
    )
    monkeypatch.setitem(main.__globals__, "download", lambda _url: b"short")
    assert main(["--install"]) == 1
    assert "size" in capsys.readouterr().err

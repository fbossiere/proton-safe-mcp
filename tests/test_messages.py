"""The user-visible text is externalised, complete, and free of private values."""

from __future__ import annotations

import pytest

from proton_safe_mcp.onboarding import messages
from proton_safe_mcp.onboarding.models import Code


def test_every_string_exists_in_every_supported_language():
    assert messages.missing_translations() == []


def test_every_code_the_specification_lists_has_a_message_and_an_action():
    documented = [
        Code.BRIDGE_UNREACHABLE,
        Code.BRIDGE_AUTH_FAILED,
        Code.BRIDGE_TLS_FAILED,
        Code.KEYRING_LOCKED,
        Code.KEYRING_UNAVAILABLE,
        Code.UNSUPPORTED_CLIENT,
        Code.CLIENT_RESTART_REQUIRED,
        Code.CLIENT_ACTION_REQUIRED,
        Code.CONFIG_CONFLICT,
        Code.CONFIG_INVALID,
        Code.CONFIG_PERMISSIONS,
        Code.RUNTIME_START_FAILED,
        Code.INSTALLATION_INCOMPLETE,
    ]
    for code in documented:
        for language in messages.SUPPORTED_LANGUAGES:
            message, action = messages.explain(str(code), language)
            assert message and action, code


def test_an_unknown_code_still_produces_honest_text():
    message, action = messages.explain("SOMETHING_NEW", "fr")

    assert "SOMETHING_NEW" not in message
    assert message and action


@pytest.mark.parametrize("language", messages.SUPPORTED_LANGUAGES)
def test_no_message_promises_that_nothing_leaves_the_computer(language):
    joined = " ".join(
        entry[language] for entry in messages.CATALOGUE.values() if entry.get(language)
    ).lower()

    assert "tout reste sur votre ordinateur" not in joined
    assert "everything stays on your computer" not in joined
    # The cloud caveat is stated instead.
    assert "transmis à son fournisseur" in joined or "sent to its provider" in joined


def test_no_message_contains_an_address_or_a_credential():
    joined = " ".join(
        text for entry in messages.CATALOGUE.values() for text in entry.values()
    ) + " ".join(
        part
        for entry in messages.CODE_MESSAGES.values()
        for pair in entry.values()
        for part in pair
    )

    assert "@proton.me" not in joined
    assert "password=" not in joined.lower()
    assert "sk-" not in joined


def test_official_links_are_fixed_and_https():
    assert set(messages.OFFICIAL_LINKS) == {
        "bridge",
        "bridge_systems",
        "client_mcp",
        "documentation",
    }
    for url in messages.OFFICIAL_LINKS.values():
        assert url.startswith("https://")


@pytest.mark.parametrize(
    ("variables", "expected"),
    [
        ({"LANG": "fr_FR.UTF-8"}, "fr"),
        ({"LANG": "en_GB.UTF-8"}, "en"),
        ({"LC_ALL": "en_US.UTF-8", "LANG": "fr_FR.UTF-8"}, "en"),
        ({"LANG": "de_DE.UTF-8"}, "fr"),
        ({}, "fr"),
    ],
)
def test_the_language_comes_from_the_session_with_french_as_the_default(
    monkeypatch, variables, expected
):
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)

    assert messages.detect_language() == expected


def test_the_bridge_help_text_names_the_right_password():
    text = messages.translate("bridge.password.help", "fr")

    assert "mot de passe IMAP affiché par Bridge" in text
    assert "pas le mot de passe de votre compte Proton" in text
    assert "trousseau" in text

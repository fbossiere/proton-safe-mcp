from __future__ import annotations

import pytest

from proton_safe_mcp.errors import BridgeError, DraftError
from proton_safe_mcp.message_ids import (
    MAX_MESSAGE_ID_CHARS,
    MAX_REFERENCES,
    MAX_REFERENCES_CHARS,
    build_references,
    parse_message_ids,
    validate_message_id,
)


def test_a_bracketed_message_id_round_trips_without_surrounding_whitespace():
    assert validate_message_id("  <abc.123@example.com>\t") == "<abc.123@example.com>"


@pytest.mark.parametrize(
    "value",
    [
        "abc@example.com",
        "<abc@example.com",
        "abc@example.com>",
        "<abc@example.com>\r\nBcc: attacker@example.com",
        "<abc@example.com>\r\nIn-Reply-To: <other@example.com>",
        "<with space@example.com>",
        "<>",
        "<a<b@example.com>",
        "<" + "a" * (MAX_MESSAGE_ID_CHARS - 1) + ">",
        "",
    ],
)
def test_rejects_a_message_id_that_could_continue_into_another_header(value):
    with pytest.raises(DraftError, match="Invalid Message-ID"):
        validate_message_id(value)


def test_rejection_uses_the_caller_s_error_type():
    with pytest.raises(BridgeError):
        validate_message_id("not-an-id", error=BridgeError)


def test_a_non_string_message_id_is_rejected_without_a_type_error():
    with pytest.raises(DraftError, match="Invalid Message-ID"):
        validate_message_id(None)  # type: ignore[arg-type]


def test_references_are_parsed_in_order_and_deduplicated():
    header = "<a@example.com> <b@example.com>\r\n\t<a@example.com> <c@example.com>"
    assert parse_message_ids(header) == (
        "<a@example.com>",
        "<b@example.com>",
        "<c@example.com>",
    )


@pytest.mark.parametrize("header", [None, "", "no identifiers here", "<>", "< >"])
def test_a_header_carrying_no_usable_identifier_yields_nothing(header):
    assert parse_message_ids(header) == ()


def test_a_malformed_entry_is_dropped_instead_of_raising():
    # A received References header is attacker-controlled: it must never fail the read.
    oversized = "<" + "a" * MAX_MESSAGE_ID_CHARS + ">"
    header = f"{oversized} <good@example.com> <bad id@example.com>"

    assert parse_message_ids(header) == ("<good@example.com>",)


def test_the_chain_is_the_parent_s_references_followed_by_the_parent():
    chain = build_references(("<root@example.com>", "<mid@example.com>"), "<parent@example.com>")

    assert chain == ("<root@example.com>", "<mid@example.com>", "<parent@example.com>")


def test_a_parent_already_present_in_the_chain_is_not_repeated():
    chain = build_references(("<root@example.com>", "<parent@example.com>"), "<parent@example.com>")

    assert chain == ("<root@example.com>", "<parent@example.com>")


def test_an_overlong_chain_keeps_the_thread_root_and_the_parent():
    references = tuple(f"<{index}@example.com>" for index in range(MAX_REFERENCES + 10))

    chain = build_references(references, "<parent@example.com>")

    assert len(chain) == MAX_REFERENCES
    assert chain[0] == "<0@example.com>"
    assert chain[-1] == "<parent@example.com>"


def test_a_chain_of_long_identifiers_is_bounded_by_rendered_length():
    references = tuple(f"<{'a' * 200}{index}@example.com>" for index in range(MAX_REFERENCES))

    chain = build_references(references, "<parent@example.com>")

    assert len(" ".join(chain)) <= MAX_REFERENCES_CHARS
    assert len(chain) < MAX_REFERENCES
    assert chain[0] == references[0]
    assert chain[-1] == "<parent@example.com>"


def test_the_root_and_parent_pair_always_fits_the_length_bound():
    # build_references trims no further than this pair, which is only sound while two
    # validated Message-IDs and their separator stay inside the rendered-length bound.
    assert 2 * MAX_MESSAGE_ID_CHARS + 1 <= MAX_REFERENCES_CHARS

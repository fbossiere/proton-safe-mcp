from __future__ import annotations

import pytest

from proton_safe_mcp import cli
from proton_safe_mcp.drafts import DraftApprovalStore


@pytest.fixture
def env(monkeypatch, settings):
    monkeypatch.setenv("PROTON_BRIDGE_USER", settings.bridge_user)
    monkeypatch.setenv("PROTON_MCP_STATE_DIR", str(settings.state_dir))
    return settings


def _prepare_draft(settings) -> str:
    store = DraftApprovalStore(settings)
    result = store.prepare(
        to=["recipient@example.com"],
        cc=[],
        bcc=[],
        subject="CLI test",
        body_text="Hello",
        attachment_tokens=[],
        attachments=[],
    )
    return result["draft_id"]


def test_approve_requires_exact_interactive_confirmation(env, monkeypatch, capsys):
    draft_id = _prepare_draft(env)
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    assert cli.main(["approve", draft_id]) == 1
    assert "Approval cancelled" in capsys.readouterr().err
    assert not (env.approvals_dir / f"{draft_id}.approved.json").exists()


def test_approve_happy_path_writes_marker(env, monkeypatch, capsys):
    draft_id = _prepare_draft(env)
    monkeypatch.setattr("builtins.input", lambda _prompt: f"APPROVE {draft_id[-8:]}")
    assert cli.main(["approve", draft_id]) == 0
    assert "Approved" in capsys.readouterr().out
    assert (env.approvals_dir / f"{draft_id}.approved.json").is_file()


def test_reject_writes_rejection_marker(env, capsys):
    draft_id = _prepare_draft(env)
    assert cli.main(["reject", draft_id]) == 0
    assert (env.approvals_dir / f"{draft_id}.rejected").is_file()


def test_show_prints_summary_without_side_effects(env, capsys):
    draft_id = _prepare_draft(env)
    assert cli.main(["show", draft_id]) == 0
    output = capsys.readouterr().out
    assert "recipient@example.com" in output
    assert "CLI test" in output
    assert not (env.approvals_dir / f"{draft_id}.approved.json").exists()


def test_unknown_draft_id_is_reported_as_error(env, capsys):
    assert cli.main(["show", "0" * 32]) == 1
    assert "Error:" in capsys.readouterr().err


def test_show_rejects_path_like_draft_id(env, capsys):
    assert cli.main(["show", "../outside"]) == 1
    assert "Invalid draft_id" in capsys.readouterr().err

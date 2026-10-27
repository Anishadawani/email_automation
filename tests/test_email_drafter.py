import csv
import json
from types import SimpleNamespace

import pytest

import email_drafter as ed

GOOD = json.dumps({"subject": "Interview invitation", "body": "Hi Asha, please share your availability."})


def fake_client(text=GOOD):
    return SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)])))


CAND = {"name": "Asha", "email": "asha@example.com", "recommendation": "shortlist", "summary": "Strong Python"}


def test_draft_email_ok():
    assert ed.draft_email(CAND, "AI Intern", "Virtuous", client=fake_client())["subject"] == "Interview invitation"


def test_draft_email_bad_recommendation():
    with pytest.raises(ed.DraftError):
        ed.draft_email(dict(CAND, recommendation="hire"), "x", "y", client=fake_client())


def test_draft_email_bad_json():
    with pytest.raises(ed.DraftError):
        ed.draft_email(CAND, "x", "y", client=fake_client("not json"))


def test_read_candidates_requires_columns(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("name,email\nA,a@x.com\n")
    with pytest.raises(ed.DraftError):
        ed.read_candidates(str(p))


def test_dry_run_does_not_send(tmp_path):
    sent = []
    out = tmp_path / "d.csv"
    res = ed.process([CAND], "AI Intern", "Virtuous", str(out), send=False,
                     client=fake_client(), sender=lambda *a: sent.append(a))
    assert sent == [] and res[0]["status"] == "drafted"
    assert list(csv.DictReader(open(out)))[0]["subject"] == "Interview invitation"


def test_send_mode_calls_sender(tmp_path):
    sent = []
    res = ed.process([CAND], "AI Intern", "Virtuous", str(tmp_path / "d.csv"), send=True,
                     client=fake_client(), sender=lambda *a: sent.append(a))
    assert len(sent) == 1 and res[0]["status"] == "sent"


def test_batch_continues_after_error(tmp_path):
    bad = dict(CAND, name="Bad", recommendation="???")
    res = ed.process([bad, CAND], "AI Intern", "Virtuous", str(tmp_path / "d.csv"), client=fake_client())
    assert res[0]["status"].startswith("error") and res[1]["status"] == "drafted"


def test_invalid_email_rejected():
    with pytest.raises(ed.DraftError):
        ed.draft_email(dict(CAND, email="not-an-email"), "x", "y", client=fake_client())


def test_header_injection_blocked_in_subject():
    evil = json.dumps({"subject": "Hi\r\nBcc: spy@x.com", "body": "ok"})
    out = ed.draft_email(CAND, "x", "y", client=fake_client(evil))
    assert "\n" not in out["subject"] and "\r" not in out["subject"]


def test_empty_body_rejected():
    with pytest.raises(ed.DraftError):
        ed.draft_email(CAND, "x", "y", client=fake_client(json.dumps({"subject": "s", "body": " "})))


def test_markdown_fenced_json_parsed():
    fenced = "```json\n" + GOOD + "\n```"
    assert ed.draft_email(CAND, "x", "y", client=fake_client(fenced))["subject"] == "Interview invitation"


def test_duplicate_email_flagged(tmp_path):
    res = ed.process([CAND, dict(CAND)], "x", "y", str(tmp_path / "d.csv"), client=fake_client())
    assert res[0]["status"] == "drafted" and "Duplicate" in res[1]["status"]


def test_send_approved_only_sends_approved_and_is_idempotent(tmp_path):
    path = tmp_path / "d.csv"
    rows = [
        dict(name="A", email="a@x.com", recommendation="shortlist", subject="s", body="b", status="drafted", approved="yes"),
        dict(name="B", email="b@x.com", recommendation="reject", subject="s", body="b", status="drafted", approved=""),
        dict(name="C", email="c@x.com", recommendation="maybe", subject="s", body="b", status="sent", approved="yes"),
    ]
    ed.write_rows(rows, str(path))
    sent = []
    c = ed.send_approved(str(path), sender=lambda *a: sent.append(a[0]), delay=0)
    assert sent == ["a@x.com"] and c == {"sent": 1, "skipped": 2, "failed": 0}
    ed.send_approved(str(path), sender=lambda *a: sent.append(a[0]), delay=0)
    assert sent == ["a@x.com"]  # rerun does not resend


def test_send_failure_recorded_not_fatal(tmp_path):
    path = tmp_path / "d.csv"
    ed.write_rows([dict(name="A", email="a@x.com", recommendation="reject", subject="s", body="b",
                        status="drafted", approved="yes")], str(path))
    def boom(*a): raise RuntimeError("smtp down")
    c = ed.send_approved(str(path), sender=boom, delay=0)
    assert c["failed"] == 1
    assert "smtp down" in list(csv.DictReader(open(path)))[0]["status"]


def fake_gemini(text=GOOD):
    return SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text=text)))


def test_gemini_client_path(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert ed._provider() == "gemini"
    out = ed.draft_email(CAND, "AI Intern", "Virtuous", client=fake_gemini())
    assert out["subject"] == "Interview invitation"


def test_gemini_bad_output_is_draft_error():
    with pytest.raises(ed.DraftError):
        ed.draft_email(CAND, "x", "y", client=fake_gemini("sorry, cannot"))


def test_provider_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    assert ed._provider() == "claude"

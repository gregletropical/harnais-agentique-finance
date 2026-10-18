"""Le bail informe qu'une autre session tient le hub, une seule fois, sans jamais bloquer."""
import json
import time

import bail_note

HUB = "---\ntype: projet-chantier\nstatus: active\n---\n# Hub\n"


def preparer(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    d = tmp_path / ".git" / "agent-sessions"
    d.mkdir(parents=True)
    maintenant = time.time()
    for sid, cid, label in (("aaaa1111", "claude-A", "poste-1"), ("bbbb3333", "claude-B", "poste-2")):
        (d / f"{sid}.json").write_text(json.dumps({
            "id": sid, "label": label, "started": maintenant, "last_seen": maintenant,
            "claude_session_id": cid}), encoding="utf-8")
    (tmp_path / "Hub.md").write_text(HUB, encoding="utf-8")
    return d


def edition(cid):
    return {"session_id": cid, "tool_name": "Edit", "tool_input": {"file_path": "Hub.md"}}


def test_bail_pose_puis_avertissement_unique(tmp_path, monkeypatch):
    d = preparer(tmp_path, monkeypatch)
    assert bail_note.traiter(edition("claude-A")) is None          # A pose son bail
    assert "Hub.md" in json.loads((d / "aaaa1111.json").read_text())["baux"]
    msg = bail_note.traiter(edition("claude-B"))                    # B est averti
    assert msg and "aaaa1111" in msg and "rien n'est bloqué" in msg
    assert bail_note.traiter(edition("claude-B")) is None          # une seule fois


def test_note_qui_n_est_pas_un_hub_ignoree(tmp_path, monkeypatch):
    preparer(tmp_path, monkeypatch)
    (tmp_path / "Hub.md").write_text("---\ntype: moc\n---\n", encoding="utf-8")
    assert bail_note.traiter(edition("claude-A")) is None

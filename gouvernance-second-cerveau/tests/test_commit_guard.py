"""Le garde-fou de commit refuse là où plusieurs sessions se marcheraient dessus.

Chaque test monte un vrai dépôt jetable : un dépôt nu joue le serveur, deux
clones jouent le poste (plusieurs sessions) et un autre écrivain (l'amont).
"""
import shutil
import subprocess
from pathlib import Path

import pytest

import commit_guard as cg

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git requis")


def g(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def cloner(remote: Path, dest: Path) -> Path:
    subprocess.run(["git", "clone", "-q", str(remote), str(dest)], check=True, capture_output=True)
    g(dest, "config", "user.name", "responsable")
    g(dest, "config", "user.email", "responsable@exemple.invalid")
    return dest


@pytest.fixture
def depots(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENT_SESSION_ID", raising=False)
    remote = tmp_path / "serveur.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    poste = cloner(remote, tmp_path / "poste")
    for nom in ("hub.md", "autre.md"):
        (poste / nom).write_text(f"# {nom}\n", encoding="utf-8")
    g(poste, "add", "hub.md", "autre.md")
    g(poste, "commit", "-q", "-m", "init")
    g(poste, "push", "-q", "-u", "origin", "main")
    amont = cloner(remote, tmp_path / "amont")
    return poste, amont, remote


def guard(depot: Path, *args: str) -> int:
    return cg.main(argv=["--repo", str(depot), *args])


def enregistrer(depot: Path, label: str) -> str:
    return cg.enregistrer(depot, label)


def test_all_refuse_des_deux_sessions(depots):
    poste, _, _ = depots
    sid = enregistrer(poste, "session-1")
    enregistrer(poste, "session-2")
    (poste / "hub.md").write_text("# modifié\n", encoding="utf-8")
    assert guard(poste, "--commit", "--all", "--id", sid, "-m", "tout") == 2
    assert g(poste, "log", "--oneline").count("\n") == 0  # aucun commit de plus


def test_index_deja_charge_par_une_autre_session(depots):
    poste, _, _ = depots
    sid = enregistrer(poste, "session-1")
    (poste / "autre.md").write_text("# travail de l'autre session\n", encoding="utf-8")
    g(poste, "add", "autre.md")  # stagé par une autre session
    (poste / "hub.md").write_text("# mon travail\n", encoding="utf-8")
    assert guard(poste, "--commit", "--id", sid, "-m", "mon lot", "--", "hub.md") == 2


def test_commit_par_chemins_avec_trailer_et_residu_intact(depots, capsys):
    poste, _, _ = depots
    sid = enregistrer(poste, "session-1")
    enregistrer(poste, "session-2")
    (poste / "hub.md").write_text("# mon travail\n", encoding="utf-8")
    (poste / "autre.md").write_text("# travail de l'autre session\n", encoding="utf-8")
    assert guard(poste, "--commit", "--id", sid, "-m", "mon lot", "--", "hub.md") == 0
    assert f"Session: {sid} (session-1)" in g(poste, "log", "-1", "--format=%B")
    assert "autre.md" in g(poste, "status", "--porcelain")      # résidu non emporté
    assert "NON commite" in capsys.readouterr().out             # et affiché


def test_refus_de_pousser_si_l_amont_a_touche_le_lot(depots):
    poste, amont, remote = depots
    (amont / "hub.md").write_text("# version de l'amont\n", encoding="utf-8")
    g(amont, "commit", "-q", "-am", "amont")
    g(amont, "push", "-q")
    sid = enregistrer(poste, "session-1")
    (poste / "hub.md").write_text("# version du poste\n", encoding="utf-8")
    serveur_avant = g(remote, "rev-parse", "main")
    assert guard(poste, "--commit", "--push", "--id", sid, "-m", "lot", "--", "hub.md") == 2
    assert g(remote, "rev-parse", "main") == serveur_avant        # rien n'est poussé
    assert g(poste, "log", "-1", "--format=%s") == "lot"          # commit local fait


def test_rebase_a_part_et_push_si_l_amont_touche_autre_chose(depots):
    poste, amont, remote = depots
    (amont / "autre.md").write_text("# l'amont écrit ailleurs\n", encoding="utf-8")
    g(amont, "commit", "-q", "-am", "amont")
    g(amont, "push", "-q")
    sid = enregistrer(poste, "session-1")
    (poste / "hub.md").write_text("# version du poste\n", encoding="utf-8")
    assert guard(poste, "--commit", "--push", "--id", sid, "-m", "lot", "--", "hub.md") == 0
    assert g(remote, "log", "-1", "--format=%s", "main") == "lot"
    assert g(remote, "log", "--format=%s", "main").splitlines()[1] == "amont"

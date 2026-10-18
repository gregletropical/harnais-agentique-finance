"""Le hook refuse le staging aveugle, et seulement lui."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import block_git_add_all as hook

HOOK = Path(__file__).resolve().parent.parent / "controles" / "hooks" / "block_git_add_all.py"


@pytest.mark.parametrize("commande", [
    "git add -A",
    "git add --all",
    "git add .",
    "git add -- .",
    "cd depot && git add -A && git commit -m x",
    "git -C depot add -A",
    "git -c core.quotepath=false add .",
    "git commit -a -m 'x'",
    "git commit -am 'x'",
    "git commit -sa -m 'x'",
    "git commit --all -m x",
    "echo ok; git add -A",
    "git status | cat\ngit add -A",
])
def test_commandes_bloquees(commande):
    assert hook.est_bloquee(commande) is not None


@pytest.mark.parametrize("commande", [
    "git add notes/a.md notes/b.md",
    "git add ./notes/a.md",
    "git commit -m 'message'",
    "git commit --amend --no-edit",
    "git status",
    "echo 'git add -A'",  # cité dans une chaîne : un seul token, pas un appel git
    "python controles/vault_commit.py --commit -m x -- a.md",
])
def test_commandes_autorisees(commande):
    assert hook.est_bloquee(commande) is None


def test_heredoc_qui_cite_la_commande_passe():
    commande = "git commit -F - <<'MSG'\nPourquoi `git add -A` est dangereux\nMSG"
    assert hook.est_bloquee(commande) is None


def test_vraie_commande_apres_le_heredoc_reste_bloquee():
    commande = "git commit -F - <<'MSG'\nmessage\nMSG\ngit add -A"
    assert hook.est_bloquee(commande) is not None


def lancer(commande: str) -> str:
    entree = json.dumps({"tool_name": "Bash", "tool_input": {"command": commande}})
    return subprocess.run([sys.executable, str(HOOK)], input=entree, text=True,
                          capture_output=True, check=True).stdout


def test_sortie_json_deny():
    sortie = json.loads(lancer("git add -A"))
    assert sortie["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_silence_si_commande_saine():
    assert lancer("git add a.md") == ""

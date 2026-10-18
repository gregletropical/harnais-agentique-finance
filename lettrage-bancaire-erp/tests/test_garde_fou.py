"""Tests du garde-fou de pré-vol (hook PreToolUse) : détection et validité d'un pré-rapport."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from controles.garde_fou_prevol import evaluer_pre_rapport, motif_detecte, vise_une_ecriture_erp

SCRIPT = Path(__file__).resolve().parents[1] / "controles" / "garde_fou_prevol.py"
T0 = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)


def rapport(genere=T0, go=T0 + timedelta(minutes=20), citation="GO pour l'écart de règlement"):
    lignes = [f"Horodatage pré-vol : {genere.isoformat()}", "## 8. Validation"]
    if citation is not None:
        lignes.append(f"GO donné en session le {go.isoformat()} : « {citation} »")
    return "\n".join(lignes)


def test_detection_des_ecritures():
    assert vise_une_ecriture_erp("python3 -c 'm.action_post([1])'")
    assert vise_une_ecriture_erp('c.call("account.move", "write", [1], vals={"ref": "x"})')
    assert vise_une_ecriture_erp('client.execute_kw("account.move.line", "reconcile", [ids])')
    assert vise_une_ecriture_erp("open('f.txt').write('x')") is None      # write sans contexte ERP
    assert vise_une_ecriture_erp("git status") is None
    # Un champ cité dans une liste de lecture n'est pas une écriture.
    assert vise_une_ecriture_erp('c.call("account.account", "search_read", fields=["reconcile"])') is None


def test_ecriture_cachee_dans_un_script_invoque(tmp_path):
    s = tmp_path / "x.py"
    s.write_text("from odoo_client import c\nc.call('account.move', 'action_post', [1])\n", encoding="utf-8")
    assert "x.py" in motif_detecte(f"python3 {s}")


def test_pre_rapport_valide():
    ok, diag = evaluer_pre_rapport(rapport(), T0 + timedelta(hours=1))
    assert ok and "GO pour l'écart" in diag


def test_refus_sans_go_ou_gabarit_non_rempli():
    assert not evaluer_pre_rapport(rapport(citation=None), T0 + timedelta(hours=1))[0]
    gabarit = "Horodatage pré-vol : 2026-10-16T09:00:00+00:00\nGO donné en session le <AAAA-MM-JJTHH:MM> : « <citation> »"
    assert not evaluer_pre_rapport(gabarit, T0 + timedelta(hours=1))[0]


def test_refus_perime_futur_ou_go_anterieur():
    assert not evaluer_pre_rapport(rapport(), T0 + timedelta(hours=48))[0]
    assert not evaluer_pre_rapport(rapport(), T0 - timedelta(hours=1))[0]
    assert not evaluer_pre_rapport(rapport(go=T0 - timedelta(minutes=5)), T0 + timedelta(hours=1))[0]
    sans_heure = "Horodatage pré-vol : 2026-10-16\nGO donné en session le 2026-10-16T09:20+00:00 : « GO »"
    assert not evaluer_pre_rapport(sans_heure, T0 + timedelta(hours=1))[0]


def _hook(commande, dossier):
    env = {**os.environ, "PREVOL_DIR": str(dossier)}
    r = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps({"tool_name": "Bash", "tool_input":
                       {"command": commande}}), capture_output=True, text=True, env=env, check=True)
    return r.stdout.strip()


def test_hook_refuse_puis_laisse_passer(tmp_path):
    cmd = "python3 -c 'c.call(\"account.move\", \"action_post\", [1])'"
    sortie = _hook(cmd, tmp_path)
    assert json.loads(sortie)["hookSpecificOutput"]["permissionDecision"] == "deny"
    maintenant = datetime.now().astimezone()
    (tmp_path / "prevol_ok.md").write_text(rapport(maintenant - timedelta(minutes=30), maintenant - timedelta(minutes=5)),
                                           encoding="utf-8")
    assert _hook(cmd, tmp_path) == ""
    assert _hook("git status", tmp_path) == ""

#!/usr/bin/env python3
"""
garde_fou_prevol.py — Hook `PreToolUse` (outil Bash) du harnais Claude Code : refuse une
commande qui ressemble à une écriture dans l'ERP quand aucun pré-rapport de pré-vol récent
ne porte un GO consigné.

Contrat du harnais : JSON sur l'entrée standard, JSON `hookSpecificOutput` sur la sortie
standard, code de sortie 0 dans tous les cas (le refus passe par
`permissionDecision: deny`, jamais par un code non nul).

Activation (fichier `.claude/settings.json` du dépôt où l'agent travaille) :

    {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
      "command": "python3 \\"$CLAUDE_PROJECT_DIR/controles/garde_fou_prevol.py\\"", "timeout": 10}]}]}}

Les pré-rapports sont cherchés dans le dossier `PREVOL_DIR` (variable d'environnement,
défaut : `prevol/` à la racine de ce dossier), fichiers `prevol_*.md`.

===========================================================================
CE QUE CE GARDE-FOU NE COUVRE PAS — à lire avant de lui faire confiance
===========================================================================

1. Il ne voit que la ligne de commande Bash, et un seul niveau de script `.py` invoqué
   (`python3 script.py` : le contenu du script est lu). Un module importé par ce script,
   un notebook, un outil MCP ou un REPL interactif ne sont PAS couverts.
2. La détection est un motif de texte, pas une analyse sémantique. Les méthodes génériques
   (`write(`, `create(`, `unlink(`) ne comptent que couplées à un marqueur de contexte ERP,
   sinon tout `f.write(...)` déclencherait une fausse alerte. Une méthode passée en variable
   passe inaperçue.
3. Il ne vérifie PAS que le pré-rapport porte sur LA MÊME opération (société, tiers,
   montant) : un pré-rapport valide sur un autre sujet, dans la fenêtre de fraîcheur, suffit.
4. Il ne bloque rien côté ERP : c'est un filet local, propre à ce harnais. Sous un autre
   harnais ou un autre modèle, il n'existe plus — d'où la cible de long terme : porter le
   contrôle dans le client ERP lui-même, qui connaît la méthode exacte appelée.

Conséquence : il rend l'oubli du pré-vol moins probable, pas impossible. La garantie reste
la validation humaine explicite (porte 8).

La fraîcheur se juge sur le CONTENU (ligne `Horodatage pré-vol : <ISO 8601>`), jamais sur
la date du fichier, qu'un clone, un checkout ou un `touch` remettent à maintenant.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
MAX_AGE_HEURES = float(os.environ.get("PREVOL_MAX_AGE_HOURS", "24"))
TOLERANCE_FUTUR_S = 300

# Méthodes d'écriture assez spécifiques à Odoo pour être détectées seules.
METHODES_SANS_AMBIGUITE = re.compile(
    r"\baction_post\b|\bbutton_draft\b|\breconcile\s*\(|\baction_create_invoice\b|\bmessage_post\b|"
    r"\bset_line_bank_statement_line\b|\bset_account_bank_statement_line\b|"
    r"\bremove_move_reconcile\b|\baction_undo_reconciliation\b"
)
# Méthodes génériques : ne comptent que couplées à un marqueur de contexte ERP. Formes :
# appel direct, nom de méthode passé en chaîne, nom passé en position de méthode d'un appel
# client (« call(modele, "reconcile", …) »), arguments nommés d'écriture (`vals=`).
METHODES_GENERIQUES = re.compile(
    r"\bwrite\s*\(|\bcreate\s*\(|\bunlink\s*\(|['\"](write|create|unlink)['\"]|"
    r"\b(?:call|execute_kw|execute)\s*\(\s*(?:[^,()\[\]{}=]+,\s*){1,4}"
    r"['\"](?:copy|reconcile|action_\w+|button_\w+)['\"]|"
    r"[(,]\s*vals(?:_list)?\s*=(?!=)"
)
MARQUEUR_ERP = re.compile(
    r"\bodoo\b|xmlrpc|execute_kw|account\.move|account\.bank|res\.partner|account\.account|"
    r"account\.journal|OdooClient|ODOO_API_KEY|/json/2\b",
    re.IGNORECASE,
)

HORODATAGE = re.compile(r"^[ \t>*_]*Horodatage pr[ée]-vol[ \t*_]*:[ \t*_`]*([^\s`*]+)", re.IGNORECASE | re.MULTILINE)
# GO consigné par l'agent : « GO donné en session le <ISO 8601> : « <citation> » ».
GO_CONSIGNE = re.compile(r"^[ \t>*_-]*GO donn[ée] en session le\s+(\S+)\s*:\s*«\s*([^»]*?)\s*»",
                         re.IGNORECASE | re.MULTILINE)


def vise_une_ecriture_erp(texte: str) -> str | None:
    """Motif détecté dans une commande ou un script, ou None."""
    m = METHODES_SANS_AMBIGUITE.search(texte)
    if m:
        return m.group(0)
    m2 = METHODES_GENERIQUES.search(texte)
    if m2 and MARQUEUR_ERP.search(texte):
        return m2.group(0) + " (contexte ERP détecté)"
    return None


def scripts_invoques(commande: str, base: Path = RACINE) -> list[Path]:
    """Scripts `.py` lancés par la commande (`python3 x.py …`). Best-effort, un niveau."""
    try:
        jetons = shlex.split(commande, posix=True)
    except ValueError:
        return []
    res = []
    for i, tok in enumerate(jetons):
        if re.fullmatch(r"python3?(\.\d+)?", tok) and i + 1 < len(jetons) and jetons[i + 1].endswith(".py"):
            p = Path(jetons[i + 1])
            res.append(p if p.is_absolute() else base / p)
    return res


def motif_detecte(commande: str) -> str | None:
    motif = vise_une_ecriture_erp(commande)
    if motif:
        return motif
    for script in scripts_invoques(commande):
        try:
            motif = vise_une_ecriture_erp(script.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if motif:
            return f"{motif} (dans {script.name})"
    return None


def _horodatage(texte: str) -> datetime | None:
    """ISO 8601 AVEC heure -> datetime avec fuseau. Une date seule ne suffit pas."""
    if not re.search(r"\d{2}:\d{2}", texte):
        return None
    try:
        d = datetime.fromisoformat(texte.strip())
    except ValueError:
        return None
    return d if d.tzinfo else d.astimezone()


def evaluer_pre_rapport(contenu: str, maintenant: datetime | None = None) -> tuple[bool, str]:
    """Juge UN pré-rapport sur son contenu. Première règle qui échoue = refus :
      1. exactement une ligne `Horodatage pré-vol` lisible, avec heure ;
      2. ni dans le futur, ni plus vieille que MAX_AGE_HEURES ;
      3. un GO consigné avec une citation non vide (pas le gabarit `<…>`) ;
      4. le GO est daté, avec heure, ni dans le futur ni antérieur à la génération."""
    maintenant = maintenant or datetime.now().astimezone()
    horos = HORODATAGE.findall(contenu)
    if len(horos) != 1:
        return False, f"{len(horos)} ligne(s) `Horodatage pré-vol` lisible(s), une seule attendue"
    genere = _horodatage(horos[0])
    if genere is None:
        return False, f"horodatage illisible ou sans heure ({horos[0]!r})"
    age_s = (maintenant - genere).total_seconds()
    if age_s < -TOLERANCE_FUTUR_S:
        return False, f"horodatage dans le futur ({genere.isoformat()})"
    if age_s > MAX_AGE_HEURES * 3600:
        return False, f"généré il y a {age_s / 3600:.0f} h, au-delà du seuil de {MAX_AGE_HEURES:.0f} h"

    gos = [(d, c) for d, c in GO_CONSIGNE.findall(contenu) if c and "<" not in c and "<" not in d]
    if not gos:
        return False, "aucun GO consigné avec citation (porte 8 non franchie)"
    date_go, citation = gos[-1]
    go = _horodatage(date_go)
    if go is None:
        return False, f"GO consigné sans date et heure lisibles ({date_go!r})"
    if (maintenant - go).total_seconds() < -TOLERANCE_FUTUR_S:
        return False, f"GO daté dans le futur ({go.isoformat()})"
    if go < genere:
        return False, f"GO ({go.isoformat()}) antérieur à la génération ({genere.isoformat()})"
    return True, f"généré le {genere.isoformat()}, GO du {go.isoformat()} : « {citation} »"


def pre_rapport_valide(dossier: Path, maintenant: datetime | None = None) -> tuple[bool, str]:
    if not dossier.exists():
        return False, f"dossier des pré-rapports absent ({dossier.name}/)"
    refus = []
    for f in sorted(dossier.glob("prevol_*.md")):
        ok, diag = evaluer_pre_rapport(f.read_text(encoding="utf-8", errors="ignore"), maintenant)
        if ok:
            return True, f"{f.name} — {diag}"
        refus.append(f"{f.name} : {diag}")
    return False, ("aucun pré-rapport valide — " + " ; ".join(refus[-5:])) if refus else "aucun pré-rapport"


def main() -> None:
    try:
        commande = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except Exception:
        return  # charge illisible : ne pas bloquer
    motif = motif_detecte(commande) if commande else None
    if not motif:
        return
    ok, diag = pre_rapport_valide(Path(os.environ.get("PREVOL_DIR", RACINE / "prevol")))
    if ok:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"ALERTE PRÉ-VOL : écriture ERP possible ({motif}), mais {diag}. Dérouler le protocole "
            "instructions/protocole-prevol.md, générer le pré-rapport (controles/prevol.py), obtenir le GO "
            "explicite de l'utilisateur et le consigner avec sa citation avant de relancer. Filet de "
            "rattrapage, pas une garantie : en cas de faux positif, relancer après revue humaine."),
    }}, ensure_ascii=False))


if __name__ == "__main__":
    main()

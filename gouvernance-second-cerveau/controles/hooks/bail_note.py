#!/usr/bin/env python3
"""
bail_note.py — Hook PreToolUse (Edit|Write|MultiEdit) de Claude Code : bail par note, INFORMATION SEULE.

Le motif de collision dominant mesuré sur le référentiel d'origine : un hub de chantier client (note
`type: projet-chantier`, porteuse de lignes de tâches) modifié par deux sessions le même jour. La fusion
`merge=union` ne peut pas le couvrir (des lignes sont modifiées, pas ajoutées), et le refus de
`commit_guard.py` arrive au commit, après le travail fait en double. Le bail dit, AU MOMENT DE
L'ÉDITION, qu'une autre session tient déjà ce hub.

Ce n'est pas un verrou : jamais de `deny`. Un verrou exclusif transforme une collision rare en blocage
fréquent et suppose que chacun libère proprement ce qu'il a pris — hypothèse démentie dès le premier jour
par les « marqueurs fantômes » des sessions fermées sans leur procédure de fin.

À chaque Edit/Write d'une note `type: projet-chantier` du dépôt :
  1. le hook pose le bail `chemin → {depuis, dernier}` dans le champ `baux` du marqueur JSON de la
     session courante (`.git/agent-sessions/<id>.json`, registre tenu par `commit_guard.py`) — les baux
     vivent et meurent avec le marqueur, sans code de nettoyage à part ;
  2. si une AUTRE session active tient un bail sur le même fichier, il renvoie un avertissement non
     bloquant (`systemMessage` pour l'humain, `additionalContext` pour l'agent) — une seule fois par
     couple (note, autre session), pour ne pas devenir un bruit qu'on cesse de lire.

Identification de la session : le hook reçoit le `session_id` de Claude Code, pas l'identifiant court du
registre. Le pont est la variable `CLAUDE_CODE_SESSION_ID`, exportée par Claude Code à ses commandes Bash :
`commit_guard.py --register` la recopie dans le marqueur sous `claude_session_id`, et le hook retrouve sa
session par ce champ. Limites assumées : une session non enregistrée ne pose pas de bail (mais reçoit
l'avertissement) ; un harnais sans mécanisme de hook (OpenCode) n'en pose pas.

Le hook ne rafraîchit PAS `last_seen` : protéger une session inactive bloquerait les autres pour rien.
En cas de doute (entrée illisible, fichier hors dépôt, registre absent) : silence, exit 0.

Test à vide :
  echo '{"session_id":"x","tool_name":"Edit","tool_input":{"file_path":"hub.md"}}' \
      | python controles/hooks/bail_note.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

TTL_SECONDES = 12 * 3600          # repli si commit_guard.py n'est pas importable
DOSSIER_SESSIONS = "agent-sessions"
RE_HUB = re.compile(r"^type:\s*[\"']?projet-chantier[\"']?\s*$", re.M)


def est_hub(texte: str) -> bool:
    if not texte.startswith("---"):
        return False
    fin = texte.find("\n---", 3)
    return bool(RE_HUB.search(texte[: fin if fin > 0 else 3000]))


def lire(f: Path) -> dict | None:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def ecrire_atomique(f: Path, m: dict) -> None:
    if not f.exists():                       # purgé ou libéré entre-temps : ne pas le ressusciter
        return
    tmp = f.with_name(f".{f.stem}.bail.tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


def ttl() -> int:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import commit_guard  # noqa: PLC0415
        return commit_guard.TTL_SECONDES
    except Exception:
        return TTL_SECONDES


def traiter(data: dict, maintenant: float | None = None) -> str | None:
    """Pose le bail et rend le message d'avertissement, ou None. Séparé de main() pour les tests."""
    maintenant = maintenant or time.time()
    ti = data.get("tool_input") or {}
    chemin = ti.get("file_path")
    if not chemin or not str(chemin).endswith(".md"):
        return None
    depot = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or ".").resolve()
    p = Path(chemin)
    if not p.is_absolute():
        p = Path(data.get("cwd") or depot) / p
    try:
        rel = p.resolve().relative_to(depot).as_posix()
    except ValueError:
        return None
    d = depot / ".git" / DOSSIER_SESSIONS
    if not d.is_dir():
        return None

    contenu = ti.get("content") if data.get("tool_name") == "Write" else None
    if contenu is None:
        try:
            contenu = p.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            return None
    if not est_hub(contenu):
        return None

    duree = ttl()
    marqueurs = []
    for f in d.glob("*.json"):
        m = lire(f)
        if m and maintenant - m.get("last_seen", m.get("started", 0)) <= duree:
            marqueurs.append((f, m))

    cid = data.get("session_id")
    miens = [(f, m) for f, m in marqueurs if cid and m.get("claude_session_id") == cid]
    moi = max(miens, key=lambda x: x[1].get("last_seen", x[1].get("started", 0))) if miens else None
    ids_miens = {m.get("id") for _, m in miens}
    autres = [m for _, m in marqueurs if m.get("id") not in ids_miens and rel in (m.get("baux") or {})]

    jour = time.strftime("%Y-%m-%d %H:%M", time.localtime(maintenant))
    a_signaler = autres
    if moi:
        f, m = moi
        baux = m.setdefault("baux", {})
        b = baux.get(rel) or {"depuis": jour, "ts": maintenant}
        b["dernier"] = jour
        deja = set(b.get("averti", []))
        a_signaler = [a for a in autres if a.get("id") not in deja]
        if autres:
            b["averti"] = sorted(deja | {a.get("id") for a in autres})
        baux[rel] = b
        ecrire_atomique(f, m)

    if not a_signaler:
        return None
    nom = Path(rel).stem

    def quand(iso: str) -> str:          # « 18:58 » le jour même, la date complète sinon
        return iso[-5:] if iso[:10] == jour[:10] else iso

    tenants = " ; ".join(
        f"la session {a.get('id', '?')} ({a.get('label', '?')}) depuis {quand(a['baux'][rel].get('depuis', '?'))}, "
        f"dernier geste à {quand(a['baux'][rel].get('dernier', '?'))}"
        for a in a_signaler)
    return (f"Bail (information, rien n'est bloqué) : le hub [[{nom}]] est aussi tenu par {tenants}. "
            "Deux sessions sur la même note, c'est la collision que le commit ne sait pas démêler "
            "(commit_guard.py pourra refuser de pousser). Prévenir l'humain avant de poursuivre l'édition.")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        msg = traiter(data)
    except Exception:
        return 0
    if msg:
        print(json.dumps({"systemMessage": msg,
                          "hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "additionalContext": msg}},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

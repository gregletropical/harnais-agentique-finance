"""Contrôle statique des gestes interdits dans le code du pipeline (analyse AST).

Une revue de code se fatigue ; une analyse AST, non. Ce contrôle parcourt les
modules Python d'un dossier et refuse :

G1  tout import réseau, de sous-processus ou d'appel natif (`socket`, `http`,
    `urllib`, `smtplib`, `subprocess`, `ctypes`...) — barrière 1 ;
G2  tout appel dynamique (`eval`, `exec`, `compile`, `__import__`, `os.system`,
    `os.popen`) qui contournerait G1 ;
G3  tout chemin de méthode qui contient un verbe interdit (`("messages", "send")`,
    `["drafts", "delete"]`...) — les trois interdits ;
G4  pour les lecteurs (`lecteur.py`, `lecteur_revue.py`) : des imports hors de la
    bibliothèque standard pure, ou l'usage de `open`, `environ`, `getenv` — le
    lecteur ne doit pouvoir atteindre ni disque, ni variable d'environnement, ni jeton ;
G5  pour l'orchestrateur : tout chemin vers le contenu brut (import de l'ingestion,
    de l'extracteur HTML, des fonctions de préparation du lecteur) — barrière 6.

Usage : python -m controles.controle_gestes [dossier]   (défaut : controles/)
Code retour 1 s'il existe au moins une violation.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
REGLES = json.loads((ICI.parent / "regles" / "gestes_interdits.json").read_text(encoding="utf-8"))
IMPORTS_INTERDITS = set(REGLES["imports_interdits_pipeline"])
VERBES_INTERDITS = set(REGLES["verbes_interdits"])
IMPORTS_LECTEURS = set(REGLES["imports_autorises_lecteurs"])
LECTEURS = {"lecteur.py", "lecteur_revue.py"}
APPELS_DYNAMIQUES = {"eval", "exec", "compile", "__import__"}
ATTRIBUTS_DYNAMIQUES = {"system", "popen", "execv", "execve", "spawnl", "startfile"}
ORCHESTRATEUR_INTERDITS = {"ingestion", "html_texte", "pieces_jointes", "preparer", "neutraliser",
                           "html_vers_texte", "corps_texte", "analyser", "lire_eml"}


def _modules_importes(n) -> list[str]:
    if isinstance(n, ast.Import):
        return [a.name.split(".")[0] for a in n.names]
    if isinstance(n, ast.ImportFrom):
        if n.level:                         # import relatif : interne au paquet
            return ["controles"] + ([n.module.split(".")[0]] if n.module else [])
        return [(n.module or "").split(".")[0]]
    return []


def analyser_fichier(chemin: Path) -> list[tuple[str, int, str, str]]:
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    nom = chemin.name
    v: list[tuple[str, int, str, str]] = []
    for n in ast.walk(arbre):
        ligne = getattr(n, "lineno", 0)
        mods = _modules_importes(n)
        for m in mods:
            if m in IMPORTS_INTERDITS:
                v.append((nom, ligne, "G1", f"import interdit : {m}"))
            if nom in LECTEURS and m not in IMPORTS_LECTEURS:
                v.append((nom, ligne, "G4", f"import hors bibliothèque standard pure : {m}"))
        if isinstance(n, ast.ImportFrom) and nom == "orchestrateur.py":
            noms = {a.name for a in n.names} | set(mods)
            if noms & ORCHESTRATEUR_INTERDITS:
                v.append((nom, ligne, "G5", f"chemin vers le contenu brut : {sorted(noms & ORCHESTRATEUR_INTERDITS)}"))
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in APPELS_DYNAMIQUES:
                v.append((nom, ligne, "G2", f"appel dynamique : {f.id}"))
            if isinstance(f, ast.Attribute) and f.attr in ATTRIBUTS_DYNAMIQUES:
                v.append((nom, ligne, "G2", f"appel système : {f.attr}"))
        if isinstance(n, (ast.Tuple, ast.List)):
            chaines = {e.value for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
            if len(n.elts) >= 2 and chaines & VERBES_INTERDITS:
                v.append((nom, ligne, "G3", f"méthode interdite : {sorted(chaines & VERBES_INTERDITS)}"))
        if nom in LECTEURS and isinstance(n, (ast.Name, ast.Attribute)):
            ident = n.id if isinstance(n, ast.Name) else n.attr
            if ident in {"open", "environ", "getenv"}:
                v.append((nom, ligne, "G4", f"accès disque ou environnement : {ident}"))
        if nom == "orchestrateur.py" and isinstance(n, ast.Attribute) and n.attr in {"corps_texte", "entetes"}:
            v.append((nom, ligne, "G5", f"accès au contenu brut : {n.attr}"))
    return v


def analyser_dossier(dossier: Path) -> list[tuple[str, int, str, str]]:
    out = []
    for f in sorted(Path(dossier).glob("*.py")):
        if f.name == "controle_gestes.py":
            continue   # ce module contient, par construction, les listes qu'il cherche
        out += analyser_fichier(f)
    return out


def main(argv: list[str]) -> int:
    dossier = Path(argv[1]) if len(argv) > 1 else ICI
    violations = analyser_dossier(dossier)
    for nom, ligne, code, detail in violations:
        print(f"[{code}] {nom}:{ligne} — {detail}")
    n = len(list(Path(dossier).glob("*.py")))
    print(f"\n{n} module(s) analysé(s), {len(violations)} violation(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

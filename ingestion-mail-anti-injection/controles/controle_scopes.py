"""Contrôle des profils de connexion : un jeton ne doit pas pouvoir plus que son niveau (barrière 7).

La consigne « en lecture, n'écris pas » ne protège de rien. Ce qui protège, c'est
qu'un jeton de lecture soit TECHNIQUEMENT incapable d'écrire faute de scope
accordé. Ce contrôle lit les fichiers de profil (un par jeton) et vérifie :

S1  le niveau est connu (lecture, maintenance, plein) ;
S2  chaque scope demandé appartient à la liste de son niveau et de son fournisseur ;
S3  aucun scope de la liste « jamais demandés » (suppression définitive,
    transfert automatique, accès à tout le tenant) ;
S4  un profil `plein` n'est ni chargeable par une routine, ni copié sur un serveur ;
S5  hors niveau `plein`, aucun outil exposé à l'agent ne permet d'envoyer, de
    supprimer, de transférer ou de répondre (liste d'outils d'un serveur MCP).

Contre-épreuve recommandée en réel : demander un scope hors niveau doit échouer
chez le fournisseur (`invalid_scope`) ; ce contrôle-ci attrape l'erreur avant.

Usage : python -m controles.controle_scopes exemples/profils
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REGLES = json.loads((Path(__file__).resolve().parents[1] / "regles" / "niveaux_de_droits.json").read_text(encoding="utf-8"))


def controler_profil(p: dict) -> list[str]:
    ecarts: list[str] = []
    niveau, fournisseur = p.get("niveau"), p.get("fournisseur")
    if niveau not in REGLES["niveaux"]:
        return [f"S1 niveau inconnu {niveau!r}"]
    autorises = set(REGLES["niveaux"][niveau].get(fournisseur, []))
    if not autorises:
        return [f"S2 fournisseur inconnu {fournisseur!r}"]
    for s in p.get("scopes", []):
        if s in REGLES["scopes_jamais_demandes"]:
            ecarts.append(f"S3 scope jamais demandé : {s}")
        elif s not in autorises:
            ecarts.append(f"S2 scope hors niveau {niveau} : {s}")
    if niveau == "plein" and (p.get("chargeable_par_routine") or p.get("copie_sur_serveur")):
        ecarts.append("S4 profil plein chargeable par une routine ou copié sur un serveur")
    if p.get("chargeable_par_routine") and not REGLES["niveaux"][niveau]["chargeable_par_routine"]:
        ecarts.append("S4 niveau non chargeable par une routine")
    if niveau != "plein":
        rx = re.compile(REGLES["outils_interdits_hors_plein"], re.I)
        for o in p.get("outils", []):
            if rx.search(o):
                ecarts.append(f"S5 outil interdit hors niveau plein : {o}")
    return ecarts


def main(argv: list[str]) -> int:
    dossier = Path(argv[1]) if len(argv) > 1 else Path("exemples/profils")
    total = 0
    for f in sorted(dossier.glob("*.json")):
        ecarts = controler_profil(json.loads(f.read_text(encoding="utf-8")))
        total += len(ecarts)
        print(f"[{'OK ' if not ecarts else 'KO '}] {f.name}")
        for e in ecarts:
            print(f"      {e}")
    print(f"\n{total} écart(s)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

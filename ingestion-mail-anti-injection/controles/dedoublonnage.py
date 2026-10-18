"""Contrôle de volumétrie et de dédoublonnage inter-boîtes.

Un même message existe souvent dans plusieurs boîtes (un expéditeur met deux
adresses en copie, deux boîtes de service reçoivent la même demande). La base
garde UNE LIGNE PAR BOÎTE — l'état lu / non lu et le dossier sont propres à
chaque boîte — mais toute volumétrie de FLUX, et toute décision, doit compter le
`Message-ID` une seule fois : sinon une même demande est traitée deux fois, ou
une même attaque comptée comme deux signaux indépendants.

Agrégats seulement, aucun contenu imprimé. Dans le système réel, la requête porte
sur la base locale du corpus ; ici, sur le manifeste des exemples.

Usage : python -m controles.dedoublonnage exemples/mails
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .ingestion import lire_eml


def controler(dossier: Path) -> dict:
    manifeste = json.loads((Path(dossier) / "manifeste.json").read_text(encoding="utf-8"))
    lignes = []
    for cas in manifeste["cas"]:
        m = lire_eml(Path(dossier) / cas["fichier"])
        lignes.append((cas["boite"], m.message_id or None))
    par_id: dict[str, set] = defaultdict(set)
    occurrences: Counter = Counter()
    for boite, mid in lignes:
        if mid:
            par_id[mid].add(boite)
            occurrences[mid] += 1
    sans_id = sum(1 for _, mid in lignes if not mid)
    uniques = len(par_id) + sans_id
    groupes = Counter()
    for mid, n in occurrences.items():
        if n > 1:
            groupes["+".join(sorted(par_id[mid]))] += 1
    return {"total": len(lignes), "uniques": uniques, "sans_id": sans_id,
            "par_boite": dict(Counter(b for b, _ in lignes)), "groupes": dict(groupes)}


def main(argv: list[str]) -> int:
    r = controler(Path(argv[1]) if len(argv) > 1 else Path("exemples/mails"))
    excedent = r["total"] - r["uniques"]
    print(f"lignes {r['total']}, messages uniques {r['uniques']}, excédent {excedent}, sans Message-ID {r['sans_id']}")
    for b, n in sorted(r["par_boite"].items()):
        print(f"  {b:20s} {n:4d}")
    for g, n in r["groupes"].items():
        print(f"  doublon {g:20s} {n:4d} groupe(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

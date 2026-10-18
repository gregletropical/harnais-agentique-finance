#!/usr/bin/env python3
"""
etat.py — Commande `etat` de la routine de lettrage (LECTURE SEULE) : produit le
rapport que l'agent soumet à l'utilisateur pour GO.

Déroulé :
  1. lit la source (ici les exemples synthétiques ; en production, l'ERP en lecture) ;
  2. contrôle la fraîcheur de la synchronisation de chaque banque ;
  3. contrôle la continuité des soldes bancaires et sort des exécutables toute ligne
     qui compense exactement un écart apparu (doublon par réimport) — AVANT classement ;
  4. classe chaque ligne (regles/classement.py) en exécutable / à arbitrer / exception ;
  5. contrôle les rapprochements automatiques faits par le robot de l'ERP pendant la nuit ;
  6. affiche les compteurs de dérive qui ont bougé depuis la veille ;
  7. écrit un rapport Markdown et un JSON (consommé par plan_ecriture.py).

Usage :
  python controles/etat.py                         # sur exemples/, rapport sur la sortie standard
  python controles/etat.py --sortie sortie/        # écrit aussi AAAA-MM-JJ_HHMM_etat.{md,json}
  python controles/etat.py --maintenant "2026-10-16 07:00:00"   # horodatage figé (UTC)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from controles.source_fichier import SourceFichier  # noqa: E402
from regles.categories import FRAICHEUR_SYNCHRO_HEURES  # noqa: E402
from regles.classement import (  # noqa: E402
    ORDRE_CLASSES, anomalie_rapprochement_auto, classement_reimport, classer, controle_continuite,
    suspects_reimport,
)

FORMAT_UTC = "%Y-%m-%d %H:%M:%S"


def eur(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",") + " €"


def construire_etat(src: SourceFichier, maintenant: dt.datetime) -> dict:
    """Fonction pure (hors horloge injectée) : tout ce que le rapport affiche."""
    lignes = src.lignes()
    depuis = src.releve.get("dernier_passage_utc", "")

    synchro = []
    for j in src.journaux.values():
        der = dt.datetime.strptime(j["derniere_synchro_utc"], FORMAT_UTC)
        age_h = (maintenant - der).total_seconds() / 3600
        synchro.append({"journal": j["nom"], "derniere_synchro_utc": j["derniere_synchro_utc"],
                        "age_heures": round(age_h, 1), "alerte": age_h > FRAICHEUR_SYNCHRO_HEURES})

    continuite, reimport = [], {}
    for j in src.journaux.values():
        diag = controle_continuite(src.points_solde(j["id"]))
        diag.update({"journal": j["nom"], "journal_id": j["id"]})
        continuite.append(diag)
        for lid in suspects_reimport(lignes, j["id"], diag):
            reimport[lid] = diag

    sortie = []
    importees = {x["id"]: x.get("importee_le", "") for x in src.releve["lignes"]}
    for l in lignes:
        k = classement_reimport(reimport[l.id]) if l.id in reimport else classer(l, src)
        sortie.append({"id": l.id, "date": l.date, "montant": l.montant, "libelle": l.libelle,
                       "journal": l.journal, "journal_id": l.journal_id, "societe": l.societe,
                       "societe_id": l.societe_id, "nouvelle": importees.get(l.id, "") >= depuis,
                       "classement": k.en_dict()})

    anomalies = []
    for r in src.ref.get("rapprochements_automatiques", []):
        motif = anomalie_rapprochement_auto(r["debit"], r["credit"], r["partiel"])
        if motif:
            anomalies.append({**r, "motif": motif})

    return {"horodatage_utc": maintenant.strftime(FORMAT_UTC), "depuis_utc": depuis,
            "lignes": sortie, "synchro": synchro, "continuite": continuite,
            "rapprochements_auto": {"total": len(src.ref.get("rapprochements_automatiques", [])),
                                    "anomalies": anomalies},
            "derive": [d for d in src.ref.get("derive", []) if d["veille"] != d["jour"]]}


def _ordre(x: dict) -> tuple:
    return ORDRE_CLASSES.index(x["classement"]["classe"]), x["id"]


def _cand(k: dict, n: int = 3) -> str:
    c = k["candidats"] if k["classe"] == "E" else k["candidats"][:n]
    return (" — " + ", ".join(c)) if c else ""


def rapport_markdown(e: dict) -> str:
    L = [f"# Rapport de lettrage du matin — {e['horodatage_utc']} UTC", "",
         f"Horodatage : {e['horodatage_utc']} UTC. Fenêtre des nouveautés : depuis {e['depuis_utc']} UTC.", ""]
    lignes = e["lignes"]
    compte = Counter(x["classement"]["famille"] for x in lignes)
    L += [f"**{len(lignes)} lignes non rapprochées** : {compte['executable']} exécutables, "
          f"{compte['a_arbitrer']} à arbitrer, {compte['exception']} exceptions.", ""]

    L += ["## Synchronisation bancaire", ""]
    for s in e["synchro"]:
        alerte = f" — **ALERTE : pas de synchronisation depuis {s['age_heures']:.0f} h**" if s["alerte"] else ""
        L.append(f"- {s['journal']} : dernier passage {s['derniere_synchro_utc']} UTC{alerte}")
    L.append("")

    L += ["## Continuité des soldes bancaires", ""]
    for j in e["continuite"]:
        if j["alerte"]:
            debut, fin = j["apparition"]
            L.append(f"- **ALERTE {j['journal']}** : écart solde banque − solde ERP de {eur(j['ecart'])} au "
                     f"{j['date']}, écart apparu entre le {debut or 'début de la fenêtre'} et le {fin} "
                     f"(ligne supprimée puis réimportée, ou ligne manquante)")
        elif j["fiable"]:
            L.append(f"- {j['journal']} : d'équerre au {j['date']}")
        else:
            L.append(f"- {j['journal']} : non contrôlable ({j['valeurs_ecart']} écarts différents sur "
                     f"{j['points']} dates : la banque transmet un solde non arrêté à la date)")
    L.append("")

    L += ["## 1. Exécutable sur simple GO", ""]
    execs = sorted((x for x in lignes if x["classement"]["famille"] == "executable"), key=_ordre)
    if execs:
        L += ["| Classe | Ligne | Date | Montant | Libellé | Traitement prévu |", "|---|---|---|---|---|---|"]
        for x in execs:
            k = x["classement"]
            note = " · validation a posteriori demandée au comptable" if k["validation_comptable"] else ""
            L.append(f"| {k['classe']} | {x['id']} | {x['date']} | {eur(x['montant'])} | {x['libelle'][:60]} | "
                     f"{k['motif']}{_cand(k)}{note} |")
    else:
        L.append("Rien d'exécutable.")
    L.append("")

    def table(sel: list) -> list[str]:
        out = ["| Classe | Ligne | Date | Montant | Société | Libellé | Motif |", "|---|---|---|---|---|---|---|"]
        for x in sorted(sel, key=_ordre):
            k = x["classement"]
            out.append(f"| {k['classe']} | {x['id']} | {x['date']} | {eur(x['montant'])} | {x['societe']} | "
                       f"{x['libelle'][:60]} | {k['motif']}{_cand(k)} |")
        return out

    for titre, fam in (("## 2. À arbitrer — une proposition existe, décision humaine", "a_arbitrer"),
                       ("## 3. Exceptions — anomalie à instruire, rien n'est proposé", "exception")):
        L += [titre, ""]
        nouv = [x for x in lignes if x["classement"]["famille"] == fam and x["nouvelle"]]
        stock = [x for x in lignes if x["classement"]["famille"] == fam and not x["nouvelle"]]
        L += table(nouv) if nouv else ["Aucune nouvelle ligne."]
        if stock:
            L += ["", f"Stock déjà signalé lors d'un passage précédent ({len(stock)} ligne(s), non ré-analysé) :", ""]
            L += table(stock)
        L.append("")

    a = e["rapprochements_auto"]
    L += ["## 4. Rapprochements automatiques de la nuit", "",
          f"{a['total']} rapprochement(s) faits par le robot de l'ERP, **{len(a['anomalies'])} anomalie(s)** :"]
    for an in a["anomalies"]:
        L.append(f"- {eur(an['montant'])} {an['debit']} ↔ {an['credit']} ({an['pieces']}) : {an['motif']}")
    L.append("")

    L += ["## 5. Dérive depuis la veille", ""]
    L += [f"- {d['controle']} : {d['veille']} → {d['jour']}" for d in e["derive"]] or ["Aucun compteur n'a bougé."]
    L += ["", "## GO attendu", "",
          "Les lignes de la section 1 s'exécutent sur GO explicite, cité mot pour mot dans le plan d'écriture :",
          "", "```", 'python controles/plan_ecriture.py --etat <ce_fichier>.json --go "<citation exacte du GO>"',
          "```", "",
          "Les sections 2 et 3 ne s'exécutent jamais par le script : chaque cas est instruit, proposé avec ses "
          "options, et tranché par l'utilisateur.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exemples", type=Path, default=RACINE / "exemples", help="dossier releve.json + referentiel.json")
    ap.add_argument("--sortie", type=Path, help="dossier où écrire le rapport .md et l'état .json")
    ap.add_argument("--maintenant", help="horodatage UTC « AAAA-MM-JJ HH:MM:SS » (défaut : maintenant)")
    args = ap.parse_args(argv)

    maintenant = (dt.datetime.strptime(args.maintenant, FORMAT_UTC) if args.maintenant
                  else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0))
    etat = construire_etat(SourceFichier.depuis_dossier(args.exemples), maintenant)
    md = rapport_markdown(etat)
    print(md)
    if args.sortie:
        args.sortie.mkdir(parents=True, exist_ok=True)
        base = args.sortie / maintenant.strftime("%Y-%m-%d_%H%M")
        Path(f"{base}_etat.json").write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
        Path(f"{base}_etat.md").write_text(md, encoding="utf-8")
        print(f"\n→ {base}_etat.md\n→ {base}_etat.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

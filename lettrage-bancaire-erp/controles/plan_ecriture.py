#!/usr/bin/env python3
"""
plan_ecriture.py — Commande `appliquer` de la routine, en version publiable : elle
produit le PLAN D'ÉCRITURE et s'arrête là (dry-run).

En production, la commande équivalente écrit dans l'ERP par son API, et seulement :
  - avec `--executer` ET `--go "<citation exacte du GO de l'utilisateur>"` ;
  - sur un état de moins de 2 heures ;
  - pour les seules lignes classées exécutables (A, A'1, B, N, R, I), dans cet ordre ;
  - en recalculant chaque garde-fou JUSTE AVANT chaque appel, en relisant l'ERP après
    chaque geste, et en s'arrêtant à la PREMIÈRE anomalie, sans jamais relancer un appel.

Le connecteur d'écriture n'est pas publié (identifiants, URL, méthodes propres à
l'environnement du client). Ce script garde tout le reste : sélection des lignes,
ordre d'exécution, garde-fous recalculés contre la source au moment du plan, arrêt à
la première anomalie, consignation du GO, compte rendu. Chaque geste est décrit en
termes métier ; l'adaptateur ERP le traduit en appels API après GO.

Usage :
  python controles/plan_ecriture.py --etat sortie/AAAA-MM-JJ_HHMM_etat.json
  python controles/plan_ecriture.py --etat … --go "GO pour les lignes exécutables"
  python controles/plan_ecriture.py --etat … --classes A,I --lignes 1,9
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from controles.source_fichier import SourceFichier  # noqa: E402
from regles.categories import COMPTE_ATTENTE_BANQUE  # noqa: E402
from regles.classement import EXECUTABLES, cents  # noqa: E402

FRAICHEUR_MAX = dt.timedelta(hours=2)
FORMAT_UTC = "%Y-%m-%d %H:%M:%S"


class Arret(Exception):
    """Garde-fou non satisfait : on s'arrête, rien n'est tenté ensuite."""


def eur(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",") + " €"


class Planificateur:
    """Recalcule les garde-fous de chaque geste contre la source, à l'instant du plan."""

    def __init__(self, src: SourceFichier):
        self.src = src

    def controle_ligne(self, x: dict) -> dict:
        st = self.src.ligne_releve(x["id"])
        if st is None:
            raise Arret(f"ligne {x['id']} introuvable")
        if st.get("rapprochee"):
            raise Arret(f"ligne {x['id']} déjà rapprochée depuis l'état")
        if cents(st["montant"]) != cents(x["montant"]):
            raise Arret(f"ligne {x['id']} : montant {st['montant']} ≠ {x['montant']} de l'état")
        soc = self.src.societes[self.src.journaux[st["journal_id"]]["societe_id"]]
        if soc.get("verrou") and st["date"] <= soc["verrou"]:
            raise Arret(f"ligne {x['id']} sur exercice clos (verrou au {soc['verrou']})")
        return {**st, "societe_id": soc["id"]}

    def _residus(self, ids: list[int]) -> dict:
        r = self.src.residus(ids)
        manquants = sorted(set(ids) - set(r))
        if manquants:
            raise Arret(f"lignes d'écriture introuvables : {manquants}")
        return r

    def lettrer(self, x: dict, st: dict) -> dict:
        g = x["classement"]["geste"]
        amls = self._residus(g["aml_ids"])
        if any(a["lettree"] for a in amls.values()):
            raise Arret(f"ligne {x['id']} : une ligne à apparier est déjà lettrée")
        if any(a["societe_id"] != st["societe_id"] for a in amls.values()):
            raise Arret(f"ligne {x['id']} : ligne à apparier d'une autre société")
        somme = sum(a["residu"] for a in amls.values())
        if cents(somme) != cents(st["montant"]):
            raise Arret(f"ligne {x['id']} : garde-fou de somme {somme:.2f} ≠ {st['montant']:.2f}")
        return {"geste": f"rapprocher la ligne bancaire avec {len(amls)} ligne(s) de tiers ouvertes "
                         f"({', '.join(g['pieces'])})",
                "garde_fous": f"somme des restes dus {eur(somme)} = montant, au centime ; aucune ligne déjà lettrée",
                "relecture": "ligne rapprochée, pièces soldées, numéro de lettrage"}

    def lot(self, x: dict, st: dict) -> dict:
        g = x["classement"]["geste"]
        b = self.src.lot(g["lot_id"])
        if b is None or b["etat"] != "envoye":
            raise Arret(f"lot {g['lot']} absent ou dans l'état {b and b['etat']}")
        if cents(b["montant"]) != cents(st["montant"]) or b["journal_id"] != st["journal_id"]:
            raise Arret(f"lot {g['lot']} : montant ou journal différent de la ligne")
        return {"geste": f"rapprocher la ligne bancaire avec le lot de paiements {g['lot']}",
                "garde_fous": "lot à l'état envoyé, même montant, même journal",
                "relecture": "ligne rapprochée, lot à l'état rapproché"}

    def imputer(self, x: dict, st: dict) -> dict:
        g = x["classement"]["geste"]
        if st.get("contreparties_posees"):
            raise Arret(f"ligne {x['id']} : contrepartie d'attente {COMPTE_ATTENTE_BANQUE} plus unique")
        etapes = []
        if g["partenaire_id"]:
            etapes.append(f"poser le tiers {self.src.tiers[g['partenaire_id']]['nom']} sur la ligne "
                          "(par la méthode de l'écran de rapprochement, jamais par écriture directe du champ)")
        etapes.append(f"imputer la contrepartie d'attente {COMPTE_ATTENTE_BANQUE} sur {g['compte']}")
        garde = f"contrepartie d'attente unique, au montant de la ligne"
        if g["lettrer_avec"]:
            od = self._residus(g["lettrer_avec"])
            if any(a["lettree"] for a in od.values()):
                raise Arret(f"ligne {x['id']} : l'OD à lettrer est déjà lettrée")
            if cents(sum(a["residu"] for a in od.values())) != cents(st["montant"]):
                raise Arret(f"ligne {x['id']} : l'OD à lettrer ne porte pas le montant du prélèvement")
            etapes.append(f"lettrer la nouvelle contrepartie {g['compte']} avec l'OD ouverte (groupe soldé à 0)")
            garde += " ; OD unique, non lettrée, au même montant"
        return {"geste": " ; puis ".join(etapes), "garde_fous": garde,
                "relecture": "ligne rapprochée, compte imputé" + (", numéro de lettrage" if g["lettrer_avec"] else "")}


def construire_plan(etat: dict, src: SourceFichier, classes: list[str] | None = None,
                    ids: set[int] | None = None) -> dict:
    classes = classes or list(EXECUTABLES)
    a_traiter = [x for x in etat["lignes"] if x["classement"]["executable"]
                 and x["classement"]["classe"] in classes and (ids is None or x["id"] in ids)]
    a_traiter.sort(key=lambda x: (EXECUTABLES.index(x["classement"]["classe"]), x["id"]))
    p = Planificateur(src)
    plan, arret = [], None
    for x in a_traiter:
        k = x["classement"]
        try:
            st = p.controle_ligne(x)
            res = {"lettrer": p.lettrer, "lot": p.lot, "imputer": p.imputer}[k["geste"]["type"]](x, st)
            if k["validation_comptable"]:
                res["suite"] = ("activité « À faire » au comptable sur la pièce de banque : composition retenue, "
                                "seule combinaison exacte, lettrage sans référence du client — à valider ou annuler")
            plan.append({"id": x["id"], "classe": k["classe"], "montant": x["montant"], "libelle": x["libelle"], **res})
        except Arret as e:
            arret = str(e)
            break
    return {"plan": plan, "a_traiter": len(a_traiter), "arret": arret}


def compte_rendu(resultat: dict, etat_nom: str, go: str | None, maintenant: dt.datetime) -> str:
    mode = "PLAN VALIDÉ PAR GO" if go else "SIMULATION"
    L = [f"# Plan d'écriture — {maintenant:%Y-%m-%d %H:%M} UTC — {mode}", "",
         f"État source : `{etat_nom}`.",
         f"GO de l'utilisateur, consigné par l'agent : « {go} »" if go else "GO : aucun (simulation).", "",
         "| Ordre | Classe | Ligne | Montant | Geste prévu | Garde-fous recalculés | Relecture après geste |",
         "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(resultat["plan"], 1):
        suite = f" ; ensuite : {r['suite']}" if r.get("suite") else ""
        L.append(f"| {i} | {r['classe']} | {r['id']} | {eur(r['montant'])} | {r['geste']}{suite} | "
                 f"{r['garde_fous']} | {r['relecture']} |")
    L += ["", f"**{len(resultat['plan'])} geste(s) planifié(s) sur {resultat['a_traiter']} ligne(s) exécutable(s).**"]
    if resultat["arret"]:
        L += ["", f"**ARRÊT** : {resultat['arret']}. Rien n'est planifié après cette ligne ; la main revient "
                  "à l'utilisateur avec l'état exact."]
    L += ["", "Ce dépôt s'arrête au plan. En production, l'adaptateur ERP exécute ces gestes un par un, "
              "relit l'ERP après chacun et s'arrête à la première anomalie, sans relance."]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--etat", type=Path, required=True, help="JSON produit par etat.py --sortie")
    ap.add_argument("--exemples", type=Path, default=RACINE / "exemples")
    ap.add_argument("--classes", help="classes à traiter parmi " + ",".join(EXECUTABLES))
    ap.add_argument("--lignes", help="identifiants de lignes, séparés par des virgules")
    ap.add_argument("--go", help="citation exacte du GO de l'utilisateur")
    ap.add_argument("--maintenant", help="horodatage UTC « AAAA-MM-JJ HH:MM:SS » (défaut : maintenant)")
    args = ap.parse_args(argv)
    if args.go is not None and not args.go.strip():
        ap.error("--go vide : un GO qui ne peut pas être cité n'existe pas")

    etat = json.loads(args.etat.read_text(encoding="utf-8"))
    maintenant = (dt.datetime.strptime(args.maintenant, FORMAT_UTC) if args.maintenant
                  else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0))
    age = maintenant - dt.datetime.strptime(etat["horodatage_utc"], FORMAT_UTC)
    if args.go and age > FRAICHEUR_MAX:
        ap.error(f"état vieux de {age} : relancer etat.py avant de valider un plan")

    res = construire_plan(etat, SourceFichier.depuis_dossier(args.exemples),
                          args.classes.split(",") if args.classes else None,
                          {int(i) for i in args.lignes.split(",")} if args.lignes else None)
    print(compte_rendu(res, args.etat.name, args.go, maintenant))
    return 1 if res["arret"] else 0


if __name__ == "__main__":
    sys.exit(main())

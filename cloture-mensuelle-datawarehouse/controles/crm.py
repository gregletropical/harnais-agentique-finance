"""CRM : registre d'anomalies, garde-fous du prévisionnel, deals disparus.

Trois leçons de clôtures réelles sont codées ici :

1. **Une correction faite à la main en base ne survit pas à son chargement** (la table est rechargée en
   DROP + CREATE). Toute correction qui ne peut pas être faite à la source vit donc dans un registre
   versionné (`regles/registre_anomalies_crm.csv`). Le chargement n'applique que les lignes `ouvert`
   dont la valeur source est toujours celle constatée, et signale de lui-même celles dont la source s'est
   corrigée entre-temps : l'obsolescence est pilotée par la donnée, pas par une date de péremption. Le
   registre n'est jamais réécrit automatiquement : repasser une ligne à `resolu` reste un geste humain.
2. **Le prévisionnel s'étale par MOIS, donc son garde-fou se juge au grain mois.** Un deal ouvert dont le
   début tombe sur le mois clôturé (ou avant) déposerait du prévisionnel sur un mois déjà réel : son
   prévisionnel démarre à P+1, montant total inchangé, et le décalage est signalé.
3. **Un deal qui disparaît d'une extraction à l'autre ne déclenche aucun contrôle de volumétrie.** Le
   diff de population le rend visible. La qualification (supprimé, archivé, filtré) demande une lecture
   en direct du CRM, en lecture seule, sur décision humaine : elle n'est pas publiée ici, et le silence
   de la source ne classe jamais un deal en « légitime » par défaut.
"""
from __future__ import annotations

import sqlite3

from controles import commun as C


class DatesInversees(RuntimeError):
    """Un deal ouvert a une fin antérieure à son début : le prévisionnel serait faux, le pipeline s'arrête."""


def appliquer_registre(deals: list[dict], registre: list[dict]) -> tuple[list[dict], list[str]]:
    """Applique les corrections `ouvert` du registre ; renvoie (deals corrigés, constats d'obsolescence)."""
    par_id = {d["id_deal"]: dict(d) for d in deals}
    constats = []
    for r in registre:
        if r.get("statut") != "ouvert":
            continue
        d = par_id.get(r["id_deal"])
        if d is None:
            constats.append(f"{r['id_deal']} : absent de l'extraction, la ligne du registre ne s'applique plus")
            continue
        actuel = d.get(r["champ"])
        if actuel == r["valeur_source"]:
            d[r["champ"]] = r["valeur_corrigee"]
        else:
            constats.append(f"{r['id_deal']}.{r['champ']} : la source vaut {actuel!r} (constaté {r['valeur_source']!r}) "
                            "- source corrigée, ligne à repasser `resolu` dans le registre")
    return [par_id[d["id_deal"]] for d in deals], constats


def controler_dates(conn: sqlite3.Connection) -> None:
    ko = conn.execute("SELECT id_deal, debut, fin FROM raw_deals WHERE statut = 'open' AND fin < debut").fetchall()
    if ko:
        raise DatesInversees("deal(s) ouvert(s) à dates inversées, à corriger à la source ou au registre : "
                             + ", ".join(f"{i} ({d} > {f})" for i, d, f in ko))


def forecast(conn: sqlite3.Connection, periode: str) -> tuple[list[tuple], list[str]]:
    """Valeur pondérée des deals ouverts, étalée également sur leurs mois, jamais sur un mois clos.

    Renvoie ([(mois, id_deal, montant)], constats de décalage)."""
    lignes, constats = [], []
    premier_mois_ouvert = C.decaler(periode, 1)
    for id_deal, valeur, proba, debut, fin in conn.execute(
            "SELECT id_deal, valeur, probabilite, debut, fin FROM raw_deals WHERE statut = 'open' ORDER BY id_deal"):
        d, f = C.mois_de(debut), C.mois_de(fin)
        if d < premier_mois_ouvert:
            constats.append(f"{id_deal} : début {debut} sur un mois clos, prévisionnel décalé à {premier_mois_ouvert} (montant inchangé)")
            d = premier_mois_ouvert
        mois = C.mois_entre(d, f) or [d]
        part = round(valeur * proba / len(mois), 2)
        lignes += [(m, id_deal, part) for m in mois]
    return lignes, constats


def deals_disparus(ancien: list[dict], nouveau: list[dict]) -> list[dict]:
    """Diff de population, pur : présents dans l'ancienne extraction, absents de la nouvelle.

    Un deal passé perdu reste dans l'extraction (tous les deals non supprimés) : ce n'est pas une disparition.
    Les montants rapportés sont les montants BRUTS de l'ancienne extraction."""
    ids = {d["id_deal"] for d in nouveau}
    return [d for d in ancien if d["id_deal"] not in ids]


def controle_disparus(ancien: list[dict], nouveau: list[dict]) -> C.Resultat:
    disp = deals_disparus(ancien, nouveau)
    det = [f"{d['id_deal']} {d['titre']} ({d['organisation']}, {d['statut']}, valeur {C.eur(C.f2(d['valeur']))}) "
           "-> INDETERMINE : qualification en lecture seule sur décision humaine" for d in disp]
    return C.Resultat("deals disparus du CRM", not disp,
                      f"{len(disp)} deal(s) à porter à l'humain" if disp else "aucune disparition",
                      bloquant=False, details=det)

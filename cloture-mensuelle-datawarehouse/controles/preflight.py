"""Pré-vol d'ouverture : ce qui est disponible pour clôturer P, AVANT toute extraction ou chargement.

La clôture n'est jamais automatique : la session présente ce bilan à l'humain et attend son GO sur le
mois à clôturer. Le pré-vol d'ouverture n'extrait rien et ne charge rien.

Vérifie :
- **mois** : le mois attendu est le mois précédant la date du jour ; un P différent est une incohérence
  (clôture en retard ou en avance), pas un refus : l'humain tranche ;
- **sources** : chaque fichier attendu est présent et non vide (manquant sinon) ;
- **paie** (seule source encore déposée à la main) : le dépôt couvre P, lu dans son contenu ; un dépôt
  qui couvre MOINS de mois que le précédent est une incohérence (le chargement de paie remplace tout :
  un historique manquant serait effacé de la production) ;
- **registre des chargements** : P déjà chargé (clôture faite ou à refaire ?) ; extrait plus ancien que
  le dernier chargé ;
- **mode par source** : delta si la source est au registre de production, complet sinon ; le CRM et la
  paie sont toujours complets.

Bilan : manquants (bloquants), incohérences (à présenter à l'humain), mode par source.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from controles import commun as C

FICHIERS = {
    "outil_projets": ["outil_projets/projets.csv", "outil_projets/cutoff.csv", "outil_projets/totaux_outil.csv",
                      "outil_projets/factures.csv", "outil_projets/achats.csv"],
    "compta": ["compta/grand_livre.csv"],
    "crm": ["crm/deals.csv"],
    "paie": ["paie/livre_paie.csv"],
}
TOUJOURS_COMPLET = {"crm": "toujours complet", "paie": "complet depuis le dépôt du mois"}


@dataclass
class Bilan:
    manquants: list[str] = field(default_factory=list)
    incoherences: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)
    modes: dict[str, str] = field(default_factory=dict)


def mois_attendu(aujourdhui: dt.date) -> str:
    """Le mois à clôturer est le mois précédant la date du jour."""
    d = aujourdhui.replace(day=1) - dt.timedelta(days=1)
    return f"{d.year}-{d.month:02d}"


def bilan_sources(exemple: Path, b: Bilan) -> None:
    for source, fichiers in FICHIERS.items():
        for f in fichiers:
            p = C.resoudre(exemple, f)
            if not p.exists() or not C.lire_csv(p):
                b.manquants.append(f"{source} : {f} absent ou vide")


def bilan_paie(livre: list[dict], periode: str, b: Bilan, mois_depot_precedent: int | None = None) -> None:
    mois = sorted({r["mois"] for r in livre})
    if not mois or mois[-1] < periode:
        b.manquants.append(f"paie : le dépôt couvre jusqu'à {mois[-1] if mois else '—'}, attendu {periode} "
                           "(déposer les exports de paie du mois)")
        return
    b.infos.append(f"paie : {len(mois)} mois couverts ({mois[0]} à {mois[-1]})")
    if mois_depot_precedent is not None and len(mois) < mois_depot_precedent:
        b.incoherences.append(f"paie : le dépôt couvre {len(mois)} mois, le précédent {mois_depot_precedent} — le chargement "
                              "remplace tout : un historique manquant serait effacé de la production")


def bilan_chaine(source: str, extrait: dict | None, charge: dict | None, periode: str, b: Bilan) -> None:
    """`extrait` : {nom, periode} de l'extrait disponible ; `charge` : {extrait, periode} du dernier chargé."""
    if source in TOUJOURS_COMPLET:
        b.modes[source] = TOUJOURS_COMPLET[source]
    else:
        b.modes[source] = (f"delta (chaîné à {charge['extrait']})" if charge
                           else "complet (absente du registre de production : premier passage)")
    if not extrait:
        return
    b.infos.append(f"{source} : extrait {extrait['nom']} (période {extrait.get('periode', '—')}) ; "
                   f"dernier chargé {charge['extrait'] if charge else '—'}")
    if charge and charge.get("periode") == periode:
        b.incoherences.append(f"{source} : {periode} est déjà chargé ({charge['extrait']}) — clôture déjà faite ou à refaire ?")
    if charge and extrait["nom"] < charge["extrait"]:
        b.incoherences.append(f"{source} : l'extrait {extrait['nom']} est plus ancien que le dernier chargé ({charge['extrait']})")


def executer(exemple: Path, periode: str, aujourdhui: dt.date) -> tuple[Bilan, list[str]]:
    b = Bilan()
    attendu = mois_attendu(aujourdhui)
    if periode != attendu:
        b.incoherences.append(f"mois demandé {periode}, mois attendu {attendu} : clôture en retard ou en avance ?")
    bilan_sources(exemple, b)
    bilan_paie(C.lire_source(exemple, "paie/livre_paie.csv"), periode, b)
    extraits = C.lire_json(exemple, "extraits.json")
    registre = C.lire_json(exemple, "registre_chargements.json")
    for source in FICHIERS:
        bilan_chaine(source, extraits.get(source), registre.get(source), periode, b)
    return b, texte(b, periode, attendu)


def texte(b: Bilan, periode: str, attendu: str) -> list[str]:
    out = [f"Pré-vol d'ouverture — mois demandé {periode}, mois attendu {attendu}", ""]
    out += ["MANQUANTS :"] + [f"  - {x}" for x in b.manquants or ["aucun"]]
    out += ["", "INCOHÉRENCES (à présenter à l'humain) :"] + [f"  - {x}" for x in b.incoherences or ["aucune"]]
    out += ["", "MODE PAR SOURCE :"] + [f"  - {k} : {v}" for k, v in b.modes.items()]
    out += ["", "INFORMATIONS :"] + [f"  - {x}" for x in b.infos]
    if b.manquants:
        out += ["", "VERDICT : MANQUANTS — compléter les sources puis relancer le pré-vol d'ouverture"]
    else:
        out += ["", "VERDICT : prêt — présenter ce bilan et attendre son GO sur le mois à clôturer"]
    return out

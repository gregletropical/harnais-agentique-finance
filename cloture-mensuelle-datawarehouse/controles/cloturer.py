"""Déroulé réduit d'une clôture mensuelle, de bout en bout, sur un dossier d'exemple synthétique.

    python -m controles.cloturer --exemple exemples/mois_conforme --periode 2026-03 --aujourdhui 2026-04-01 --go

Étapes (numérotées comme dans `instructions/commande-cloture-mensuelle.md`) :
  0. pré-vol d'ouverture bilan des sources ; sans --go, s'arrête ici : le GO sur le mois est humain
  1. chargement         raw_* depuis les extraits, cutoff d'abord avec son contrôle bloquant
  2-3. pipeline         garde MDM, stg_*, mart_* (contrôles de module bloquants)
  4. contrôles du mois  cadrages ventes, achats, paie ; vraisemblance ; deals disparus
  5. fin de clôture     contrôle avant diffusion : verdict CONFORME ou ÉCHEC
  6. récapitulatif      chiffres du mois, marqués NON DIFFUSABLES tant que 5 n'est pas conforme

Codes retour : 0 conforme ; 1 bloqué (manquant, contrôle bloquant, fin de clôture en échec) ;
2 arrêt volontaire en attente du GO humain.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

from controles import chargement, commun as C, crm, fin_de_cloture, mdm, pipeline, preflight, recap, recette


def _afficher(resultats: list[C.Resultat], detail: bool) -> None:
    for r in resultats:
        print("  " + r.ligne())
        if r.details and (detail or not r.ok):
            for d in r.details:
                print("      " + d)


def cloturer(exemple: Path, periode: str, aujourdhui: dt.date, go: bool, base: str = ":memory:",
             detail: bool = False, figer: Path | None = None, regles: Path = C.REGLES) -> int:
    exemple = Path(exemple)
    print(f"\n### 0. Pré-vol d'ouverture ({exemple.name})")
    bilan, texte = preflight.executer(exemple, periode, aujourdhui)
    print("\n".join("  " + l for l in texte))
    if bilan.manquants:
        return 1
    if not go:
        print("\n  ARRÊT : en attente du GO humain sur le mois à clôturer (relancer avec --go).")
        return 2
    print(f"  GO humain reçu sur {periode}.")

    conn = sqlite3.connect(base)
    try:
        print("\n### 1. Chargement des sources (raw_*)")
        try:
            _afficher(chargement.charger(conn, exemple, periode, regles), detail)
        except chargement.ChargementBloque as e:
            print(f"  {e}\n\n  CHARGEMENT BLOQUÉ : aucune autre source n'est chargée. Décision humaine attendue "
                  "(ajustement + exception motivée), puis recharger le même extrait.")
            return 1

        print("\n### 2-3. Garde MDM et pipeline (stg_*, mart_*)")
        try:
            for c in pipeline.executer(conn, periode, exemple):
                print(f"  CONSTAT {c}")
        except (mdm.GardeMDM, pipeline.ErreurModule, crm.DatesInversees) as e:
            print(f"  ÉCHEC   {e}\n\n  PIPELINE ARRÊTÉ : l'erreur se rapporte, elle ne se contourne pas.")
            return 1

        print("\n### 4. Contrôles du mois")
        _afficher(fin_de_cloture.controles_mois(conn, periode, exemple, regles), detail)

        print("\n### 5. Fin de clôture (contrôle avant diffusion)")
        fin = fin_de_cloture.executer(conn, periode, exemple, regles)
        _afficher(fin, detail)
        echecs = [r.nom for r in fin if r.bloquant and not r.ok]
        print("\n  FIN DE CLÔTURE : " + ("CONFORME" if not echecs else f"ÉCHEC ({', '.join(echecs)})"))

        print("\n### 6. Récapitulatif")
        print("\n".join("  " + l for l in recap.lignes(conn, periode, exemple, diffusable=not echecs)))
        if echecs:
            print("\n  Diffusion bloquée : présenter les échecs à l'humain, qui décide (correction à la source, "
                  "registre motivé, ajustement). Rien n'est forcé.")
            return 1
        if figer:
            print(f"\n  Instantané figé pour l'oracle M-1 de la clôture suivante : {recette.figer(conn, periode, figer)}")
        print("\n  Prochaine étape humaine : franchir le jalon « données publiables », puis monter la synthèse.")
        return 0
    finally:
        conn.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exemple", required=True, type=Path, help="dossier d'exemple (extraits figés synthétiques)")
    ap.add_argument("--periode", required=True, help="mois clôturé AAAA-MM")
    ap.add_argument("--aujourdhui", type=dt.date.fromisoformat, default=dt.date.today(), help="date du jour simulée (AAAA-MM-JJ)")
    ap.add_argument("--go", action="store_true", help="GO humain sur le mois, donné après lecture du pré-vol d'ouverture")
    ap.add_argument("--base", default=":memory:", help="fichier SQLite à conserver pour inspection (défaut : en mémoire)")
    ap.add_argument("--detail", action="store_true", help="afficher le détail de tous les contrôles, y compris conformes")
    ap.add_argument("--figer", type=Path, help="dossier où figer l'instantané des marts si la clôture est conforme")
    a = ap.parse_args(argv)
    return cloturer(a.exemple, a.periode, a.aujourdhui, a.go, a.base, a.detail, a.figer)


if __name__ == "__main__":
    sys.exit(main())

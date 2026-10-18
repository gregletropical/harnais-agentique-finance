"""Chargement des extraits figés dans la couche `raw_*`, et des référentiels versionnés dans `ref_*`.

Le système réel vit dans PostgreSQL, une couche par schéma (`raw`, `stg`, `mart`, `ctrl`) : le schéma
porte la couche, le nom de table ne la répète pas. SQLite n'a pas de schémas : la couche passe ici en
préfixe (`raw_cutoff` pour `raw.cutoff`). Chaque chargement est idempotent (DROP puis CREATE en
transaction) : le rejouer ne change rien.

Ordre imposé dans le réel, conservé ici : la source qui porte le seul contrôle bloquant au chargement
(le cutoff des projets, contrôlé contre les totaux de l'outil) passe EN PREMIER. S'il bloque, aucune
autre source n'est chargée, pour que la production ne mélange jamais deux mois.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from controles import commun as C
from controles import crm
from controles.controle_totaux_outil import controle_totaux_outil

# table -> (fichier d'exemple, colonnes typées)
SOURCES = {
    "raw_projets": ("outil_projets/projets.csv",
                    [("id_projet", "TEXT"), ("libelle", "TEXT"), ("client", "TEXT"), ("interne", "INTEGER"),
                     ("entite", "TEXT")]),
    "raw_cutoff": ("outil_projets/cutoff.csv",
                   [("periode", "TEXT"), ("entite", "TEXT"), ("id_projet", "TEXT"), ("ca", "REAL"), ("cout", "REAL")]),
    "raw_totaux_outil": ("outil_projets/totaux_outil.csv",
                         [("periode", "TEXT"), ("entite", "TEXT"), ("ca_produit", "REAL"), ("mb_produite", "REAL")]),
    "raw_factures": ("outil_projets/factures.csv",
                     [("numero", "TEXT"), ("date", "TEXT"), ("entite", "TEXT"), ("client", "TEXT"), ("devise", "TEXT"),
                      ("montant_devise", "REAL"), ("ht_eur", "REAL")]),
    "raw_achats": ("outil_projets/achats.csv",
                   [("id_ecriture", "TEXT"), ("date", "TEXT"), ("entite", "TEXT"), ("id_projet", "TEXT"),
                    ("fournisseur", "TEXT"), ("numero_facture", "TEXT"), ("bon_commande", "TEXT"), ("ht_eur", "REAL")]),
    "raw_grand_livre": ("compta/grand_livre.csv",
                        [("entite", "TEXT"), ("journal", "TEXT"), ("date", "TEXT"), ("piece", "TEXT"), ("compte", "TEXT"),
                         ("tiers", "TEXT"), ("libelle", "TEXT"), ("debit", "REAL"), ("credit", "REAL")]),
    "raw_livre_paie": ("paie/livre_paie.csv",
                       [("matricule", "TEXT"), ("mois", "TEXT"), ("rubrique", "TEXT"), ("montant", "REAL")]),
}
COLS_DEALS = [("id_deal", "TEXT"), ("titre", "TEXT"), ("organisation", "TEXT"), ("statut", "TEXT"), ("valeur", "REAL"),
              ("marge", "REAL"), ("probabilite", "REAL"), ("debut", "TEXT"), ("fin", "TEXT")]
REFERENTIELS = {
    "ref_taxonomie_pnl": ("taxonomie_pnl.csv", [("prefixe_compte", "TEXT"), ("poste_pnl", "TEXT"), ("sous_poste", "TEXT")]),
    "ref_passage_rubrique": ("passage_rubrique_compte.csv", [("rubrique", "TEXT"), ("compte", "TEXT"), ("libelle", "TEXT")]),
    "ref_groupes": ("groupes_clients.csv", [("id_groupe", "TEXT"), ("libelle", "TEXT"), ("segment", "TEXT"), ("cree_le", "TEXT")]),
    "ref_xref_client": ("xref_client_groupe.csv", [("client", "TEXT"), ("id_groupe", "TEXT"), ("source", "TEXT"), ("decision", "TEXT")]),
    "ref_ajustements": ("ajustements_cutoff.csv", [("periode", "TEXT"), ("id_projet", "TEXT"), ("delta_ca", "REAL"),
                                                  ("delta_cout", "REAL"), ("forme", "TEXT"), ("motif", "TEXT"), ("decision", "TEXT")]),
}


class ChargementBloque(RuntimeError):
    """Le contrôle bloquant du chargement a échoué : rien d'autre n'est chargé."""


creer_table = C.publier


def charger(conn: sqlite3.Connection, exemple: Path, periode: str, regles: Path = C.REGLES) -> list[C.Resultat]:
    """Charge référentiels et sources ; renvoie les résultats des contrôles de chargement.

    Lève `ChargementBloque` si le cutoff ne passe pas le contrôle des totaux de l'outil."""
    resultats = []
    for table, (fichier, cols) in REFERENTIELS.items():
        creer_table(conn, table, cols, C.regle(fichier, regles))

    # 1. Le cutoff d'abord, avec son contrôle bloquant
    for table in ("raw_projets", "raw_cutoff", "raw_totaux_outil"):
        fichier, cols = SOURCES[table]
        creer_table(conn, table, cols, C.lire_source(exemple, fichier))
    res = controle_totaux_outil(conn, periode, regles)
    resultats.append(res)
    if not res.ok:
        raise ChargementBloque(res.ligne() + "\n  " + "\n  ".join(res.details))

    # 2. Les autres sources
    for table in ("raw_factures", "raw_achats", "raw_grand_livre", "raw_livre_paie"):
        fichier, cols = SOURCES[table]
        creer_table(conn, table, cols, C.lire_source(exemple, fichier))

    # 3. Le CRM, corrigé par le registre d'anomalies (seules les lignes `ouvert` dont la source n'a pas bougé)
    deals, constats = crm.appliquer_registre(C.lire_source(exemple, "crm/deals.csv"), C.regle("registre_anomalies_crm.csv", regles))
    creer_table(conn, "raw_deals", COLS_DEALS, deals)
    resultats.append(C.Resultat("registre d'anomalies CRM", not constats,
                                f"{len(constats)} ligne(s) à repasser résolue(s)" if constats else "aucune correction périmée",
                                bloquant=False, details=constats))
    return resultats

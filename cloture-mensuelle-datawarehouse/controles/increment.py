"""Mise à jour incrémentale d'une table `raw_*` (delta à fenêtre glissante).

Une extraction complète de l'outil de gestion de projets coûte de longues minutes et sollicite une API
limitée en débit. Le mode delta ne réextrait que la fenêtre M-2..M (les mois récents
peuvent encore bouger) et remplace dans la table :
- toutes les lignes de la fenêtre (une ligne supprimée à la source disparaît aussi de la base) ;
- toutes les lignes dont la clé est dans le delta, même hors fenêtre (une correction rétroactive passe).
Après chargement, un contrôle vérifie que la fenêtre contient exactement les lignes du delta qui y tombent.

Garde-fous du réel conservés : un delta ne s'applique que sur une table déjà chargée en complet ; chaque
delta est chaîné à l'extrait précédemment chargé (registre des chargements), et un extrait extrait mais
jamais chargé est un « orphelin » que le pré-vol d'ouverture signale avant toute nouvelle extraction.
"""
from __future__ import annotations

import datetime as dt
import sqlite3


def debut_fenetre(periode: str, recouvrement: int = 2) -> dt.date:
    """'2026-03' -> 1er janvier 2026 (M-2) : premier jour de la fenêtre glissante."""
    a, m = map(int, periode.split("-"))
    m -= recouvrement
    while m < 1:
        a, m = a - 1, m + 12
    return dt.date(a, m, 1)


def remplacer(conn: sqlite3.Connection, table: str, colonnes: list[tuple[str, str]], lignes, fenetre: dict | None = None) -> dict:
    """Remplace dans `table` : tout (fenetre None), ou la fenêtre et les clés du delta.

    `fenetre` = {"colonne": nom, "depuis": 'AAAA-MM-JJ', "cle": [colonnes]}. À appeler dans une transaction
    ouverte par l'appelant. Renvoie {supprimees, inserees}."""
    lignes = [tuple(l) for l in lignes]
    noms = [c for c, _ in colonnes]
    if fenetre is None:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(f"CREATE TABLE {table} ({', '.join(f'{c} {t}' for c, t in colonnes)})")
        sup = 0
    else:
        if conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is None:
            raise RuntimeError(f"{table} absente : un delta ne s'applique que sur une table déjà chargée")
        col = fenetre["colonne"]
        sup = conn.execute(f"DELETE FROM {table} WHERE {col} >= ?", (str(fenetre["depuis"]),)).rowcount
        cle = fenetre.get("cle") or []
        if cle:
            idx = [noms.index(c) for c in cle]
            cond = " AND ".join(f"{c} = ?" for c in cle)
            for l in lignes:
                sup += conn.execute(f"DELETE FROM {table} WHERE {cond}", [l[i] for i in idx]).rowcount
    conn.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(noms))})", lignes)
    return {"supprimees": sup, "inserees": len(lignes)}


def controler(conn: sqlite3.Connection, table: str, fenetre: dict, attendu: int) -> None:
    """Après chargement : les lignes de la fenêtre sont exactement celles du delta qui y tombent."""
    n = conn.execute(f"SELECT count(*) FROM {table} WHERE {fenetre['colonne']} >= ?", (str(fenetre["depuis"]),)).fetchone()[0]
    if n != attendu:
        raise RuntimeError(f"{table} : {n} lignes dans la fenêtre après chargement, {attendu} attendues")

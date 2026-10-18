"""Outils communs : lecture des exemples, mois, paramètres, résultat d'un contrôle.

Dans le système réel, chaque source est lue par un connecteur API en lecture seule (GET uniquement),
écrite d'abord en « extrait figé » daté sur disque, puis chargée depuis cet extrait : deux chargements
du même extrait donnent la même base. Ici, l'extrait figé EST le dossier d'exemple : `lire_source`
remplace le connecteur, et aucun appel réseau n'existe dans ce dossier.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REGLES = RACINE / "regles"


# ---------------------------------------------------------------------------
# Résultat d'un contrôle
# ---------------------------------------------------------------------------

@dataclass
class Resultat:
    """Verdict d'un contrôle. `bloquant` dit si un échec arrête la diffusion ; un constat ne bloque pas."""
    nom: str
    ok: bool
    message: str
    bloquant: bool = True
    details: list[str] = field(default_factory=list)

    def ligne(self) -> str:
        etat = "OK     " if self.ok else ("ÉCHEC  " if self.bloquant else "CONSTAT")
        return f"{etat} {self.nom:<34} {self.message}"


# ---------------------------------------------------------------------------
# Mois
# ---------------------------------------------------------------------------

def fin_de_mois(periode: str) -> dt.date:
    a, m = map(int, periode.split("-"))
    return dt.date(a + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)


def decaler(periode: str, n: int) -> str:
    """'2026-03', -2 -> '2026-01'."""
    a, m = map(int, periode.split("-"))
    k = a * 12 + m - 1 + n
    return f"{k // 12}-{k % 12 + 1:02d}"


def mois_de(date_iso: str) -> str:
    return date_iso[:7]


def mois_entre(debut: str, fin: str) -> list[str]:
    out, m = [], debut
    while m <= fin:
        out.append(m)
        m = decaler(m, 1)
    return out


# ---------------------------------------------------------------------------
# Lecture des fichiers
# ---------------------------------------------------------------------------

def lire_csv(chemin: Path) -> list[dict]:
    if not chemin.exists():
        return []
    with chemin.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def regle(nom: str, regles: Path = REGLES) -> list[dict]:
    """Un référentiel versionné de `regles/` (registres, taxonomie, seeds MDM)."""
    return lire_csv(regles / nom)


def parametres(regles: Path = REGLES) -> dict:
    return json.loads((regles / "parametres.json").read_text(encoding="utf-8"))


def resoudre(exemple: Path, relatif: str) -> Path:
    """Chemin d'un fichier d'exemple, en suivant l'héritage d'une variante.

    Une variante (`variante.json` : {"herite_de": ...}) ne porte que les fichiers qui diffèrent de son
    parent : le lecteur voit d'un coup d'œil ce qui a été cassé volontairement."""
    exemple = Path(exemple)
    p = exemple / relatif
    if p.exists():
        return p
    v = exemple / "variante.json"
    if v.exists():
        parent = json.loads(v.read_text(encoding="utf-8"))["herite_de"]
        return resoudre(exemple.parent / parent, relatif)
    return p


def lire_source(exemple: Path, relatif: str) -> list[dict]:
    """Interface qui remplace un connecteur API : lit un extrait figé d'exemple."""
    return lire_csv(resoudre(exemple, relatif))


def lire_json(exemple: Path, relatif: str) -> dict:
    p = resoudre(exemple, relatif)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def eur(x, signe: bool = False) -> str:
    """Montant affiché au format français : espace des milliers, virgule décimale (« 53 000,00 », « +12,40 »)."""
    return (f"{float(x):+,.2f}" if signe else f"{float(x):,.2f}").replace(",", " ").replace(".", ",")


def f2(x) -> float:
    """Montant arrondi au centime (les CSV portent des chaînes)."""
    return round(float(x or 0), 2)


def publier(conn, table: str, colonnes: list[tuple[str, str]], lignes: list[dict]) -> int:
    """Remplace `table` par `lignes` (DROP, CREATE, INSERT) en une transaction : idempotent."""
    noms = [c for c, _ in colonnes]
    with conn:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(f"CREATE TABLE {table} ({', '.join(f'{c} {t}' for c, t in colonnes)})")
        conn.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(noms))})",
                         [tuple((r.get(c) if r.get(c) != "" else None) for c in noms) for r in lignes])
    return len(lignes)

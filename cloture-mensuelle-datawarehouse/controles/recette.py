"""Recette des marts : qualification des écarts et oracle M-1 (non-régression des mois passés).

**Une table est finie quand elle égale son oracle, vérifié par un harnais, jamais déclaré à la main.**
Dans le système réel, deux oracles se sont succédé : l'ancien entrepôt validé (pendant la migration),
puis l'instantané des marts figé à chaque fin de clôture. Ce module porte le second.

- **figer** (fin de clôture de P) : les marts sont copiés tels quels ; c'est l'oracle de la clôture de P+1.
- **comparer** (clôture de P+1) : sur tous les mois ANTÉRIEURS à P+1, les marts courants doivent égaler
  l'instantané de P. Un mois passé qui bouge est soit une décision (ajustement, version de cutoff),
  qualifiée au registre `regles/ecarts_snap_qualifies.csv` avec son montant et sa cause, soit une
  régression à rapporter.

Statut de chaque écart, au grain (mesure, clé) :
- ARRONDI      |écart| <= 0,02 ;
- QUALIFIE     une ligne du registre couvre l'écart : même mesure, clé conforme au motif `fnmatch`, écart
               égal au montant de la ligne à 0,02 près. **Le montant est obligatoire** : une ligne sans
               montant qualifierait « tout montant » et masquerait un vrai écart ; elle est refusée ;
- NON_QUALIFIE sinon : la recette échoue.
Une ligne du registre qui ne sert à rien est signalée : une cause périmée se retire.
"""
from __future__ import annotations

import fnmatch
import sqlite3
from pathlib import Path

from controles import commun as C

COLONNES_REGISTRE = ["mesure", "cle", "ecart", "cause"]


def valider_registre(lignes: list[dict]) -> list[dict]:
    erreurs = []
    for n, r in enumerate(lignes, start=2):
        if any(c not in r for c in COLONNES_REGISTRE):
            raise ValueError(f"registre d'écarts : colonnes attendues {COLONNES_REGISTRE}")
        try:
            float(r["ecart"])
        except (TypeError, ValueError):
            erreurs.append(f"ligne {n} ({r['cle']}) : ecart {r['ecart']!r} - montant obligatoire")
        if not (r.get("cause") or "").strip():
            erreurs.append(f"ligne {n} ({r['cle']}) : cause vide")
    if erreurs:
        raise ValueError("registre d'écarts refusé : " + " ; ".join(erreurs))
    return lignes


def qualifier(ecarts: list[dict], registre: list[dict], tol: float = 0.02) -> tuple[list[dict], list[str]]:
    """`ecarts` : {mesure, cle, ecart}. Renvoie (écarts avec statut et cause, causes orphelines du registre)."""
    servies = set()
    out = []
    for e in ecarts:
        if abs(e["ecart"]) <= tol:
            out.append({**e, "statut": "ARRONDI", "cause": ""})
            continue
        for i, r in enumerate(registre):
            if (r["mesure"] == e["mesure"] and fnmatch.fnmatchcase(e["cle"], r["cle"])
                    and abs(e["ecart"] - float(r["ecart"])) <= tol):
                out.append({**e, "statut": "QUALIFIE", "cause": r["cause"]})
                servies.add(i)
                break
        else:
            out.append({**e, "statut": "NON_QUALIFIE", "cause": ""})
    orphelines = [f"{r['mesure']} {r['cle']} : {r['cause']}" for i, r in enumerate(registre) if i not in servies]
    return out, orphelines


def ecarts_contre_instantane(courant: dict[tuple, tuple], instantane: dict[tuple, tuple]) -> list[dict]:
    """Écarts au grain (mois, groupe) pour chaque mesure ; une clé absente d'un côté vaut zéro."""
    out = []
    for cle in sorted(set(courant) | set(instantane)):
        a, b = courant.get(cle, (0.0, 0.0)), instantane.get(cle, (0.0, 0.0))
        for i, mesure in enumerate(("ca", "mb")):
            e = round(a[i] - b[i], 2)
            if e:
                out.append({"mesure": mesure, "cle": f"{cle[0]}|{cle[1]}", "ecart": e})
    return out


def comparer(conn: sqlite3.Connection, periode: str, exemple: Path, regles: Path = C.REGLES) -> C.Resultat:
    precedent = C.decaler(periode, -1)
    chemin = C.resoudre(exemple, f"snapshot/fct_ca_mensuel_{precedent}.csv")
    if not chemin.exists():
        return C.Resultat("oracle M-1", False, f"instantané de {precedent} absent : la clôture précédente n'a pas figé ses marts")
    inst = {(r["mois"], r["id_groupe"]): (C.f2(r["ca"]), C.f2(r["mb"])) for r in C.lire_csv(chemin) if r["mois"] < periode}
    cour = {(m, g): (round(ca, 2), round(mb, 2)) for m, g, ca, mb in conn.execute(
        "SELECT mois, COALESCE(id_groupe, '(sans groupe)'), ca, mb FROM mart_fct_ca_mensuel WHERE mois < ?", (periode,))}
    prm = C.parametres(regles)
    jug, orph = qualifier(ecarts_contre_instantane(cour, inst),
                          valider_registre(C.regle("ecarts_snap_qualifies.csv", regles)), prm["tolerance_arrondi_recette_eur"])
    nq = [e for e in jug if e["statut"] == "NON_QUALIFIE"]
    det = [f"{e['mesure']} {e['cle']} {C.eur(e['ecart'], signe=True)} -> {e['statut']} {e['cause']}" for e in jug]
    det += [f"[INFO] ligne de registre sans usage, à retirer si la cause est périmée : {o}" for o in orph]
    q = sum(e["statut"] == "QUALIFIE" for e in jug)
    return C.Resultat("oracle M-1", not nq,
                      f"{len(nq)} écart(s) NON qualifié(s) sur les mois passés" if nq
                      else f"mois passés inchangés ({q} écart(s) qualifié(s) au registre)", details=det)


def figer(conn: sqlite3.Connection, periode: str, sortie: Path) -> Path:
    """Fige `mart_fct_ca_mensuel` en CSV : l'oracle de la clôture suivante. Refuse d'écraser."""
    date_cloture = conn.execute("SELECT date_cloture FROM stg_date_cloture").fetchone()[0]
    if date_cloture != C.fin_de_mois(periode).isoformat():
        raise RuntimeError(f"date de clôture {date_cloture} : on ne fige pas un autre mois sous le nom de {periode}")
    cible = Path(sortie) / f"fct_ca_mensuel_{periode}.csv"
    if cible.exists():
        raise FileExistsError(f"{cible} existe déjà : instantané non écrasé")
    cible.parent.mkdir(parents=True, exist_ok=True)
    lignes = conn.execute("SELECT mois, id_groupe, ca, mb FROM mart_fct_ca_mensuel WHERE id_groupe IS NOT NULL ORDER BY 1, 2")
    cible.write_text("mois,id_groupe,ca,mb\n" + "".join(f"{m},{g},{ca:.2f},{mb:.2f}\n" for m, g, ca, mb in lignes), encoding="utf-8")
    return cible

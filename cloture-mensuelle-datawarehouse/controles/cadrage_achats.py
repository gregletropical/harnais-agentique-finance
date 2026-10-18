"""Cadrage mensuel des ACHATS de sous-traitance projet : outil de gestion de projets contre grand livre.

Porté d'un contrôle réel recetté à résiduel nul avant mise en production. Ce qui fait sa valeur :

- **appariement un pour un, par niveaux de preuve décroissants** (une pièce comptable ne sert qu'une
  fois, la preuve la plus forte passe d'abord) :
    N1 bon de commande ET numéro de facture retrouvés dans le libellé de la pièce ;
    N3 numéro de facture seul (normalisation bornée : « F 2026 011 » ne matche pas l'intérieur d'un autre) ;
    N2 bon de commande et montant à 5 % près ;
    N4 tiers et montant à 3 % près, à 45 jours au plus, sans contradiction de numéro de facture ;
    N5 numéro de facture retrouvé dans une AUTRE entité du groupe (achat comptabilisé chez la sœur) ;
- **qualification des non-appariés** : payé en banque mais jamais comptabilisé, écriture de l'outil sans
  facture (réallocation, estimation), absent de la comptabilité ; côté comptable, pièce sans écriture ;
- **périmètre déclaré, jamais implicite** (`regles/perimetre_cadrage_achats.csv`) : comptes et tiers de
  coûts indirects, projets internes. Ce qui sort du périmètre est publié avec la catégorie
  `hors_perimetre`, jamais effacé ;
- **tableau de passage** HT outil -> HT comptable 604, résidu inexpliqué nul attendu (le total comptable
  est lu dans le grand livre, pas reconstitué depuis les paires).
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3

from controles import commun as C

COLS_OUTIL = [("mois", "TEXT"), ("id_ecriture", "TEXT"), ("id_projet", "TEXT"), ("fournisseur", "TEXT"),
              ("numero_facture", "TEXT"), ("ht_eur", "REAL"), ("piece", "TEXT"), ("niveau_preuve", "TEXT"),
              ("ecart_ht", "REAL"), ("categories", "TEXT"), ("nature", "TEXT")]
COLS_COMPTA = [("mois", "TEXT"), ("piece", "TEXT"), ("tiers", "TEXT"), ("comptes_charge", "TEXT"), ("ht_604", "REAL"),
               ("id_ecriture", "TEXT"), ("categorie", "TEXT"), ("nature", "TEXT")]
COLS_PASSAGE = [("mois", "TEXT"), ("entite", "TEXT"), ("ligne", "TEXT"), ("montant", "REAL"), ("detail", "TEXT")]
NIVEAUX = ["N1_bc_facture", "N3_facture", "N2_bc", "N4_tiers_montant", "N5_facture_autre_entite"]


def nb(s) -> str:
    """Normalisation bornée : ' SG 2026 114 ' — un numéro ne matche pas l'intérieur d'un autre."""
    return " " + re.sub(r"[^A-Z0-9]+", " ", str(s or "").upper()).strip() + " "


def norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def jours(a: str, b: str) -> int:
    return abs((dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days)


def perimetre(regles) -> dict[str, set[str]]:
    out = {"compte": set(), "tiers": set(), "projet_interne": set()}
    for r in C.regle("perimetre_cadrage_achats.csv", regles):
        out.setdefault(r["type"], set()).add(r["valeur"])
    return out


def pieces_comptables(conn: sqlite3.Connection, prm: dict, perim: dict) -> list[dict]:
    """Pièces des journaux d'achats qui touchent la classe 604, avec leur statut de périmètre."""
    cpt = prm["comptes"]
    par_piece: dict[tuple, dict] = {}
    for ent, j, date, piece, compte, tiers, lib, d, c in conn.execute(
            "SELECT entite, journal, date, piece, compte, tiers, libelle, debit, credit FROM raw_grand_livre"):
        if j not in cpt["journaux_achats"]:
            continue
        p = par_piece.setdefault((ent, piece), {"entite": ent, "piece": piece, "date": date, "tiers": tiers or "",
                                                "txt": lib or "", "comptes": set(), "ht": 0.0, "ht_604": 0.0})
        if compte.startswith("6"):
            p["comptes"].add(compte)
            p["ht"] += d - c
            if compte.startswith(cpt["achats_perimetre"]):
                p["ht_604"] += d - c
    out = []
    for p in par_piece.values():
        if not any(c.startswith(cpt["achats_perimetre"]) for c in p["comptes"]):
            continue
        p["txt_n"] = nb(p["txt"])
        p["hors_perimetre"] = bool(p["comptes"] & perim["compte"]) or p["tiers"] in perim["tiers"]
        p["mois"] = p["date"][:7]
        out.append(p)
    return sorted(out, key=lambda p: (p["entite"], p["piece"]))


def apparier(F: list[dict], P: list[dict], prm: dict) -> dict[str, tuple[str, str]]:
    """Appariement un pour un par niveaux de preuve décroissants. Renvoie {id_ecriture: (piece, niveau)}."""
    a = prm["achats"]
    lmin = a["longueur_min_numero_facture"]
    m, utilisees = {}, set()
    connus = {nb(f["numero_facture"]) for f in F if len(norm(f["numero_facture"])) >= lmin}
    for niveau in NIVEAUX:
        for f in F:
            if f["id_ecriture"] in m:
                continue
            inv, bc, ht = nb(f["numero_facture"]), nb(f["bon_commande"]), f["ht_eur"]
            lg = len(norm(f["numero_facture"]))
            autre = niveau.startswith("N5")
            cands = [p for p in P if p["piece"] not in utilisees and ((p["entite"] != f["entite"]) if autre else (p["entite"] == f["entite"]))]
            if niveau.startswith("N1"):
                cands = [p for p in cands if norm(f["bon_commande"]) and bc in p["txt_n"] and lg >= 4 and inv in p["txt_n"]]
            elif niveau.startswith("N2"):
                cands = [p for p in cands if norm(f["bon_commande"]) and bc in p["txt_n"]
                         and abs(p["ht"] - ht) <= max(1, abs(ht) * a["ecart_relatif_bon_commande"])]
            elif niveau.startswith(("N3", "N5")):
                cands = [p for p in cands if lg >= lmin and inv in p["txt_n"]]
            else:
                fk = norm(f["fournisseur"])
                cands = [p for p in cands if len(fk) >= 3 and (fk in norm(p["tiers"]) or fk in norm(p["txt"]))
                         and abs(p["ht"] - ht) <= max(1, abs(ht) * a["ecart_relatif_tiers_montant"])
                         and jours(p["date"], f["date"]) <= a["jours_max_tiers_montant"]
                         # pas de contradiction : si la pièce porte un numéro connu de l'outil, ce doit être le sien
                         and all(k == inv or k not in p["txt_n"] for k in connus)]
            if cands:
                best = min(cands, key=lambda p: abs(p["ht"] - ht))
                m[f["id_ecriture"]] = (best["piece"], niveau)
                utilisees.add(best["piece"])
    return m


def calculer(conn: sqlite3.Connection, mois: str, prm: dict, regles=C.REGLES):
    tol = prm["tolerance_achats_eur"]
    perim = perimetre(regles)
    internes = {r[0] for r in conn.execute("SELECT id_projet FROM raw_projets WHERE interne = 1")}
    fenetre = {C.decaler(mois, k) for k in (-2, -1, 0, 1, 2)}
    F = [dict(zip(("id_ecriture", "date", "entite", "id_projet", "fournisseur", "numero_facture", "bon_commande", "ht_eur"), r))
         for r in conn.execute("SELECT id_ecriture, date, entite, id_projet, fournisseur, numero_facture, bon_commande, ht_eur "
                               "FROM raw_achats ORDER BY id_ecriture")]
    F = [f for f in F if f["date"][:7] in fenetre]
    for f in F:
        f["hors_perimetre"] = f["id_projet"] in internes and "*" in perim["projet_interne"]
    P = [p for p in pieces_comptables(conn, prm, perim) if p["mois"] in fenetre]
    m = apparier([f for f in F if not f["hors_perimetre"]], [p for p in P if not p["hors_perimetre"]], prm)
    Pi = {p["piece"]: p for p in P}
    banque = [r for r in conn.execute("SELECT entite, journal, date, compte, libelle, debit, credit FROM raw_grand_livre")
              if r[1] in prm["comptes"]["journaux_banque"] and r[3].startswith(prm["comptes"]["fournisseurs"])]

    lignes_outil = []
    for f in (f for f in F if f["date"][:7] == mois):
        piece, niveau = m.get(f["id_ecriture"], (None, None))
        p = Pi.get(piece)
        cats = []
        if f["hors_perimetre"]:
            cats.append("hors_perimetre (projet interne de frais généraux)")
        elif p is None:
            inv = nb(f["numero_facture"])
            paye = [b for b in banque if b[0] == f["entite"] and len(norm(f["numero_facture"])) >= 5 and inv in nb(b[4])]
            if paye:
                cats.append(f"O_seul:paye_non_comptabilise ({paye[0][2]}, {C.eur(sum(b[5] - b[6] for b in paye))} TTC en banque)")
            elif not norm(f["numero_facture"]):
                cats.append("O_seul:ecriture_sans_facture (réallocation ou estimation dans l'outil)")
            else:
                cats.append("O_seul:absent_compta")
        else:
            if p["entite"] != f["entite"]:
                cats.append("entite_differente")
            e = round(f["ht_eur"] - p["ht"], 2)
            cats.append("identique" if abs(e) <= tol else f"ecart_montant ({C.eur(e, signe=True)})")
            if p["mois"] != mois:
                cats.append(f"ecart_periode (comptabilité {p['mois']})")
            if not all(c.startswith(prm["comptes"]["achats_perimetre"]) for c in p["comptes"]):
                cats.append(f"ecart_compte ({','.join(sorted(p['comptes']))})")
        nature = ("hors_perimetre" if f["hors_perimetre"] else "ok" if cats == ["identique"] else "a_instruire")
        lignes_outil.append({"mois": mois, "id_ecriture": f["id_ecriture"], "id_projet": f["id_projet"],
                             "fournisseur": f["fournisseur"], "numero_facture": f["numero_facture"], "ht_eur": f["ht_eur"],
                             "piece": piece, "niveau_preuve": niveau,
                             "ecart_ht": round(f["ht_eur"] - p["ht"], 2) if p else None,
                             "categories": " ; ".join(cats), "nature": nature, "_entite": f["entite"]})

    inverse = {piece: (fid, niveau) for fid, (piece, niveau) in m.items()}
    mois_f = {f["id_ecriture"]: f["date"][:7] for f in F}
    lignes_compta = []
    for p in (p for p in P if p["mois"] == mois):
        fid = inverse.get(p["piece"], (None, None))[0]
        if p["hors_perimetre"]:
            cat, nature = "hors_perimetre (compte ou tiers de coût indirect)", "hors_perimetre"
        elif fid is None:
            cat, nature = "C_seul : pièce sans écriture dans l'outil", "a_instruire"
        elif mois_f[fid] != mois:
            cat, nature = f"ecart_periode (outil {mois_f[fid]})", "a_instruire"
        else:
            cat, nature = "apparie", "ok"
        lignes_compta.append({"mois": mois, "piece": p["piece"], "tiers": p["tiers"], "comptes_charge": ",".join(sorted(p["comptes"])),
                              "ht_604": round(p["ht_604"], 2), "id_ecriture": fid, "categorie": cat, "nature": nature,
                              "_entite": p["entite"]})
    return lignes_outil, lignes_compta, passage(conn, lignes_outil, lignes_compta, Pi, mois, prm, perim)


def passage(conn, lo, lc, Pi, mois, prm, perim) -> list[dict]:
    cpt = prm["comptes"]
    rows = []
    for ent in sorted({l["_entite"] for l in lo + lc}):
        o = [l for l in lo if l["_entite"] == ent and l["nature"] != "hors_perimetre"]
        c = [l for l in lc if l["_entite"] == ent and l["nature"] != "hors_perimetre"]

        def R(lib, v, det=""):
            rows.append({"mois": mois, "entite": ent, "ligne": lib, "montant": round(v, 2), "detail": det})
        R("1. HT outil du mois (périmètre)", sum(l["ht_eur"] for l in o))
        x = [l for l in o if l["piece"] is None]
        R("2. - écritures de l'outil sans pièce comptable", -sum(l["ht_eur"] for l in x), ",".join(l["id_ecriture"] for l in x))
        x = [l for l in o if l["piece"] and Pi[l["piece"]]["mois"] != mois]
        R("3. - écritures de M comptabilisées un autre mois", -sum(l["ht_eur"] for l in x), ",".join(l["id_ecriture"] for l in x))
        x = [l for l in c if l["categorie"].startswith("ecart_periode")]
        R("4. + pièces de M rattachées à une écriture d'un autre mois", sum(l["ht_604"] for l in x), ",".join(l["piece"] for l in x))
        x = [l for l in o if l["piece"] and Pi[l["piece"]]["mois"] == mois]
        R("5. +/- écarts de montant HT des paires", sum(Pi[l["piece"]]["ht_604"] - l["ht_eur"] for l in x),
          ",".join(l["id_ecriture"] for l in x if abs(Pi[l["piece"]]["ht_604"] - l["ht_eur"]) > 0.005))
        x = [l for l in c if l["categorie"].startswith("C_seul")]
        R("6. + pièces comptables sans écriture dans l'outil", sum(l["ht_604"] for l in x), ",".join(l["piece"] for l in x))
        # total comptable lu dans le grand livre, indépendamment des paires
        gl, hors = 0.0, 0.0
        for e, j, date, compte, tiers, d, cr in conn.execute(
                "SELECT entite, journal, date, compte, tiers, debit, credit FROM raw_grand_livre WHERE entite = ?", (ent,)):
            if j in cpt["journaux_achats"] and compte.startswith(cpt["achats_perimetre"]) and date[:7] == mois:
                if compte in perim["compte"] or (tiers or "") in perim["tiers"]:
                    hors += d - cr
                else:
                    gl += d - cr
        R("7. = HT comptable en 604 du mois (périmètre)", gl)
        calc = sum(r["montant"] for r in rows if r["entite"] == ent and r["ligne"][:1] in "123456")
        R("   contrôle : résidu inexpliqué (7 - somme 1..6)", gl - calc)
        R("   pour mémoire : HT en 604 hors périmètre", hors)
    return rows


def executer(conn: sqlite3.Connection, mois: str, prm: dict, regles=C.REGLES) -> list[C.Resultat]:
    lo, lc, pas = calculer(conn, mois, prm, regles)
    C.publier(conn, "ctrl_cadrage_achats_outil", COLS_OUTIL, lo)
    C.publier(conn, "ctrl_cadrage_achats_compta", COLS_COMPTA, lc)
    C.publier(conn, "ctrl_cadrage_achats_passage", COLS_PASSAGE, pas)
    residus = [r for r in pas if "résidu" in r["ligne"] and abs(r["montant"]) > 0.01]
    instr = [l for l in lo if l["nature"] == "a_instruire"] + [l for l in lc if l["nature"] == "a_instruire"]
    hors = sum(l["nature"] == "hors_perimetre" for l in lo + lc)
    det = [f"{l.get('id_ecriture') or l.get('piece')} : {l.get('categories') or l.get('categorie')}" for l in instr]
    det += [f"{l['id_ecriture']} apparié à {l['piece']} au niveau {l['niveau_preuve']}" for l in lo if l["piece"]]
    return [
        C.Resultat("cadrage achats : résidu du passage", not residus,
                   "résidu nul" if not residus else "résidu non nul : " + ", ".join(
                       "{} {}".format(r["entite"], C.eur(r["montant"], signe=True)) for r in residus),
                   details=[f"{r['ligne']:<75} {C.eur(r['montant']):>12}  {r['detail']}" for r in pas]),
        C.Resultat("cadrage achats : écritures à instruire", not instr,
                   f"{len(lo)} écriture(s) outil, {len(lc)} pièce(s) comptable(s), {len(instr)} à instruire, {hors} hors périmètre",
                   bloquant=False, details=det),
    ]

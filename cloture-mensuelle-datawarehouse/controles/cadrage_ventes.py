"""Cadrage mensuel des VENTES : factures de l'outil de gestion de projets contre journal des ventes.

Méthode (portée d'un contrôle réel, recetté à résiduel nul sur deux mois avant mise en production) :

- pièces de l'outil = son export comptable (HT en EUR, au taux fixe de l'export pour les devises) ;
- pièces comptables = pièces des journaux de ventes (HT = classe 70, TVA = 4457, TTC = 411) ;
- rapprochement pièce à pièce sur (entité, numéro de facture), sur une fenêtre M-1..M+1 pour attraper
  les décalages de période ; tolérance d'arrondi 0,05 EUR ;
- qualification de chaque pièce : OK | METHODE (écart compris et admis : change, arrondi) | INSTRUIRE ;
- tableau de passage HT outil -> HT comptable, dont le **résidu inexpliqué doit être nul**. Le total
  comptable est lu directement dans le grand livre, pas reconstitué depuis les paires : une pièce que le
  rapprochement n'a pas vue fait apparaître un résidu, et un résidu non nul veut dire que le contrôle
  lui-même est faux (bloquant).

Les pièces à instruire sont des CONSTATS : elles se présentent à l'humain à la porte de publication, qui
les arbitre. Non porté : les produits à recevoir et constatés d'avance, qui relèvent de la clôture
comptable et non du cadrage.
"""
from __future__ import annotations

import re
import sqlite3

from controles import commun as C

NUM = re.compile(r"\bF-\d{4}-\d{3,}\b")
COLS_PIECES = [("mois", "TEXT"), ("entite", "TEXT"), ("numero", "TEXT"), ("presence", "TEXT"), ("f_date", "TEXT"),
               ("p_date", "TEXT"), ("devise", "TEXT"), ("f_ht", "REAL"), ("p_ht", "REAL"), ("ecart_ht", "REAL"),
               ("categories", "TEXT"), ("niveau", "TEXT")]
COLS_PASSAGE = [("mois", "TEXT"), ("entite", "TEXT"), ("ligne", "TEXT"), ("montant", "REAL"), ("detail", "TEXT")]


def pieces_comptables(conn: sqlite3.Connection, mois: list[str], prm: dict) -> dict:
    """{(entite, numero): {date, ht, tva, ttc, autre}} des journaux de ventes sur les mois donnés."""
    cpt = prm["comptes"]
    out = {}
    q = f"""SELECT entite, piece, libelle, date, compte, debit, credit FROM raw_grand_livre
            WHERE journal IN ({','.join('?' * len(cpt['journaux_ventes']))})"""
    for ent, piece, lib, date, compte, d, c in conn.execute(q, cpt["journaux_ventes"]):
        if date[:7] not in mois:
            continue
        m = NUM.search(f"{piece} {lib}")
        if not m:
            continue
        p = out.setdefault((ent, m.group(0)), {"date": date, "ht": 0.0, "tva": 0.0, "ttc": 0.0, "autre": 0.0})
        if compte.startswith(cpt["ventes_ht"]):
            p["ht"] += c - d
        elif compte.startswith(cpt["ventes_tva"]):
            p["tva"] += c - d
        elif compte.startswith(cpt["clients"]):
            p["ttc"] += d - c
        else:
            p["autre"] += c - d
    return out


def qualifier(f: dict | None, p: dict | None, mois: str, tol: float) -> tuple[list[str], str]:
    """Catégories et niveau d'une pièce rapprochée (pur)."""
    if p is None:
        return ["outil_seul : facture exportée par l'outil, absente des journaux de ventes de M-1..M+1"], "INSTRUIRE"
    if f is None:
        return ["compta_seul : pièce de ventes sans facture dans l'outil"], "INSTRUIRE"
    cats, niv = [], []
    if f["date"][:7] != p["date"][:7]:
        cats.append(f"ecart_periode : {f['date']} dans l'outil, {p['date']} en comptabilité"); niv.append("INSTRUIRE")
    e = round(p["ht"] - f["ht_eur"], 2)
    if abs(e) > tol:
        if f["devise"] != "EUR" and abs(e) <= 0.02 * abs(f["ht_eur"]):
            cats.append(f"ecart_change : {f['devise']} {C.eur(f['montant_devise'])}, export au taux fixe ({C.eur(f['ht_eur'])}), "
                        f"comptabilité au taux de la facture ({C.eur(p['ht'])})"); niv.append("METHODE")
        elif f["devise"] == "EUR" and abs(e) <= 1.0:
            cats.append("ecart_montant : arrondi"); niv.append("METHODE")
        else:
            cats.append(f"ecart_montant : HT {C.eur(e, signe=True)}"); niv.append("INSTRUIRE")
    if abs(p["autre"]) > 0.005:
        cats.append(f"ecart_compte : {C.eur(p['autre'])} de HT imputé hors classe 70"); niv.append("INSTRUIRE")
    if not cats:
        return ["identique"], "OK"
    return cats, ("INSTRUIRE" if "INSTRUIRE" in niv else "METHODE")


def calculer(conn: sqlite3.Connection, mois: str, prm: dict) -> tuple[list[dict], list[dict]]:
    tol = prm["tolerance_ventes_eur"]
    fenetre = [C.decaler(mois, -1), mois, C.decaler(mois, 1)]
    P = pieces_comptables(conn, fenetre, prm)
    F = {(r[0], r[1]): {"date": r[2], "devise": r[3], "montant_devise": r[4], "ht_eur": r[5]} for r in conn.execute(
        "SELECT entite, numero, date, devise, montant_devise, ht_eur FROM raw_factures")
        if r[2][:7] in fenetre}
    pieces = []
    for cle in sorted(set(F) | set(P)):
        f, p = F.get(cle), P.get(cle)
        if mois not in {(f or {}).get("date", "")[:7], (p or {}).get("date", "")[:7]}:
            continue
        cats, niv = qualifier(f, p, mois, tol)
        pieces.append({"mois": mois, "entite": cle[0], "numero": cle[1],
                       "presence": "deux" if f and p else ("outil_seul" if f else "compta_seul"),
                       "f_date": f and f["date"], "p_date": p and p["date"], "devise": f and f["devise"],
                       "f_ht": f and round(f["ht_eur"], 2), "p_ht": p and round(p["ht"], 2),
                       "ecart_ht": round(p["ht"] - f["ht_eur"], 2) if f and p else None,
                       "categories": " ; ".join(cats), "niveau": niv})
    return pieces, passage(conn, pieces, mois, prm)


def passage(conn: sqlite3.Connection, pieces: list[dict], mois: str, prm: dict) -> list[dict]:
    cpt = prm["comptes"]
    rows = []
    for ent in sorted({p["entite"] for p in pieces} | {r[0] for r in conn.execute("SELECT DISTINCT entite FROM raw_grand_livre")}):
        x = [p for p in pieces if p["entite"] == ent]
        fm = lambda p: (p["f_date"] or "")[:7] == mois
        pm = lambda p: (p["p_date"] or "")[:7] == mois

        def R(lib, v, det=""):
            rows.append({"mois": mois, "entite": ent, "ligne": lib, "montant": round(v, 2), "detail": det})

        def S(sel, fn):
            return sum(fn(p) for p in x if sel(p)), ",".join(p["numero"] for p in x if sel(p))

        R("1. HT outil en EUR (factures datées M)", *S(fm, lambda p: p["f_ht"]))
        R("2. - factures de l'outil absentes de la comptabilité", *S(lambda p: fm(p) and p["presence"] == "outil_seul", lambda p: -p["f_ht"]))
        R("3. - factures de M comptabilisées un autre mois", *S(lambda p: fm(p) and p["presence"] == "deux" and not pm(p), lambda p: -p["f_ht"]))
        R("4. + factures d'un autre mois comptabilisées en M", *S(lambda p: pm(p) and p["presence"] == "deux" and not fm(p), lambda p: p["p_ht"]))
        deux_m = lambda p: fm(p) and pm(p) and p["presence"] == "deux"
        R("5a. +/- change : taux de la facture contre taux fixe de l'export (méthode)",
          *S(lambda p: deux_m(p) and "ecart_change" in p["categories"], lambda p: p["p_ht"] - p["f_ht"]))
        autres = [p for p in x if deux_m(p) and "ecart_change" not in p["categories"]]
        R("5b. +/- autres écarts de montant HT", sum(p["p_ht"] - p["f_ht"] for p in autres),
          ",".join(p["numero"] for p in autres if abs(p["p_ht"] - p["f_ht"]) > 0.005))
        R("6. + pièces de ventes sans facture dans l'outil", *S(lambda p: pm(p) and p["presence"] == "compta_seul", lambda p: p["p_ht"]))
        vt = sum(c - d for j, compte, d, c, date in conn.execute(
            "SELECT journal, compte, debit, credit, date FROM raw_grand_livre WHERE entite = ?", (ent,))
            if j in cpt["journaux_ventes"] and compte.startswith(cpt["ventes_ht"]) and date[:7] == mois)
        R("7. = HT comptable des journaux de ventes (classe 70)", vt)
        calc = sum(r["montant"] for r in rows if r["entite"] == ent and r["ligne"][:2].rstrip(".ab") in {"1", "2", "3", "4", "5", "6"})
        R("   contrôle : résidu inexpliqué (7 - somme 1..6)", vt - calc)
        hors = sum(c - d for j, compte, d, c, date in conn.execute(
            "SELECT journal, compte, debit, credit, date FROM raw_grand_livre WHERE entite = ?", (ent,))
            if j not in cpt["journaux_ventes"] and compte.startswith(cpt["ventes_ht"]) and date[:7] == mois)
        R("8. + écritures de classe 70 hors journaux de ventes", hors)
        R("9. = solde du grand livre en classe 70 du mois", vt + hors)
    return rows


def executer(conn: sqlite3.Connection, mois: str, prm: dict) -> list[C.Resultat]:
    pieces, pas = calculer(conn, mois, prm)
    C.publier(conn, "ctrl_cadrage_ventes_pieces", COLS_PIECES, pieces)
    C.publier(conn, "ctrl_cadrage_ventes_passage", COLS_PASSAGE, pas)
    residus = [r for r in pas if "résidu" in r["ligne"] and abs(r["montant"]) > 0.01]
    instr = [p for p in pieces if p["niveau"] == "INSTRUIRE"]
    meth = [p for p in pieces if p["niveau"] == "METHODE"]
    return [
        C.Resultat("cadrage ventes : résidu du passage", not residus,
                   "résidu nul" if not residus else "résidu non nul : " + ", ".join(
                       "{} {}".format(r["entite"], C.eur(r["montant"], signe=True)) for r in residus),
                   details=[f"{r['ligne']:<75} {C.eur(r['montant']):>12}  {r['detail']}" for r in pas]),
        C.Resultat("cadrage ventes : pièces à instruire", not instr,
                   f"{len(pieces)} pièce(s), {len(instr)} à instruire, {len(meth)} écart(s) de méthode", bloquant=False,
                   details=[f"{p['numero']} [{p['niveau']}] {p['categories']}" for p in instr + meth]),
    ]

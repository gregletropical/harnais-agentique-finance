#!/usr/bin/env python3
"""
prevol.py — Outillage du protocole de pré-vol (instructions/protocole-prevol.md) :
recherche de précédents (porte 2), état avant (porte 4), contrôles bloquants (porte 6)
et génération du pré-rapport que l'utilisateur valide (porte 8).

Architecture en cinq primitives, pour rester portable d'un ERP à l'autre : le protocole
(8 portes + contrôle après) ne change pas, seul l'adaptateur change.

    chercher_precedents(spec)   -> porte 2
    lire_etat(spec)             -> porte 4
    simuler(spec)               -> porte 5 — DÉLIBÉRÉMENT NON IMPLÉMENTÉE
    controles_bloquants(spec)   -> porte 6
    relire(piece)               -> contrôle a posteriori (porte 9)

`simuler` n'est pas implémentée par choix : l'outil de pré-vol est incapable d'écrire,
par construction et pas seulement par discipline. La création du brouillon et sa
comptabilisation restent un geste distinct, vérifié ensuite par `relire`.

En production, l'adaptateur interroge l'ERP en lecture seule. Ici, `AdaptateurFichier`
lit un grand livre synthétique (exemples/prevol/grand_livre.json).

Usage :
  python controles/prevol.py exemples/prevol/demande_ecart_reglement.json
  python controles/prevol.py exemples/prevol/demande_correction_anterieure.json
Code de sortie : 0 si tous les contrôles bloquants passent, 1 sinon.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

RACINE = Path(__file__).resolve().parents[1]

# --------------------------------------------------------------------------- #
# Structures
# --------------------------------------------------------------------------- #


@dataclass
class Precedent:
    piece: str
    date: str
    tiers: str
    montant: float
    lettrage: str
    auteur: str = ""
    source: str = "grand livre (lecture seule)"


@dataclass
class EtatCompte:
    compte: str
    libelle: str
    solde: float
    attendu: str = ""


@dataclass
class EtatAvant:
    comptes: list[EtatCompte] = field(default_factory=list)
    verrous: dict[str, Any] = field(default_factory=dict)
    journal: dict[str, Any] | None = None
    lu_le: str = ""


@dataclass
class ControleResultat:
    nom: str
    statut: str  # "ok" | "fail" | "na" | "manuel"
    detail: str


@dataclass
class LigneEcriture:
    compte: str
    libelle: str
    debit: float = 0.0
    credit: float = 0.0


@dataclass
class OperationSpec:
    """Ce que l'agent connaît de l'opération projetée : l'entrée du pré-vol."""
    societe: str
    societe_id: int
    type_geste: str
    comptes: list[str]
    date: str
    tiers: str | None = None
    tiers_id: int | None = None
    ref: str | None = None
    montant: float | None = None
    journal_id: int | None = None
    lignes: list[LigneEcriture] = field(default_factory=list)
    lettrage_groupe_ids: list[int] = field(default_factory=list)
    besoin_metier: str | None = None
    lettrage_partiel_delibere: bool = False


class AdaptateurPrevol(Protocol):
    def chercher_precedents(self, spec: OperationSpec, limit: int = 10) -> list[Precedent]: ...
    def lire_etat(self, spec: OperationSpec) -> EtatAvant: ...
    def controles_bloquants(self, spec: OperationSpec) -> list[ControleResultat]: ...
    def relire(self, piece: str, societe_id: int) -> dict[str, Any]: ...
    def simuler(self, spec: OperationSpec) -> None: ...


# --------------------------------------------------------------------------- #
# Fonctions pures : le coeur des contrôles bloquants
# --------------------------------------------------------------------------- #


def equilibre(lignes: list[LigneEcriture]) -> tuple[bool, float, float]:
    """Débit = crédit. Retourne (ok, total débit, total crédit)."""
    td = round(sum(l.debit for l in lignes), 2)
    tc = round(sum(l.credit for l in lignes), 2)
    return abs(td - tc) < 0.005, td, tc


def exercice_ouvert(date_ecriture: str, verrou: str | None, verrou_dur: str | None,
                    exercice_en_cours: int) -> tuple[bool, str]:
    """Le plus restrictif entre les verrous de l'ERP ET la règle absolue « on n'écrit que sur
    l'exercice en cours ». L'absence de verrou technique n'est jamais une autorisation : une
    correction antérieure passe par une extourne sur l'exercice courant."""
    d = date_cls.fromisoformat(date_ecriture)
    if d.year != exercice_en_cours:
        return False, (f"date {date_ecriture} hors exercice en cours ({exercice_en_cours}) — règle absolue : "
                       "on n'écrit que sur l'exercice en cours, une correction antérieure passe par une "
                       "extourne sur l'exercice courant")
    for nom, v in (("verrou d'exercice", verrou), ("verrou dur", verrou_dur)):
        if v and d <= date_cls.fromisoformat(v):
            return False, f"date {date_ecriture} <= {nom} au {v}"
    return True, f"exercice {exercice_en_cours} ouvert" + (f", verrou au {verrou}" if verrou else "")


def lettrage_solde_zero(soldes: list[float]) -> tuple[bool, float]:
    """Garde-fou de lettrage : le groupe à lettrer doit solder EXACTEMENT à 0."""
    total = round(sum(soldes), 2)
    return abs(total) < 0.005, total


def correspond_doublon(piece: dict, ref: str | None, tiers_id: int | None, montant: float | None) -> bool:
    """Anti-doublon : même référence, ou même tiers ET même montant — tous états confondus."""
    if ref and piece.get("ref") and ref.strip().upper() in piece["ref"].upper():
        return True
    return (tiers_id is not None and montant is not None and piece.get("tiers_id") == tiers_id
            and round(piece.get("montant", 0), 2) == round(montant, 2))


# --------------------------------------------------------------------------- #
# Adaptateur fichier (remplace l'adaptateur ERP, non publié)
# --------------------------------------------------------------------------- #


class AdaptateurFichier:
    """Implémente AdaptateurPrevol sur un grand livre JSON synthétique. Lecture seule."""

    def __init__(self, grand_livre: dict, lu_le: str | None = None):
        self.gl = grand_livre
        self.lu_le = lu_le or datetime.now().strftime("%Y-%m-%d %H:%M")

    @classmethod
    def depuis_fichier(cls, chemin: str | Path, lu_le: str | None = None) -> "AdaptateurFichier":
        return cls(json.loads(Path(chemin).read_text(encoding="utf-8")), lu_le)

    def _societe(self, sid: int) -> dict:
        return self.gl["societes"][str(sid)]

    def chercher_precedents(self, spec: OperationSpec, limit: int = 10) -> list[Precedent]:
        lignes = [l for l in self.gl["ecritures"] if l["societe_id"] == spec.societe_id
                  and l["compte"] in spec.comptes and (spec.tiers_id is None or l.get("tiers_id") == spec.tiers_id
                                                      or l["compte"] not in ("411000", "401000"))]
        lignes.sort(key=lambda l: l["date"], reverse=True)
        return [Precedent(piece=l["piece"], date=l["date"], tiers=l.get("tiers") or "—",
                          montant=round(l["debit"] - l["credit"], 2), lettrage=l.get("lettrage") or "non lettré",
                          auteur=l.get("auteur", "")) for l in lignes[:limit]]

    def lire_etat(self, spec: OperationSpec) -> EtatAvant:
        comptes = []
        for code in spec.comptes:
            ls = [l for l in self.gl["ecritures"] if l["societe_id"] == spec.societe_id
                  and l["compte"] == code and l["date"] <= spec.date]
            libelle = self.gl.get("plan_comptable", {}).get(code, "?")
            comptes.append(EtatCompte(code, libelle, round(sum(l["debit"] - l["credit"] for l in ls), 2)))
        s = self._societe(spec.societe_id)
        verrous = {k: s[k] for k in ("verrou", "verrou_dur") if s.get(k)}
        journal = self.gl.get("journaux", {}).get(str(spec.journal_id)) if spec.journal_id else None
        return EtatAvant(comptes, verrous, journal, self.lu_le)

    def controles_bloquants(self, spec: OperationSpec) -> list[ControleResultat]:
        res = []
        s = self._societe(spec.societe_id)
        ok, detail = exercice_ouvert(spec.date, s.get("verrou"), s.get("verrou_dur"), s["exercice_en_cours"])
        res.append(ControleResultat("exercice ouvert (et exercice EN COURS)", "ok" if ok else "fail", detail))

        if spec.ref or (spec.tiers_id is not None and spec.montant is not None):
            trouves = [p for p in self.gl.get("pieces", []) if p["societe_id"] == spec.societe_id
                       and correspond_doublon(p, spec.ref, spec.tiers_id, spec.montant)]
            res.append(ControleResultat(
                "anti-doublon", "fail" if trouves else "ok",
                f"{len(trouves)} pièce(s) correspondante(s), tous états confondus"
                + (" : " + ", ".join(f"{p['nom']} ({p['etat']})" for p in trouves) if trouves else "")))
        else:
            res.append(ControleResultat("anti-doublon", "manuel",
                                        "ni référence ni (tiers + montant) : à vérifier à la main au grand livre"))

        if spec.lignes:
            ok, td, tc = equilibre(spec.lignes)
            res.append(ControleResultat("équilibre débit = crédit", "ok" if ok else "fail",
                                        f"débit {td:.2f} / crédit {tc:.2f}"))
        else:
            res.append(ControleResultat("équilibre débit = crédit", "manuel", "aucune ligne fournie"))

        if spec.lettrage_groupe_ids:
            ouvertes = self.gl.get("lignes_ouvertes", {})
            soldes = [ouvertes[str(i)] for i in spec.lettrage_groupe_ids if str(i) in ouvertes]
            if len(soldes) != len(spec.lettrage_groupe_ids):
                res.append(ControleResultat("garde-fou lettrage (groupe = 0)", "fail",
                                            "ligne(s) du groupe introuvable(s) ou déjà lettrée(s)"))
            else:
                # Le groupe se lettre APRÈS comptabilisation de l'écriture proposée : on
                # ajoute ses lignes sur le compte de tiers au groupe.
                tiers = [l.debit - l.credit for l in spec.lignes if l.compte.startswith(("411", "401"))]
                ok, total = lettrage_solde_zero(soldes + tiers)
                detail = f"solde du groupe, écriture proposée comprise = {total:.2f}"
                if spec.lettrage_partiel_delibere:
                    detail += " — lettrage partiel DÉLIBÉRÉ demandé : à justifier dans le pré-rapport"
                res.append(ControleResultat("garde-fou lettrage (groupe = 0)",
                                            "ok" if ok or spec.lettrage_partiel_delibere else "fail", detail))
        else:
            res.append(ControleResultat("garde-fou lettrage (groupe = 0)", "na", "pas de lettrage"))

        res.append(ControleResultat("cohérence de TVA", "manuel",
                                    "non automatisé : vérifier le régime réel du tiers (marge, exonération, "
                                    "non-déductibilité) avant de valider"))
        return res

    def relire(self, piece: str, societe_id: int) -> dict[str, Any]:
        ls = [l for l in self.gl["ecritures"] if l["piece"] == piece and l["societe_id"] == societe_id]
        return {"trouve": bool(ls), "piece": piece, "lignes": ls}

    def simuler(self, spec: OperationSpec) -> None:
        raise NotImplementedError("simuler() n'est pas implémentée par choix : l'outil de pré-vol doit rester "
                                  "incapable d'écrire. Le brouillon est un geste distinct, vérifié par relire().")


# --------------------------------------------------------------------------- #
# Pré-rapport (fonction pure)
# --------------------------------------------------------------------------- #


def _m(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",")


def _table_precedents(precedents: list[Precedent]) -> str:
    if not precedents:
        return ("**AUCUN PRÉCÉDENT TROUVÉ** — périmètre cherché : comptes et société de la demande, au grand livre — "
                "légitimité : **À DOCUMENTER À LA MAIN**. Une absence de précédent est un signal d'alerte, pas une "
                "formalité : sur une comptabilité tenue depuis des années, c'est bien plus souvent le signe d'un "
                "problème mal cadré que d'une vraie première.")
    L = ["| pièce | date | tiers | montant | lettrage | auteur |", "|---|---|---|---|---|---|"]
    L += [f"| {p.piece} | {p.date} | {p.tiers} | {_m(p.montant)} | {p.lettrage} | {p.auteur or '—'} |"
          for p in precedents]
    L += ["", f"**{len(precedents)} précédent(s) listé(s) automatiquement, à relire un par un.** Vérifier qu'au moins "
              "un provient de l'auteur d'origine du process, pas seulement d'une reproduction récente par l'agent : "
              "un précédent qu'on a soi-même écrit ne prouve rien."]
    return "\n".join(L)


def _table_etat(etat: EtatAvant) -> str:
    L = ["| Compte | Libellé | Solde | Attendu |", "|---|---|---|---|"]
    L += [f"| {c.compte} | {c.libelle} | {_m(c.solde)} | {c.attendu or 'À DOCUMENTER'} |" for c in etat.comptes]
    L.append("")
    L.append("**Verrous** : " + (", ".join(f"{k} au {v}" for k, v in etat.verrous.items()) or "aucun"))
    if etat.journal:
        nature = ("inaltérable : pas de remise en brouillon, seule l'extourne corrige"
                  if etat.journal.get("inalterable") else "remise en brouillon possible")
        L.append(f"\n**Journal** : {etat.journal.get('nom')} — {nature}.")
    return "\n".join(L)


_SYMBOLE = {"ok": "[x]", "fail": "[!] ÉCHEC —", "na": "n/a", "manuel": "[ ] MANUEL —"}


def _liste_controles(controles: list[ControleResultat]) -> str:
    L = [f"- {_SYMBOLE.get(c.statut, '[ ]')} **{c.nom}** — {c.detail}" for c in controles]
    echecs = [c for c in controles if c.statut == "fail"]
    if echecs:
        L += ["", f"**{len(echecs)} contrôle(s) bloquant(s) en échec : l'écriture NE DOIT PAS être proposée** "
                  "tant qu'ils ne sont pas levés. Pas « proposée avec réserve » : pas proposée."]
    return "\n".join(L)


def _table_lignes(spec: OperationSpec) -> str:
    if not spec.lignes:
        return "*(aucune ligne fournie — à compléter)*"
    L = ["| compte | libellé | débit | crédit |", "|---|---|---|---|"]
    L += [f"| {l.compte} | {l.libelle} | {_m(l.debit) if l.debit else ''} | {_m(l.credit) if l.credit else ''} |"
          for l in spec.lignes]
    return "\n".join(L)


def construire_rapport(spec: OperationSpec, precedents: list[Precedent], etat: EtatAvant,
                       controles: list[ControleResultat], genere_le: datetime | None = None) -> str:
    """Pré-rapport aux 9 sections. La ligne `Horodatage pré-vol : <ISO 8601>` est ce sur quoi
    le garde-fou (garde_fou_prevol.py) juge la fraîcheur : ne pas la retirer ni la reformater."""
    genere_le = (genere_le or datetime.now()).astimezone()
    jour = genere_le.strftime("%Y-%m-%d")
    return f"""# Pré-vol — {spec.type_geste} — {spec.societe} — {jour}

Protocole : instructions/protocole-prevol.md. Généré par `prevol.py` (lecture seule). **Les portes 1, 3, 5, 7, 8 et 9 restent à compléter par l'agent et l'utilisateur.**

Horodatage pré-vol : {genere_le.isoformat(timespec="seconds")}

## 1. Besoin métier

{spec.besoin_metier or "À COMPLÉTER — une phrase, en langage comptable."}

## 2. Précédent(s) — OBLIGATOIRE

{_table_precedents(precedents)}

## 3. Qualification du geste

À COMPLÉTER — process standard | contournement maison à reproduire | première occurrence.

## 4. État AVANT (lu le {etat.lu_le})

{_table_etat(etat)}

## 5. Écriture proposée

Société **{spec.societe}**, date **{spec.date}**{f", référence `{spec.ref}`" if spec.ref else ""}.

{_table_lignes(spec)}

**Effet comptable** : À COMPLÉTER — une phrase.

## 6. Contrôles bloquants

{_liste_controles(controles)}

## 7. Réversibilité

À COMPLÉTER — hiérarchie à préférer : brouillon + suppression > remise en brouillon + suppression > extourne (qui laisse deux écritures au grand livre).

## 8. Validation

À CONSIGNER PAR L'AGENT — le GO se donne en conversation, jamais dans ce fichier. Forme attendue :
GO donné en session le <AAAA-MM-JJTHH:MM+02:00> : « <citation exacte du message de l'utilisateur> »

## 9. Contrôle APRÈS (rempli après exécution)

À COMPLÉTER — relecture de la pièce dans l'ERP, comparée à l'attendu de la porte 5.
"""


def charger_spec(chemin: str | Path) -> OperationSpec:
    d = json.loads(Path(chemin).read_text(encoding="utf-8"))
    d.pop("_commentaire", None)
    d["lignes"] = [LigneEcriture(**l) for l in d.get("lignes", [])]
    return OperationSpec(**d)


def executer_prevol(spec: OperationSpec, adaptateur: AdaptateurPrevol,
                    genere_le: datetime | None = None) -> tuple[str, list[ControleResultat]]:
    precedents = adaptateur.chercher_precedents(spec)
    etat = adaptateur.lire_etat(spec)
    controles = adaptateur.controles_bloquants(spec)
    return construire_rapport(spec, precedents, etat, controles, genere_le), controles


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("demande", type=Path, help="demande JSON (cf. exemples/prevol/)")
    ap.add_argument("--grand-livre", type=Path, default=RACINE / "exemples" / "prevol" / "grand_livre.json")
    ap.add_argument("--out", type=Path, help="fichier du pré-rapport (défaut : sortie standard)")
    args = ap.parse_args(argv)
    rapport, controles = executer_prevol(charger_spec(args.demande), AdaptateurFichier.depuis_fichier(args.grand_livre))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rapport, encoding="utf-8")
        print(f"Pré-rapport : {args.out}", file=sys.stderr)
    else:
        print(rapport)
    return 1 if any(c.statut == "fail" for c in controles) else 0


if __name__ == "__main__":
    sys.exit(main())

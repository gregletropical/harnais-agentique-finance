"""
source_fichier.py — La source du classement, lue dans un fichier d'exemples.

En production, la routine lit l'ERP (Odoo, par son API) en LECTURE SEULE : lignes de
relevé non rapprochées, pièces ouvertes, lots de paiement, précédents bancaires, soldes.
Ce connecteur n'est pas publié : il porte des identifiants, une URL et des noms de
modèles propres à l'environnement du client.

`SourceFichier` implémente exactement le même contrat (`regles.classement.Source`) à
partir de deux fichiers JSON synthétiques :

  - `releve.json`      : les lignes bancaires non rapprochées du matin ;
  - `referentiel.json` : sociétés, journaux, tiers, pièces ouvertes, lots, paiements en
                         cours, précédents bancaires, factures soldées, soldes bancaires,
                         rapprochements automatiques de la nuit, compteurs de dérive.

Le classement ne voit pas la différence : c'est ce qui rend la routine testable et
rejouable sans accès au système du client.
"""

from __future__ import annotations

import json
from pathlib import Path

from regles.classement import Ligne, Piece, PointSolde, cents, compact, emetteur, id_emetteur


class SourceFichier:
    def __init__(self, referentiel: dict, releve: dict):
        self.ref = referentiel
        self.releve = releve
        self.societes = {s["id"]: s for s in referentiel["societes"]}
        self.journaux = {j["id"]: j for j in referentiel["journaux"]}
        self.tiers = {t["id"]: t for t in referentiel["tiers"]}
        self.pieces = [self._piece(p) for p in referentiel.get("pieces", [])]
        self._societe_piece = {p["id"]: p["societe_id"] for p in referentiel.get("pieces", [])}

    @classmethod
    def depuis_dossier(cls, dossier: str | Path) -> "SourceFichier":
        d = Path(dossier)
        return cls(json.loads((d / "referentiel.json").read_text(encoding="utf-8")),
                   json.loads((d / "releve.json").read_text(encoding="utf-8")))

    # -- conversions -----------------------------------------------------------
    def _piece(self, p: dict) -> Piece:
        return Piece(id=p["id"], nom=p["nom"], tiers_id=p["tiers_id"], tiers=self.tiers[p["tiers_id"]]["nom"],
                     residu=p["residu"], aml_ids=list(p["aml_ids"]), echeance=p.get("echeance"),
                     date=p.get("date"), echeances=list(p.get("echeances", [])), ref=p.get("ref", ""))

    def lignes(self) -> list[Ligne]:
        """Les lignes de relevé non rapprochées, enrichies de la société et du verrou."""
        res = []
        for x in self.releve["lignes"]:
            if x.get("rapprochee"):
                continue
            j = self.journaux[x["journal_id"]]
            s = self.societes[j["societe_id"]]
            pid = x.get("partenaire_id")
            res.append(Ligne(id=x["id"], date=x["date"], montant=x["montant"], libelle=x["libelle"],
                             journal_id=j["id"], journal=j["nom"], societe_id=s["id"], societe=s["nom"],
                             partenaire_id=pid, partenaire=self.tiers[pid]["nom"] if pid else None,
                             verrou=s.get("verrou"), contreparties_posees=list(x.get("contreparties_posees", []))))
        return res

    def _de_la_societe(self, p: Piece, societe_id: int) -> bool:
        return self._societe_piece.get(p.id) == societe_id

    # -- contrat Source --------------------------------------------------------
    def pieces_citees(self, numeros, jetons, societe_id):
        jetons_c = [compact(j) for j in jetons]
        return [p for p in self.pieces if self._de_la_societe(p, societe_id)
                and (any(p.nom.endswith("-" + n) for n in numeros)
                     or (p.ref and any(j == compact(p.ref) for j in jetons_c)))]

    def tiers_des_numeros(self, numeros, societe_id):
        res = {p.tiers_id: p.tiers for p in self.pieces
               if self._de_la_societe(p, societe_id) and any(p.nom.endswith("-" + n) for n in numeros)}
        for f in self.ref.get("factures_payees", []):
            if f["societe_id"] == societe_id and any(f["nom"].endswith("-" + n) for n in numeros):
                res[f["tiers_id"]] = self.tiers[f["tiers_id"]]["nom"]
        return list(res.items())

    def pieces_par_residu(self, montant, societe_id):
        return [p for p in self.pieces if self._de_la_societe(p, societe_id) and cents(p.residu) == cents(montant)]

    def pieces_du_tiers(self, tiers_id, societe_id, cote):
        return [p for p in self.pieces if p.tiers_id == tiers_id and self._de_la_societe(p, societe_id)
                and (p.residu > 0) == (cote == "client")]

    def tiers_par_nom(self, nom):
        # L'ERP fait un « ilike » ; le filtre fin est fait par `correspond` dans le classement.
        return [(t["id"], t["nom"]) for t in self.tiers.values()]

    def coquilles(self, tiers_ids):
        return {t for t in tiers_ids if self.tiers[t].get("archive_sans_piece")}

    def _precedents(self, filtre, journal_id, exclure_id):
        return [(p["tiers_id"], self.tiers[p["tiers_id"]]["nom"] if p["tiers_id"] else None)
                for p in self.ref.get("precedents_bancaires", [])
                if p["journal_id"] == journal_id and p.get("ligne_id") != exclure_id and filtre(p["libelle"])]

    def tiers_precedents(self, libelle, journal_id, exclure_id):
        return self._precedents(lambda lib: lib == libelle, journal_id, exclure_id)

    def tiers_precedents_emetteur(self, emetteur_, journal_id, exclure_id):
        return self._precedents(lambda lib: emetteur(lib) == emetteur_, journal_id, exclure_id)

    def tiers_precedents_id_emetteur(self, ics, journal_id, exclure_id):
        return self._precedents(lambda lib: id_emetteur(lib) == ics, journal_id, exclure_id)

    def factures_payees(self, tiers_id, societe_id, montant, date_min, date_max):
        return [f for f in self.ref.get("factures_payees", []) if f["tiers_id"] == tiers_id
                and f["societe_id"] == societe_id and cents(f["montant"]) == cents(montant)
                and date_min <= f["date"] <= date_max]

    def lots_envoyes(self, montant, journal_id):
        return [x for x in self.ref.get("lots", []) if x["etat"] == "envoye"
                and cents(x["montant"]) == cents(montant) and x["journal_id"] == journal_id]

    def lignes_ouvertes_tiers(self, tiers_id, societe_id, montant):
        return [x for x in self.ref.get("lignes_ouvertes_tiers", []) if x["tiers_id"] == tiers_id
                and x["societe_id"] == societe_id and cents(x["residu"]) == cents(montant)]

    def lignes_ouvertes_compte(self, compte, societe_id, montant):
        return [x for x in self.ref.get("lignes_ouvertes_compte", []) if x["compte"] == compte
                and x["societe_id"] == societe_id and cents(x["residu"]) == cents(montant)]

    def paiements_en_cours(self, journal_id, date_min, date_max):
        return [x for x in self.ref.get("paiements_en_cours", []) if x["journal_id"] == journal_id
                and date_min <= x["date"] <= date_max]

    # -- lectures du rapport et du plan d'écriture -----------------------------
    def points_solde(self, journal_id: int) -> list[PointSolde]:
        return [PointSolde(p["date"], p["soldes_banque"], p["solde_erp"])
                for p in self.ref.get("soldes", {}).get(str(journal_id), [])]

    def residus(self, aml_ids: list[int]) -> dict[int, dict]:
        """Lignes d'écriture ouvertes par identifiant : {id: {"residu", "societe_id", "lettree"}}.
        Sert au plan d'écriture, qui recalcule le garde-fou de somme juste avant le geste."""
        index: dict[int, dict] = {}
        for p in self.ref.get("pieces", []):
            if p.get("echeances"):
                for e in p["echeances"]:
                    index[e["id"]] = {"residu": e["residu"], "societe_id": p["societe_id"],
                                      "lettree": e.get("lettree", False)}
            else:
                for a in p["aml_ids"]:
                    index[a] = {"residu": p["residu"], "societe_id": p["societe_id"],
                                "lettree": p.get("lettree", False)}
        for x in self.ref.get("lignes_ouvertes_tiers", []) + self.ref.get("lignes_ouvertes_compte", []):
            index[x["id"]] = {"residu": x["residu"], "societe_id": x["societe_id"], "lettree": x.get("lettree", False)}
        for x in self.ref.get("paiements_en_cours", []):
            soc = self.journaux[x["journal_id"]]["societe_id"]
            index[x["id"]] = {"residu": x["residu"], "societe_id": soc, "lettree": x.get("lettree", False)}
        return {a: index[a] for a in aml_ids if a in index}

    def ligne_releve(self, ligne_id: int) -> dict | None:
        return next((x for x in self.releve["lignes"] if x["id"] == ligne_id), None)

    def lot(self, lot_id: int) -> dict | None:
        return next((x for x in self.ref.get("lots", []) if x["id"] == lot_id), None)

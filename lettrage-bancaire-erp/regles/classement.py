"""
classement.py — Classement des lignes bancaires non rapprochées : le « lint de
comptabilisation » de la routine de lettrage.

Module PUR : aucun appel réseau. Toute lecture du référentiel comptable passe par
un objet « source » qui respecte le protocole `Source` ci-dessous. En production,
cette source interroge l'ERP en lecture seule ; ici, `controles/source_fichier.py`
la remplace par la lecture d'un fichier d'exemples synthétiques, et les tests par
un bouchon en mémoire. Le classement est donc identique dans les trois cas.

Classes, regroupées en trois familles :

  Exécutables (après GO, sans autre décision humaine)
    A    référence de pièce citée au libellé, montant = reste dû
    A'1  tiers identifié, combinaison unique ET triviale (<= 3 pièces appariées,
         <= 8 pièces ouvertes chez le tiers) — exécuté, avec demande de validation
         a posteriori au comptable, car c'est un lettrage par déduction
    B    montant = un paiement par lot envoyé, unique
    N    virement groupé (/NBT n) = n paiements en cours, combinaison unique de taille n
    R    remboursement d'un trop-perçu client : une seule ligne client ouverte au montant
    I    imputation sans facture d'une catégorie ACTÉE (cf. categories.py)

  À arbitrer (une proposition existe, un humain tranche)
    A'2  combinaison unique, mais au-delà des seuils : coïncidence possible
    C    règlement partiel d'une pièce citée
    E    versement d'échéancier : lignes du périmètre dans l'ordre, dernière partielle

  Exceptions (rien à proposer en l'état : anomalie à instruire)
    P    ligne déjà partiellement traitée (contreparties posées)
    D    ambiguïté, rien trouvé, tiers inconnu ou incertain, montant hors tolérance,
         doublon probable, double paiement, exercice clos, catégorie hors périmètre
"""

from __future__ import annotations

import datetime as dt
import itertools
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Protocol

from regles.categories import (
    CATEGORIES_I, COMPTES_PAIRES_EXCLUES, FENETRE_DOUBLE_PAIEMENT_JOURS, FENETRE_NBT_JOURS,
    MAX_PIECES_ENUMEREES, MAX_PREFIXES_ECHEANCES, MIN_PRECEDENTS, MOTIF_ECHEANCIER, MOTIF_NBT,
    MOTIF_REMBOURSEMENT, PREFIXES_AUTO_NORMAUX, SEUIL_PIECES_APPARIEES, SEUIL_PIECES_OUVERTES, CategorieI,
)

EXECUTABLES = ("A", "A'1", "B", "N", "R", "I")   # ordre d'exécution du plan d'écriture
A_ARBITRER = ("A'2", "C", "E")
EXCEPTIONS = ("P", "D")
ORDRE_CLASSES = EXECUTABLES + A_ARBITRER + EXCEPTIONS


def famille(classe: str) -> str:
    if classe in EXECUTABLES:
        return "executable"
    if classe in A_ARBITRER:
        return "a_arbitrer"
    return "exception"


def cents(x: float) -> int:
    return int(round(x * 100))


def normaliser(texte: str) -> str:
    """Majuscules sans accents."""
    t = unicodedata.normalize("NFKD", texte or "")
    return "".join(ch for ch in t if not unicodedata.combining(ch)).upper()


def compact(texte: str) -> str:
    """Normalisé, réduit aux lettres et chiffres : « ALPHA L.B. » -> « ALPHALB »."""
    return re.sub(r"[^A-Z0-9]", "", normaliser(texte))


def categorie_i(libelle: str, montant: float, societe_id: int
                ) -> tuple[CategorieI | None, CategorieI | None]:
    """(catégorie applicable, catégorie reconnue mais actée pour une autre société)."""
    lib = normaliser(libelle)
    for cat in CATEGORIES_I:
        if (montant > 0) != (cat.sens > 0):
            continue
        if re.search(cat.motif, lib):
            if cat.societes is not None and societe_id not in cat.societes:
                return None, cat
            return cat, None
    return None, None


# --------------------------------------------------------------------------- #
# Extraction depuis le libellé bancaire
# --------------------------------------------------------------------------- #

def factures_citees(libelle: str) -> list[str]:
    """Numéros de facture fournisseur cités explicitement : « REF/FACTURE 90000123 »,
    « LIB/FACTURE … », « FACTURE 90000123 » (8 chiffres). Sert au garde-fou de A'."""
    lib = normaliser(libelle)
    nums = re.findall(r"\b(?:REF|LIB)/FACTURE[ :]*([A-Z0-9][A-Z0-9\-]*)", lib)
    nums += re.findall(r"(?<![A-Z0-9])FACTURE (\d{8})(?!\d)", lib)
    return sorted({compact(n) for n in nums if compact(n)})


def ref_concorde(cites: list[str], pieces: list["Piece"]) -> bool:
    """Un numéro cité au moins figure dans la référence fournisseur d'une des pièces."""
    refs = [compact(p.ref) for p in pieces if p.ref]
    return any(n in r for n in cites for r in refs)


def numeros_cites(libelle: str) -> list[str]:
    """Numéros de facture client à 5 chiffres isolés (« FV 00129 », « FV00129 »).
    Les dates (6 chiffres) et identifiants longs sont exclus par construction."""
    return sorted(set(re.findall(r"(?<!\d)(\d{5})(?!\d)", libelle or "")))


def jetons_cites(libelle: str) -> list[str]:
    """Jetons alphanumériques d'au moins 6 caractères avec un chiffre : candidats
    à la référence d'une facture fournisseur."""
    jetons = re.findall(r"[A-Z0-9][A-Z0-9\-]{5,}", normaliser(libelle))
    return sorted({j for j in jetons if re.search(r"\d", j)})


_MOTIFS_NOM = (
    r"/FRM (.+?)(?: /|$)",
    r"/PID (.+?)(?: /|$)",
    r"^PRLV SEPA (?:B2B )?(.+?)(?: ECH/| ID EMETTEUR|$)",
    r"^PRLV (.+)$",
    r"^VIR SEPA (?:INSTANT )?(?:RECU |EMIS )?(.+)$",
    r"^VIR INST(?:ANTANE)? (.+?)(?: -| /|$)",
    r"^VIR (?!SEPA\b|ETRANGER\b)(.+?)(?: -| /|$)",
    r"^EVI REMISE (.+)$",
)


def nom_contrepartie(libelle: str) -> str | None:
    lib = normaliser(libelle).strip()
    for motif in _MOTIFS_NOM:
        m = re.search(motif, lib)
        if m:
            nom = m.group(1).split(" - ")[0].strip()
            return nom or None
    return None


# Formes juridiques : ignorées dans l'appariement de nom, en tête comme en fin.
FORMES_JURIDIQUES = frozenset({"SA", "SAS", "SASU", "SARL", "EURL", "SCI", "SNC", "SCP", "SCM", "SELARL",
                               "SELAS", "SELAFA", "SCOP", "SCA", "GIE"})


def nom_sans_forme(nom: str) -> str:
    """Nom compacté, formes juridiques retirées : « SAS ALPHA LOGICIELS » -> « ALPHALOGICIELS »."""
    return "".join(m for m in re.split(r"[^A-Z0-9]+", normaliser(nom)) if m not in FORMES_JURIDIQUES)


def mots_significatifs(nom: str) -> list[str]:
    vides = FORMES_JURIDIQUES | {"STE", "SOCIETE", "LA", "LE", "LES", "DE", "DU", "DES", "ET", "M", "MME"}
    mots = [m for m in re.split(r"[^A-Z0-9]+", normaliser(nom)) if len(m) >= 2 and m not in vides]
    if not mots and re.fullmatch(r"(?:[A-Z]\.)+[A-Z]?\.?", normaliser(nom).replace(" ", "")):
        return [compact(nom)]   # sigle à points : « S.T.X. » -> « STX »
    return mots


def correspond(nom: str | None, nom_tiers: str) -> bool:
    """Les deux premiers mots significatifs du libellé figurent dans le nom compacté du
    tiers (un mot seul suffit s'il est le nom exact, ou s'il fait au moins 4 caractères).
    Empêche qu'un particulier « M JEAN DUPONT » se rattache à une adresse « rue Jean Jaurès »."""
    mots = mots_significatifs(nom or "")
    if not mots:
        return False
    cible = compact(nom_tiers)
    if len(mots) == 1:
        return cible == mots[0] or (len(mots[0]) >= 4 and mots[0] in cible)
    return all(m in cible for m in mots[:2])


def choisir_tiers(nom: str, candidats: list[tuple[int, str]],
                  coquilles: frozenset | set = frozenset()) -> tuple[int, str] | None:
    """Tiers identifié à coup sûr, ou None — jamais de devinette. `coquilles` : fiches
    archivées SANS aucune pièce comptable (doublons d'import), écartées quand plusieurs
    tiers sont plausibles ; une fiche archivée qui porte des pièces reste candidate."""
    retenus = [(tid, n) for tid, n in {tid: n for tid, n in candidats}.items() if correspond(nom, n)]
    if len(retenus) > 1:
        retenus = [t for t in retenus if t[0] not in coquilles]
    if len(retenus) > 1:
        # Plusieurs tiers plausibles : seul celui dont le nom EST le libellé départage,
        # formes juridiques ignorées. Sinon, pas de devinette.
        retenus = [t for t in retenus if nom_sans_forme(t[1]) == nom_sans_forme(nom)]
    return retenus[0] if len(retenus) == 1 else None


def emetteur(libelle: str) -> str | None:
    """Émetteur d'un virement reçu : le texte après « /FRM » jusqu'au « / » suivant."""
    m = re.search(r"/FRM ([^/]+)", normaliser(libelle))
    if not m:
        return None
    return " ".join(m.group(1).split()) or None


def id_emetteur(libelle: str) -> str | None:
    """Identifiant créancier SEPA d'un prélèvement (« ID EMETTEUR/… »)."""
    m = re.search(r"\bID EMETTEUR/([A-Z0-9]+)", normaliser(libelle))
    return m.group(1) if m else None


def tiers_par_precedent(precedents: list[tuple]) -> tuple[int, str] | None:
    """Tiers des lignes déjà rapprochées du même émetteur (ou même créancier SEPA, ou même
    libellé). Retenu seulement s'il y en a au moins MIN_PRECEDENTS et qu'elles sont
    UNANIMES : un seul discordant, ou une ligne sans tiers, et la règle ne joue pas."""
    if len(precedents) < MIN_PRECEDENTS:
        return None
    ids = {t[0] for t in precedents}
    if len(ids) != 1 or None in ids:
        return None
    return precedents[0][0], precedents[0][1]


# --------------------------------------------------------------------------- #
# Échéances et échéanciers
# --------------------------------------------------------------------------- #

def echeancier(libelle: str) -> tuple[int, int] | None:
    """(n, m) d'un versement d'échéancier annoncé au libellé, sinon None."""
    m = re.search(MOTIF_ECHEANCIER, normaliser(libelle))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def dates_factures_citees(libelle: str, date_ligne: str) -> list[str]:
    """Dates de factures citées : « FACTURES 15/06+07 » -> 15/06 et 15/07, « FACTURES 15/06
    ET 15/07 ». Année de la ligne, ou la précédente si le mois cité est postérieur."""
    lib, d = normaliser(libelle), dt.date.fromisoformat(date_ligne)
    dates = set()
    for bloc in re.finditer(r"FACTURES?\s*((?:(?:\s*(?:ET|,)\s*)?\d{2}/\d{2}(?:\+\d{2})*)+)", lib):
        for t in re.finditer(r"(\d{2})/(\d{2})((?:\+\d{2})*)", bloc.group(1)):
            jour = int(t.group(1))
            for mois in [int(t.group(2))] + [int(x) for x in re.findall(r"\d{2}", t.group(3))]:
                annee = d.year - 1 if mois > d.month else d.year
                try:
                    dates.add(dt.date(annee, mois, jour).isoformat())
                except ValueError:
                    pass
    return sorted(dates)


def dates_completes_citees(libelle: str) -> list[str]:
    """Dates complètes citées au libellé (« 15-09-2026 », « 15/09/2026 »), en ISO."""
    dates = set()
    for j, m, a in re.findall(r"(?<!\d)(\d{2})[-/](\d{2})[-/](\d{4})(?!\d)", libelle or ""):
        try:
            dates.add(dt.date(int(a), int(m), int(j)).isoformat())
        except ValueError:
            pass
    return sorted(dates)


def _echeances(p: "Piece") -> list[dict]:
    """Lignes de tiers ouvertes d'une pièce dans l'ordre d'échéance ; à défaut de détail,
    la pièce entière en une seule ligne."""
    if p.echeances:
        return sorted(({"aml_ids": [e["id"]], "residu": e["residu"], "echeance": e.get("echeance")}
                       for e in p.echeances), key=lambda e: (e["echeance"] or "9999", e["aml_ids"][0]))
    return [{"aml_ids": list(p.aml_ids), "residu": p.residu, "echeance": p.echeance}]


def echeances_anciennes(pieces: list["Piece"], montant: float) -> list[list[tuple]] | None:
    """Solutions « échéances les plus anciennes, sans saut » : pour chaque pièce, un préfixe
    (éventuellement vide) de ses lignes ouvertes dans l'ordre d'échéance, dont la somme vaut
    le montant. None si l'énumération est trop large."""
    listes = [_echeances(p) for p in pieces]
    taille = 1
    for x in listes:
        taille *= len(x) + 1
    if taille > MAX_PREFIXES_ECHEANCES:
        return None
    cible, solutions = cents(montant), []
    for ks in itertools.product(*[range(len(x) + 1) for x in listes]):
        if not any(ks):
            continue
        choix = [(p, e) for p, x, k in zip(pieces, listes, ks) for e in x[:k]]
        if sum(cents(e["residu"]) for _, e in choix) == cible:
            solutions.append(choix)
    return solutions


def proposition_echeancier(lignes: list[tuple], montant: float) -> dict | None:
    """Lignes (pièce, échéance) ordonnées : les premières soldées, la dernière éventuellement
    partielle. Garde-fou : somme des pleines < montant <= somme avec la dernière."""
    cible, cumul = cents(montant), 0
    for i, (_, e) in enumerate(lignes):
        avant, cumul = cumul, cumul + cents(e["residu"])
        if cumul >= cible:
            if not (avant < cible <= cumul):
                return None
            return {"lignes": lignes[:i + 1], "reste_partielle": (cumul - cible) / 100}
    return None


# --------------------------------------------------------------------------- #
# Combinaisons exactes (meet-in-the-middle, en centimes)
# --------------------------------------------------------------------------- #

def _sous_sommes(valeurs: list[int]) -> tuple[list[int], list[int]]:
    sommes, masques = [0], [0]
    for i, v in enumerate(valeurs):
        bit = 1 << i
        sommes += [s + v for s in sommes]
        masques += [m | bit for m in masques]
    return sommes, masques


def combinaisons_exactes(valeurs: list[int], cible: int, taille: int | None = None,
                         max_exemples: int = 2) -> tuple[int | None, list[list[int]]]:
    """Nombre de sous-ensembles NON VIDES de `valeurs` (centimes) dont la somme vaut `cible`,
    éventuellement de taille imposée, et au plus `max_exemples` d'entre eux (indices).
    None si trop de valeurs pour énumérer."""
    n = len(valeurs)
    if n == 0:
        return 0, []
    if n > MAX_PIECES_ENUMEREES:
        return None, []
    h = n // 2
    gs, gm = _sous_sommes(valeurs[:h])
    ds, dm = _sous_sommes(valeurs[h:])
    index: dict = {}
    for s, m in zip(gs, gm):
        cle = (s, bin(m).count("1")) if taille is not None else s
        index.setdefault(cle, []).append(m)
    total, exemples = 0, []
    for s, m in zip(ds, dm):
        k = bin(m).count("1")
        if taille is not None:
            if k > taille:
                continue
            gauche = index.get((cible - s, taille - k), [])
        else:
            gauche = index.get(cible - s, [])
        for g in gauche:
            if g == 0 and m == 0:
                continue  # sous-ensemble vide
            total += 1
            if len(exemples) < max_exemples:
                masque = g | (m << h)
                exemples.append([i for i in range(n) if masque >> i & 1])
    return total, exemples


# --------------------------------------------------------------------------- #
# Objets échangés avec la source
# --------------------------------------------------------------------------- #

@dataclass
class Ligne:
    id: int
    date: str
    montant: float
    libelle: str
    journal_id: int
    journal: str
    societe_id: int
    societe: str
    partenaire_id: int | None = None
    partenaire: str | None = None
    verrou: str | None = None                                  # date de verrouillage de l'exercice
    contreparties_posees: list = field(default_factory=list)   # comptes hors banque et hors attente


@dataclass
class Piece:
    id: int
    nom: str
    tiers_id: int
    tiers: str
    residu: float            # somme SIGNÉE des lignes de tiers ouvertes (client + / fournisseur -)
    aml_ids: list
    echeance: str | None = None
    date: str | None = None                                    # date de facture
    echeances: list = field(default_factory=list)              # [{"id","residu","echeance"}]
    ref: str = ""                                              # référence fournisseur


@dataclass
class Classement:
    classe: str
    motif: str
    geste: dict | None = None
    candidats: list = field(default_factory=list)
    tiers: str | None = None
    pieces_ouvertes: int | None = None
    combinaisons: int | None = None
    validation_comptable: bool = False   # A'1 : demander au comptable de valider après coup

    @property
    def executable(self) -> bool:
        return self.classe in EXECUTABLES

    def en_dict(self) -> dict:
        d = asdict(self)
        d["executable"] = self.executable
        d["famille"] = famille(self.classe)
        return d


class Source(Protocol):
    """Lectures dont le classement a besoin. En production : requêtes ERP en lecture
    seule. Ici : `controles/source_fichier.SourceFichier`."""

    def pieces_citees(self, numeros: list[str], jetons: list[str], societe_id: int) -> list[Piece]: ...
    def tiers_des_numeros(self, numeros: list[str], societe_id: int) -> list[tuple[int, str]]: ...
    def pieces_par_residu(self, montant: float, societe_id: int) -> list[Piece]: ...
    def pieces_du_tiers(self, tiers_id: int, societe_id: int, cote: str) -> list[Piece]: ...
    def tiers_par_nom(self, nom: str) -> list[tuple[int, str]]: ...
    def coquilles(self, tiers_ids: list[int]) -> set[int]: ...
    def tiers_precedents(self, libelle: str, journal_id: int, exclure_id: int) -> list[tuple]: ...
    def tiers_precedents_emetteur(self, emetteur: str, journal_id: int, exclure_id: int) -> list[tuple]: ...
    def tiers_precedents_id_emetteur(self, ics: str, journal_id: int, exclure_id: int) -> list[tuple]: ...
    def factures_payees(self, tiers_id: int, societe_id: int, montant: float,
                        date_min: str, date_max: str) -> list[dict]: ...
    def lots_envoyes(self, montant: float, journal_id: int) -> list[dict]: ...
    def lignes_ouvertes_tiers(self, tiers_id: int, societe_id: int, montant: float) -> list[dict]: ...
    def lignes_ouvertes_compte(self, compte: str, societe_id: int, montant: float) -> list[dict]: ...
    def paiements_en_cours(self, journal_id: int, date_min: str, date_max: str) -> list[dict]: ...


def _egal(a: float, b: float) -> bool:
    return cents(a) == cents(b)


def _geste_lettrer(pieces: list[Piece], montant: float) -> dict:
    return {"type": "lettrer", "aml_ids": [a for p in pieces for a in p.aml_ids],
            "pieces": [p.nom for p in pieces], "somme": round(sum(p.residu for p in pieces), 2),
            "montant": montant}


def _geste_imputer(cat: CategorieI, montant: float, lettrer_avec: list | None = None,
                   societe_id: int | None = None) -> dict:
    return {"type": "imputer", "categorie": cat.code, "compte": cat.compte_de(societe_id),
            "partenaire_id": cat.partenaire_id, "lettrer_avec": lettrer_avec or [],
            "montant": montant}


# --------------------------------------------------------------------------- #
# Classement d'une ligne — l'ordre des étapes EST la règle
# --------------------------------------------------------------------------- #

def classer(l: Ligne, src: Source) -> Classement:
    # 1. Exercice clos : on ne touche que l'exercice ouvert.
    if l.verrou and l.date <= l.verrou:
        return Classement("D", f"exercice clos (verrou au {l.verrou}) — signalé, jamais exécuté")

    # 2. Ligne partiellement traitée (robot ou humain) : jamais complétée automatiquement.
    if l.contreparties_posees:
        return Classement("P", "contreparties déjà posées sur " + ", ".join(l.contreparties_posees)
                          + " — le solde en attente ne correspond pas forcément au reste dû")

    cat, cat_hors = categorie_i(l.libelle, l.montant, l.societe_id)

    # 3. Imputations actées (sauf celles qui ne valent qu'à défaut de facture).
    if cat and not cat.apres_factures:
        return _classer_i(l, cat, src)

    # 4. Paiement par lot.
    if l.montant < 0:
        lots = src.lots_envoyes(l.montant, l.journal_id)
        if len(lots) == 1:
            lot = lots[0]
            return Classement("B", f"lot {lot['nom']} au montant exact",
                              geste={"type": "lot", "lot_id": lot["id"], "lot": lot["nom"], "montant": l.montant},
                              candidats=[lot["nom"]])
        if len(lots) > 1:
            return Classement("D", f"{len(lots)} lots au même montant", candidats=[x["nom"] for x in lots])

    # 5. Virement groupé de paiements en cours (notes de frais…).
    m = re.search(MOTIF_NBT, normaliser(l.libelle))
    if m and l.montant < 0:
        return _classer_n(l, int(m.group(1)), src)

    # 6. Pièces citées au libellé. Une référence citée au montant exact l'emporte sur
    #    l'annonce d'échéancier.
    numeros, jetons = numeros_cites(l.libelle), jetons_cites(l.libelle)
    citees = src.pieces_citees(numeros, jetons, l.societe_id) if (numeros or jetons) else []
    citees = [p for p in citees if (p.residu > 0) == (l.montant > 0)]
    k_cite = _classer_citees(l, citees, src) if citees else None
    if k_cite and k_cite.classe == "A":
        return k_cite

    # 6bis. Versement d'échéancier : pas d'énumération de combinaisons.
    ech = echeancier(l.libelle)
    if ech and (dates_factures_citees(l.libelle, l.date) or not k_cite):
        return _classer_e(l, ech, src)
    if k_cite:
        return k_cite

    # 7. Remboursement d'un trop-perçu client.
    if l.montant < 0 and (re.search(MOTIF_REMBOURSEMENT, normaliser(l.libelle)) or numeros):
        r = _classer_r(l, numeros, src)
        if r:
            return r

    # 8. Tiers identifié et combinaison de pièces ouvertes.
    res = _classer_par_tiers(l, src)
    if res and res.classe != "D":
        return res

    # 9. Imputations actées valant à défaut de facture.
    if cat and cat.apres_factures:
        return _classer_i(l, cat, src)

    if cat_hors:
        return Classement("D", f"catégorie {cat_hors.code} ({cat_hors.compte}) reconnue, mais actée "
                               f"seulement pour d'autres sociétés — extension à arbitrer")
    return res or Classement("D", "aucune correspondance : tiers inconnu, aucune pièce au montant")


def _classer_citees(l: Ligne, citees: list[Piece], src: Source) -> Classement:
    if _egal(sum(p.residu for p in citees), l.montant):
        return Classement("A", "référence citée, montant = reste dû",
                          geste=_geste_lettrer(citees, l.montant),
                          candidats=[p.nom for p in citees], tiers=citees[0].tiers)
    nb, ex = combinaisons_exactes([cents(p.residu) for p in citees], cents(l.montant))
    if nb == 1:
        retenues = [citees[i] for i in ex[0]]
        return Classement("A", "références citées, sous-ensemble unique au montant exact",
                          geste=_geste_lettrer(retenues, l.montant),
                          candidats=[p.nom for p in retenues], tiers=retenues[0].tiers)
    # Raisonnement par échéance : le montant est-il celui des échéances ouvertes les plus
    # anciennes, dans l'ordre, sans saut ?
    sol = echeances_anciennes(citees, l.montant)
    if sol and len(sol) == 1:
        choix = sol[0]
        detail = [f"{p.nom} échéance {e['echeance'] or '—'} ({e['residu']:.2f})" for p, e in choix]
        return Classement("A", "référence citée, montant = échéance(s) ouverte(s) la(les) plus ancienne(s)",
                          geste={"type": "lettrer", "aml_ids": [a for _, e in choix for a in e["aml_ids"]],
                                 "pieces": detail, "somme": round(sum(e["residu"] for _, e in choix), 2),
                                 "montant": l.montant},
                          candidats=detail, tiers=choix[0][0].tiers)
    lot = _classer_lot_du_jour(l, citees, src)
    if lot:
        return lot
    if len(citees) == 1 and abs(l.montant) < abs(citees[0].residu):
        p = citees[0]
        return Classement("C", f"règlement partiel de {p.nom} (reste dû {p.residu:.2f}, "
                               f"aucune échéance ne correspond)", candidats=[p.nom], tiers=p.tiers)
    ecart = l.montant - sum(p.residu for p in citees)
    return Classement("D", f"référence citée mais montant ≠ reste dû (écart {ecart:+.2f}, tolérance nulle)",
                      candidats=[f"{p.nom} ({p.residu:.2f})" for p in citees], tiers=citees[0].tiers)


def _classer_lot_du_jour(l: Ligne, citees: list[Piece], src: Source) -> Classement | None:
    """Lot de factures du même jour payé en un virement qui n'en cite que la première.
    Conditions binaires : une seule pièce citée, sa date de facture citée en toutes lettres,
    et le montant égal au reste dû de TOUTES les pièces ouvertes du tiers à cette date."""
    if len(citees) != 1 or not citees[0].date:
        return None
    p = citees[0]
    if p.date not in dates_completes_citees(l.libelle):
        return None
    cote = "client" if l.montant > 0 else "fournisseur"
    lot = sorted((q for q in src.pieces_du_tiers(p.tiers_id, l.societe_id, cote) if q.date == p.date),
                 key=lambda q: q.nom)
    if len(lot) < 2 or not _egal(sum(q.residu for q in lot), l.montant):
        return None
    return Classement("A", f"référence citée = facture d'un lot du {p.date} (date citée) : lot complet de "
                           f"{len(lot)} pièces de {p.tiers} au montant exact",
                      geste=_geste_lettrer(lot, l.montant), candidats=[q.nom for q in lot],
                      tiers=p.tiers, pieces_ouvertes=len(lot))


def _classer_e(l: Ligne, ech: tuple[int, int], src: Source) -> Classement:
    """Classe E (non exécutable) : périmètre = pièces ouvertes du tiers aux dates de factures
    citées, lignes par pièce puis échéance, la dernière partielle. Sans date citée, le
    périmètre est indéterminé -> D."""
    n, m = ech
    solde = n == m or bool(re.search(r"\bSOLDE\b", normaliser(l.libelle)))
    dates = dates_factures_citees(l.libelle, l.date)
    if not dates:
        return Classement("D", f"échéancier {n}/{m} sans date de facture citée : périmètre indéterminé")
    tiers, _, origine = _identifier_tiers(l, src)
    if tiers is None:
        return Classement("D", f"échéancier {n}/{m} : tiers non identifié")
    tid, tnom = tiers
    cote = "client" if l.montant > 0 else "fournisseur"
    pieces = src.pieces_du_tiers(tid, l.societe_id, cote)
    perimetre = sorted((p for p in pieces if p.date in dates), key=lambda p: p.id)
    portee = "factures du " + ", ".join(f"{d[8:10]}/{d[5:7]}" for d in dates)
    if not perimetre:
        return Classement("D", f"échéancier {n}/{m} : aucune pièce ouverte de {tnom} ({portee})",
                          tiers=tnom, pieces_ouvertes=len(pieces))
    lignes = [(p, e) for p in perimetre for e in _echeances(p)]
    total = round(sum(e["residu"] for _, e in lignes), 2)
    prop = proposition_echeancier(lignes, l.montant)
    ecart = (f" ; écart de solde d'échéancier : {total - l.montant:.2f} €"
             if solde and not _egal(total, l.montant) else "")
    if prop is None:
        return Classement("D", f"échéancier {n}/{m} : le périmètre ({portee}, {total:.2f}) ne couvre pas "
                               f"le montant{ecart}", tiers=tnom, pieces_ouvertes=len(perimetre))
    retenues = prop["lignes"]
    detail = [p.nom for p, _ in retenues[:-1]]
    p_der, _ = retenues[-1]
    detail.append(f"{p_der.nom} (partielle, reste {prop['reste_partielle']:.2f})"
                  if prop["reste_partielle"] else p_der.nom)
    restent = [p.nom for p in perimetre if p.nom not in {q.nom for q, _ in retenues}]
    motif = (f"échéancier {n}/{m}{' SOLDE' if solde else ''} de {tnom}{origine} : {len(retenues)} ligne(s) "
             f"du périmètre ({portee}, {len(perimetre)} pièce(s), {total:.2f}) dans l'ordre, dernière "
             f"partielle — proposition à valider{ecart}"
             + (f" ; restent ouvertes : {', '.join(restent)}" if restent else ""))
    return Classement("E", motif, geste={"type": "lettrer_partiel",
                                         "aml_ids": [a for _, e in retenues for a in e["aml_ids"]],
                                         "pieces": detail, "somme": round(sum(e["residu"] for _, e in retenues), 2),
                                         "reste_partielle": prop["reste_partielle"], "montant": l.montant},
                      candidats=detail, tiers=tnom, pieces_ouvertes=len(pieces))


def _classer_i(l: Ligne, cat: CategorieI, src: Source) -> Classement:
    if cat.a_arbitrer:
        return Classement("D", f"{cat.code} : {cat.a_arbitrer} — signalé, jamais exécuté")
    if cat.montant_max is not None and abs(l.montant) > cat.montant_max:
        return Classement("D", f"{cat.code} : {cat.hors_plafond or 'montant au-delà du plafond de la catégorie'}")
    if cat.sans_tiers and l.partenaire_id:
        return Classement("D", f"{cat.code} : tiers posé sur la ligne ({l.partenaire}) — "
                               "imputation automatique écartée")
    compte = cat.compte_de(l.societe_id)
    if cat.lettrage == "od_ca3":
        ods = src.lignes_ouvertes_compte(compte, l.societe_id, l.montant)
        if len(ods) != 1:
            return Classement("D", f"CA3 : {len(ods)} OD ouverte(s) du même montant sur {compte} "
                                   "— contrôle d'unicité bloquant", candidats=[o["piece"] for o in ods])
        return Classement("I", f"{cat.code} → {compte}, lettrage avec {ods[0]['piece']} ({cat.decision})",
                          geste=_geste_imputer(cat, l.montant, [ods[0]["id"]], l.societe_id),
                          candidats=[ods[0]["piece"]])
    motif = f"{cat.code} → {compte} ({cat.decision})"
    if cat.lettrage == "paie":
        motif += " — lettrage avec la paie du mois à faire ensuite"
    return Classement("I", motif, geste=_geste_imputer(cat, l.montant, societe_id=l.societe_id))


def _classer_n(l: Ligne, nbt: int, src: Source) -> Classement:
    date_min = (dt.date.fromisoformat(l.date) - dt.timedelta(days=FENETRE_NBT_JOURS)).isoformat()
    lignes = src.paiements_en_cours(l.journal_id, date_min, l.date)
    if not lignes:
        return Classement("D", f"virement groupé ({nbt} annoncés), aucun paiement en cours")
    nb, ex = combinaisons_exactes([cents(x["residu"]) for x in lignes], cents(l.montant), taille=nbt)
    if nb == 1:
        retenus = [lignes[i] for i in ex[0]]
        return Classement("N", f"virement groupé : seule combinaison de {nbt} paiements en cours",
                          geste={"type": "lettrer", "aml_ids": [x["id"] for x in retenus],
                                 "pieces": [x["libelle"] for x in retenus],
                                 "somme": round(sum(x["residu"] for x in retenus), 2), "montant": l.montant},
                          candidats=[x["libelle"] for x in retenus],
                          pieces_ouvertes=len(lignes), combinaisons=1)
    total = round(sum(x["residu"] for x in lignes), 2)
    return Classement("D", f"virement groupé ({nbt} annoncés) : {nb if nb is not None else 'trop de'} "
                           f"combinaison(s) parmi {len(lignes)} paiements en cours ({total:.2f})",
                      pieces_ouvertes=len(lignes), combinaisons=nb)


def _classer_r(l: Ligne, numeros: list[str], src: Source) -> Classement | None:
    tiers = src.tiers_des_numeros(numeros, l.societe_id) if numeros else []
    if not tiers and l.partenaire_id:
        tiers = [(l.partenaire_id, l.partenaire or "")]
    if not tiers:
        t, _ = _tiers_par_nom(nom_contrepartie(l.libelle), src)
        tiers = [t] if t else []
    tiers = list(dict(tiers).items())
    if len(tiers) != 1:
        return None
    tid, tnom = tiers[0]
    lignes = src.lignes_ouvertes_tiers(tid, l.societe_id, l.montant)
    if len(lignes) == 1:
        x = lignes[0]
        return Classement("R", f"remboursement : seule ligne client ouverte de {tnom} au montant exact",
                          geste={"type": "lettrer", "aml_ids": [x["id"]], "pieces": [x["piece"]],
                                 "somme": x["residu"], "montant": l.montant},
                          candidats=[x["piece"]], tiers=tnom)
    if len(lignes) > 1:
        return Classement("D", f"remboursement : {len(lignes)} lignes ouvertes de {tnom} au même montant",
                          candidats=[x["piece"] for x in lignes], tiers=tnom)
    return None


def _tiers_par_nom(nom: str | None, src: Source) -> tuple[tuple[int, str] | None, dict]:
    """(tiers retenu par le nom, tiers plausibles hors coquilles archivées)."""
    if not nom:
        return None, {}
    candidats = src.tiers_par_nom(nom)
    plausibles = {tid: n for tid, n in candidats if correspond(nom, n)}
    coq = src.coquilles(list(plausibles)) if len(plausibles) > 1 else set()
    plausibles = {tid: n for tid, n in plausibles.items() if tid not in coq}
    return choisir_tiers(nom, candidats, coq), plausibles


def _identifier_tiers(l: Ligne, src: Source) -> tuple[tuple[int, str] | None, dict, str]:
    """Tiers de la ligne : posé sur la ligne, sinon par le nom, sinon par précédent bancaire
    unanime (émetteur /FRM, à défaut créancier SEPA, à défaut libellé identique). Retourne
    aussi les plausibles par le nom (pour motiver l'ambiguïté) et l'origine à citer."""
    if l.partenaire_id:
        return (l.partenaire_id, l.partenaire or ""), {}, ""
    tiers, plausibles = _tiers_par_nom(nom_contrepartie(l.libelle), src)
    if tiers:
        # Homonyme sans pièce : la fiche au nom exact n'a aucune pièce ouverte, mais les
        # précédents bancaires désignent unanimement une autre fiche qui en a.
        cote = "client" if l.montant > 0 else "fournisseur"
        if not src.pieces_du_tiers(tiers[0], l.societe_id, cote):
            t, origine = _tiers_par_precedent_bancaire(l, src)
            if t and t[0] != tiers[0] and src.pieces_du_tiers(t[0], l.societe_id, cote):
                return t, plausibles, (f" (tiers par précédent bancaire : {origine} ; la fiche « {tiers[1]} » "
                                       f"trouvée par le nom n'a aucune pièce ouverte)")
        return tiers, plausibles, ""
    t, origine = _tiers_par_precedent_bancaire(l, src)
    if t:
        return t, plausibles, f" (tiers par précédent bancaire : {origine})"
    return None, plausibles, ""


def _tiers_par_precedent_bancaire(l: Ligne, src: Source) -> tuple[tuple[int, str] | None, str]:
    if not (l.libelle or "").strip():
        return None, ""
    em, ics = emetteur(l.libelle), id_emetteur(l.libelle)
    if em:
        precedents = src.tiers_precedents_emetteur(em, l.journal_id, l.id)
        origine = f"{len(precedents)} lignes du même émetteur « {em} »"
    elif ics:
        precedents = src.tiers_precedents_id_emetteur(ics, l.journal_id, l.id)
        origine = f"{len(precedents)} lignes du même ID émetteur SEPA {ics}"
    else:
        precedents = src.tiers_precedents(l.libelle, l.journal_id, l.id)
        origine = f"{len(precedents)} lignes au même libellé"
    return tiers_par_precedent(precedents), origine


def _double_paiement(l: Ligne, tid: int, src: Source) -> str | None:
    date_min = (dt.date.fromisoformat(l.date) - dt.timedelta(days=FENETRE_DOUBLE_PAIEMENT_JOURS)).isoformat()
    payees = src.factures_payees(tid, l.societe_id, l.montant, date_min, l.date)
    if not payees:
        return None
    f = payees[0]
    return f"facture {f['nom']} au montant exact déjà payée le {f['date']} : double paiement probable"


def _classer_par_tiers(l: Ligne, src: Source) -> Classement | None:
    nom = nom_contrepartie(l.libelle)
    tiers, plausibles, origine = _identifier_tiers(l, src)
    if tiers is None:
        # Recherche par montant : le nom dans l'ERP diffère souvent du libellé bancaire.
        par_montant = list(src.pieces_par_residu(l.montant, l.societe_id))
        if len(par_montant) == 1 and correspond(nom, par_montant[0].tiers):
            tiers = (par_montant[0].tiers_id, par_montant[0].tiers)
        elif par_montant:
            return Classement("D", "tiers incertain : pièce(s) au montant exact chez un tiers "
                                   "dont le nom ne correspond pas au libellé",
                              candidats=[f"{p.nom} — {p.tiers}" for p in par_montant[:5]])
        elif len(plausibles) > 1:
            return Classement("D", f"tiers ambigu : {len(plausibles)} tiers correspondent à « {nom} »",
                              candidats=list(plausibles.values())[:5])
        else:
            return None
    tid, tnom = tiers
    cote = "client" if l.montant > 0 else "fournisseur"
    pieces = src.pieces_du_tiers(tid, l.societe_id, cote)
    if not pieces:
        double = _double_paiement(l, tid, src)
        return Classement("D", f"{tnom}{origine} : aucune pièce ouverte" + (f" — {double}" if double else ""),
                          tiers=tnom, pieces_ouvertes=0)
    nb, ex = combinaisons_exactes([cents(p.residu) for p in pieces], cents(l.montant))
    if nb is None:
        return Classement("D", f"{tnom} : {len(pieces)} pièces ouvertes, énumération non tentée",
                          tiers=tnom, pieces_ouvertes=len(pieces))
    if nb == 0:
        double = _double_paiement(l, tid, src)
        return Classement("D", f"{tnom}{origine} : aucune combinaison exacte parmi {len(pieces)} pièces ouvertes"
                          + (f" — {double}" if double else ""),
                          tiers=tnom, pieces_ouvertes=len(pieces), combinaisons=0)
    if nb > 1:
        return Classement("D", f"{tnom} : {nb} combinaisons exactes parmi {len(pieces)} pièces ouvertes",
                          candidats=[" + ".join(pieces[i].nom for i in e) for e in ex],
                          tiers=tnom, pieces_ouvertes=len(pieces), combinaisons=nb)
    retenues = [pieces[i] for i in ex[0]]
    # Garde-fou : le libellé cite un numéro de facture que ne porte aucune pièce appariée ->
    # le montant coïncide, mais ce n'est pas cette facture.
    cites = factures_citees(l.libelle)
    if cites and not ref_concorde(cites, retenues):
        refs = ", ".join(f"{p.nom} (réf. {p.ref or '—'})" for p in retenues)
        return Classement("D", f"{tnom}{origine} : le libellé cite la facture {', '.join(cites)}, absente des "
                               f"références de la combinaison au montant ({refs}) — appariement refusé",
                          candidats=[p.nom for p in retenues], tiers=tnom,
                          pieces_ouvertes=len(pieces), combinaisons=1)
    triviale = len(retenues) <= SEUIL_PIECES_APPARIEES and len(pieces) <= SEUIL_PIECES_OUVERTES
    classe = "A'1" if triviale else "A'2"
    motif = (f"{tnom}{origine} : seule combinaison exacte ({len(retenues)} pièce(s) parmi {len(pieces)} ouvertes)"
             + ("" if triviale else " — au-delà des seuils, coïncidence possible, à valider"))
    return Classement(classe, motif, geste=_geste_lettrer(retenues, l.montant),
                      candidats=[p.nom for p in retenues], tiers=tnom,
                      pieces_ouvertes=len(pieces), combinaisons=1, validation_comptable=triviale)


# --------------------------------------------------------------------------- #
# Contrôle des rapprochements automatiques de la nuit (robot de l'ERP)
# --------------------------------------------------------------------------- #

def anomalie_rapprochement_auto(compte_debit: str, compte_credit: str, piece_partielle: bool) -> str | None:
    """Motif d'alerte sur un appariement fait par le robot de l'ERP, ou None s'il est normal."""
    if compte_debit == compte_credit and compte_debit in COMPTES_PAIRES_EXCLUES:
        return None
    hors = [c for c in (compte_debit, compte_credit) if not c.startswith(PREFIXES_AUTO_NORMAUX)]
    if hors:
        return "compte hors 411/401 : " + ", ".join(sorted(set(hors)))
    if piece_partielle:
        return "pièce restée partiellement réglée"
    return None


# --------------------------------------------------------------------------- #
# Continuité des soldes bancaires : la ligne réimportée (doublon)
# --------------------------------------------------------------------------- #
# Cas fondateur : la reconnexion d'une banque a réimporté une ligne déjà supprimée, et une
# catégorie actée l'aurait imputée sans rien signaler. L'ERP ne garde aucune trace d'une
# ligne supprimée : le seul témoin est le solde que la banque joint à chaque ligne. L'écart
# « solde banque − solde ERP du compte du journal » à chaque date doit être constant.
# Un journal n'est contrôlé que si son écart n'a pris qu'au plus deux valeurs sur la fenêtre
# (la valeur de repos et celle d'un incident) : certaines banques transmettent un solde non
# arrêté à la date de la ligne, leur journal est alors « non contrôlable », jamais en alerte.

MIN_POINTS_CONTINUITE = 5
MAX_VALEURS_ECART = 2


@dataclass
class PointSolde:
    date: str
    soldes_banque: list          # soldes transmis à cette date (plusieurs si plusieurs imports)
    solde_erp: float             # solde du compte du journal, écritures jusqu'à `date`


def ecart_du_point(p: PointSolde) -> float:
    """Écart retenu à une date : le plus petit en valeur absolue parmi les soldes transmis."""
    return min((round(s - p.solde_erp, 2) for s in p.soldes_banque), key=abs)


def controle_continuite(points: list[PointSolde]) -> dict:
    """Diagnostic d'un journal : `fiable`, `alerte` (écart courant non nul sur un journal
    fiable) et `apparition` (date exclue, date incluse) de l'écart courant."""
    pts = sorted(points, key=lambda p: p.date)
    ecarts = [ecart_du_point(p) for p in pts]
    res = {"points": len(pts), "valeurs_ecart": len({cents(e) for e in ecarts}),
           "ecart": ecarts[-1] if ecarts else None, "fiable": False, "alerte": False, "apparition": None,
           "date": pts[-1].date if pts else None}
    if len(pts) < MIN_POINTS_CONTINUITE:
        return res
    res["fiable"] = res["valeurs_ecart"] <= MAX_VALEURS_ECART
    if not res["fiable"] or cents(ecarts[-1]) == 0:
        return res
    res["alerte"] = True
    k = len(ecarts) - 1
    while k > 0 and cents(ecarts[k - 1]) == cents(ecarts[-1]):
        k -= 1
    res["apparition"] = (pts[k - 1].date if k > 0 else None, pts[k].date)
    return res


def suspects_reimport(lignes: list[Ligne], journal_id: int, diag: dict) -> list[int]:
    """Lignes non rapprochées du journal, datées dans la fenêtre d'apparition, dont le montant
    compense exactement l'écart : c'est la ligne en trop."""
    if not diag.get("alerte") or not diag.get("apparition"):
        return []
    debut, fin = diag["apparition"]
    return [l.id for l in lignes if l.journal_id == journal_id and (debut is None or l.date > debut)
            and l.date <= fin and cents(l.montant) == cents(-diag["ecart"])]


def classement_reimport(diag: dict) -> Classement:
    return Classement("D", f"doublon probable : écart solde banque − solde ERP de {diag['ecart']:+.2f} € "
                           f"depuis le {diag['apparition'][1]}, et cette ligne compense exactement l'écart "
                           f"(ligne supprimée puis réimportée ?) — vérifier avant toute imputation")

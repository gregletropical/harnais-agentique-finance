"""Contrôles anti-fraude déterministes (règle 5 du §5 bis de la doctrine).

La fraude comptable — faux changement de RIB, faux virement urgent du dirigeant,
facture d'un sosie de fournisseur — se contrôle par du CODE contre le
référentiel des tiers, pas par le modèle. Un modèle peut être convaincu ; une
comparaison d'IBAN, non.

Ce module lit le texte du message (sujet, corps), mais c'est du code
déterministe, pas un modèle : il ne peut pas être « persuadé », et sa sortie est
une liste fermée de codes d'anomalie. Toute anomalie déclenche une revue humaine.

Ce qu'il ne remplace pas : le CONTRE-APPEL sur un numéro déjà connu du
fournisseur, qui reste humain par nature. Un mail parfaitement authentifié
(compte du fournisseur piraté) n'en dispense jamais.

Dans le système réel, le référentiel des tiers vient de l'ERP (comptes bancaires
connus du partenaire, historique des montants, commandes ouvertes). Ici, il vient
de `exemples/boite_exemple.json`.
"""
from __future__ import annotations

import re
import unicodedata

ANOMALIES = (
    "domaine_sosie",            # domaine proche d'un domaine connu (distance d'édition, inclusion, homographe)
    "iban_inconnu",             # un IBAN cité n'est pas un compte connu du partenaire
    "iban_sans_partenaire",     # un IBAN est cité par un émetteur qui n'est pas un partenaire connu
    "montant_hors_historique",  # montant supérieur au plafond de l'historique du partenaire
    "facture_sans_commande",    # facture qui ne cite aucune commande ouverte connue
    "piece_jointe_deguisee",    # type réel des octets différent de l'extension (posé par la passe)
)

RE_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")
RE_MONTANT = re.compile(r"(\d{1,3}(?:[  .]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s?(?:€|EUR\b|euros?\b)", re.I)
RE_COMMANDE = re.compile(r"\bBC-\d{4}(?:-\d+)?\b")
FACTEUR_PLAFOND = 3.0

# Petite table d'homoglyphes (cyrillique et grec usuels -> latin). Une table
# complète (Unicode TR39, « confusables ») serait préférable en production.
_HOMOGLYPHES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j",
    "ѕ": "s", "ԁ": "d", "һ": "h", "ӏ": "l", "А": "a", "Е": "e", "О": "o", "Р": "p", "С": "c",
    "ο": "o", "α": "a", "ε": "e", "ι": "i", "ν": "v", "τ": "t",
})


def levenshtein(a: str, b: str) -> int:
    """Distance d'édition classique (insertion, suppression, substitution)."""
    if len(a) < len(b):
        a, b = b, a
    prec = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cour = [i]
        for j, cb in enumerate(b, 1):
            cour.append(min(prec[j] + 1, cour[j - 1] + 1, prec[j - 1] + (ca != cb)))
        prec = cour
    return prec[-1]


def squelette(domaine: str) -> str:
    """Forme canonique pour comparer des domaines : NFKC, minuscules, homoglyphes ramenés au latin."""
    return unicodedata.normalize("NFKC", domaine).lower().translate(_HOMOGLYPHES)


def _etiquette(domaine: str) -> str:
    """Partie significative : `fournisseur-papeterie.test` -> `fournisseur-papeterie`."""
    parties = domaine.split(".")
    return ".".join(parties[:-1]) if len(parties) > 1 else domaine


def domaine_sosie(domaine: str, references: list[str]) -> str | None:
    """Rend le domaine de référence imité, ou None. Un domaine identique n'est pas un sosie."""
    if not domaine:
        return None
    sq = squelette(domaine)
    for ref in references:
        ref = ref.lower()
        if domaine == ref:
            return None
    for ref in references:
        ref = ref.lower()
        if sq == ref:                                     # homographe parfait
            return ref
        if levenshtein(sq, ref) <= 2:                     # coquille volontaire
            return ref
        et_ref, et = _etiquette(ref), _etiquette(sq)
        if len(et_ref) >= 6 and et_ref in et:             # `societe-exemple-support.test`
            return ref
    return None


def _montants(texte: str) -> list[float]:
    out = []
    for m in RE_MONTANT.finditer(texte):
        brut = re.sub(r"[  .]", "", m.group(1)).replace(",", ".")
        try:
            out.append(float(brut))
        except ValueError:
            continue
    return out


def ibans_cites(texte: str) -> list[str]:
    return [i.replace(" ", "") for i in RE_IBAN.findall(texte or "")]


def controler(domaine: str, sujet: str, corps: str, conf: dict) -> tuple[str, ...]:
    """Codes d'anomalie (liste fermée) pour un message. Tuple vide = rien de détecté."""
    tiers = {d.lower(): v for d, v in conf.get("tiers_connus", {}).items()}
    references = list(tiers) + [conf["domaine_interne"]]
    texte = f"{sujet}\n{corps}"
    anomalies: list[str] = []

    imite = domaine_sosie(domaine, references)
    if imite:
        anomalies.append("domaine_sosie")
    partenaire = tiers.get(domaine.lower())

    ibans = ibans_cites(texte)
    if ibans:
        if partenaire is None:
            anomalies.append("iban_sans_partenaire")
        elif any(i not in {k.replace(" ", "") for k in partenaire.get("ibans", [])} for i in ibans):
            anomalies.append("iban_inconnu")

    if partenaire and partenaire.get("montants_historiques"):
        plafond = max(partenaire["montants_historiques"]) * FACTEUR_PLAFOND
        if any(m > plafond for m in _montants(texte)):
            anomalies.append("montant_hors_historique")
    elif imite and _montants(texte):
        anomalies.append("montant_hors_historique")   # un sosie n'a pas d'historique : tout montant est hors historique

    if re.search(r"\bfacture\b", texte, re.I) and (partenaire or imite):
        commandes = set((partenaire or {}).get("commandes_ouvertes", []))
        if not (set(RE_COMMANDE.findall(texte)) & commandes):
            anomalies.append("facture_sans_commande")
    return tuple(dict.fromkeys(anomalies))

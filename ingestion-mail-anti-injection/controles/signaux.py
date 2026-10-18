"""Signaux de confiance calculés sur les EN-TÊTES (barrière 8 et règle 4 du §5 bis).

Tout se calcule hors ligne, sans appeler aucun service. Le corps du message n'est
jamais lu ici : la confiance ne se déduit que de ce que le fournisseur de
messagerie a posé à l'entrée, jamais de ce que l'expéditeur écrit.

Quatre règles qui font la valeur de ce module :

1. **Un verdict DMARC absent est un échec, jamais un neutre.** Une valeur inconnue
   devient `absent`.
2. **Seul l'en-tête `Authentication-Results` posé par NOTRE serveur compte.** Un
   expéditeur peut écrire lui-même un `Authentication-Results: ...; dmarc=pass`
   dans son message : on ne lit que l'en-tête dont l'identifiant de serveur
   (`authserv-id`, le premier jeton) est celui de la configuration, et on signale
   les autres comme une tentative de forge.
3. **Le filtrage contourné ou douteux bascule en traitement dégradé** : en-tête
   anti-spam `SFV:SK*` (filtrage sauté par une règle de transport), `compauth=fail`,
   catégorie anti-spam non vide, DMARC autre que `pass` hors courrier interne.
   En mode dégradé, on garde les métadonnées, aucun fait n'est tiré, et la seule
   proposition est la revue humaine.
4. **La confiance exige deux preuves** : DMARC `pass` ET un émetteur déjà en
   relation (domaine interne, tiers connu ou correspondant connu). L'une sans
   l'autre ne suffit pas. `authentifie` (la première preuve seule) suffit pour
   qu'une revue PROPOSE quelque chose à l'humain ; seule `confiance` ouvre un
   automatisme, l'extraction d'une pièce jointe ou un fait candidat.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

VERDICTS_DMARC = ("pass", "fail", "none", "neutral", "softfail", "temperror", "permerror", "absent")

# Liste fermée des drapeaux de non-confiance.
DRAPEAUX = (
    "dmarc_non_pass",             # fail, none, absent... hors courrier interne authentifié
    "entete_auth_forge",          # un Authentication-Results d'un autre serveur prétend un résultat
    "filtrage_contourne",         # SFV:SK, SFV:SKN, SFV:SKI... : le filtre anti-spam a été sauté
    "compauth_echec",             # authentification composite en échec
    "categorie_antispam",         # le fournisseur a catégorisé le message (phishing, spam...)
    "domaine_non_ascii",          # domaine internationalisé : risque d'homographe (IDN)
    "nom_affiche_avec_adresse",   # « Service <admin@interne> » <attaquant@ailleurs>
    "expediteur_illisible",       # pas d'adresse exploitable
)

RE_DMARC = re.compile(r"\bdmarc=([a-z]+)", re.I)
RE_SPF = re.compile(r"\bspf=([a-z]+)", re.I)
RE_DKIM = re.compile(r"\bdkim=([a-z]+)", re.I)
RE_COMPAUTH = re.compile(r"\bcompauth=([a-z]+)", re.I)
RE_ADRESSE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


@dataclass(frozen=True)
class Signaux:
    """Ce que l'orchestrateur sait de l'origine d'un message — rien d'autre."""
    domaine: str
    dmarc: str
    interne: bool
    connu: bool
    drapeaux: tuple
    authentifie: bool    # DMARC pass et aucun drapeau : l'origine est vérifiée
    confiance: bool      # authentifié ET émetteur déjà en relation
    mode: str            # "normal" | "degrade"

    def __post_init__(self):
        if self.dmarc not in VERDICTS_DMARC:
            raise ValueError("verdict DMARC hors liste")
        if set(self.drapeaux) - set(DRAPEAUX):
            raise ValueError("drapeau hors liste fermée")
        if self.mode not in ("normal", "degrade"):
            raise ValueError("mode inconnu")


def _authserv(valeur: str) -> str:
    return valeur.split(";", 1)[0].strip().lower()


def verdict_authentification(entetes: dict, serveur_de_confiance: str) -> tuple[dict, bool]:
    """(résultats lus sur l'en-tête de NOTRE serveur, forge détectée).

    On prend le PREMIER en-tête de notre serveur (le plus haut, posé en dernier, à
    l'entrée chez nous). Tout autre en-tête portant un résultat est une forge
    possible : il est ignoré et signalé.
    """
    res = {"dmarc": "absent", "spf": "absent", "dkim": "absent", "compauth": "absent"}
    trouve, forge = False, False
    for v in entetes.get("authentication-results", []):
        if _authserv(v) == serveur_de_confiance.lower():
            if not trouve:
                for cle, rx in (("dmarc", RE_DMARC), ("spf", RE_SPF), ("dkim", RE_DKIM), ("compauth", RE_COMPAUTH)):
                    m = rx.search(v)
                    if m:
                        res[cle] = m.group(1).lower()
                trouve = True
        elif RE_DMARC.search(v) or RE_SPF.search(v) or RE_DKIM.search(v):
            forge = True
    if res["dmarc"] not in VERDICTS_DMARC:
        res["dmarc"] = "absent"   # une valeur inconnue n'est jamais traitée comme neutre
    return res, forge


def calculer(message, conf: dict) -> Signaux:
    """`message` : objet portant `entetes`, `domaine`, `adresse_expediteur`, `nom_affiche`.
    `conf` : configuration de la boîte (cf. exemples/boite_exemple.json)."""
    drapeaux: list[str] = []
    auth, forge = verdict_authentification(message.entetes, conf["serveur_auth_de_confiance"])
    dmarc = auth["dmarc"]
    domaine = message.domaine
    if not message.adresse_expediteur or not domaine:
        drapeaux.append("expediteur_illisible")
    if forge:
        drapeaux.append("entete_auth_forge")
    try:
        domaine.encode("ascii")
    except UnicodeEncodeError:
        drapeaux.append("domaine_non_ascii")
    if domaine.startswith("xn--") or ".xn--" in domaine:
        drapeaux.append("domaine_non_ascii")
    if RE_ADRESSE.search(message.nom_affiche or "") and message.adresse_expediteur not in (message.nom_affiche or ""):
        drapeaux.append("nom_affiche_avec_adresse")

    antispam = " ".join(message.entetes.get("x-forefront-antispam-report", []))
    if re.search(r"\bSFV:SK", antispam):
        drapeaux.append("filtrage_contourne")
    m = re.search(r"\bCAT:([A-Z]+)", antispam)
    if m and m.group(1) != "NONE":
        drapeaux.append("categorie_antispam")
    if auth["compauth"] == "fail":
        drapeaux.append("compauth_echec")

    interne = domaine == conf["domaine_interne"].lower() and dmarc == "pass"
    if dmarc != "pass" and not interne:
        drapeaux.append("dmarc_non_pass")
    connu = (interne
             or domaine in {d.lower() for d in conf.get("tiers_connus", {})}
             or message.adresse_expediteur in {a.lower() for a in conf.get("correspondants_connus", [])})
    drapeaux = tuple(dict.fromkeys(drapeaux))
    authentifie = not drapeaux and dmarc == "pass"
    confiance = authentifie and connu
    return Signaux(domaine=domaine, dmarc=dmarc, interne=interne, connu=connu, drapeaux=drapeaux,
                   authentifie=authentifie, confiance=confiance, mode="normal" if not drapeaux else "degrade")

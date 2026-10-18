"""
categories.py — Paramétrage de la routine de lettrage : seuils, comptes techniques
et catégories d'imputation sans facture ACTÉES (classe I).

C'est le fichier qu'on modifie quand une règle évolue. La logique de classement,
elle, vit dans `classement.py` et ne change pas à chaque arbitrage.

Doctrine, à respecter avant toute modification :

- Une catégorie n'entre ici qu'APRÈS arbitrage de l'utilisateur (le DAF), avec ses
  précédents relevés dans le grand livre et la décision qui l'a actée (champ
  `decision`). L'agent peut la proposer, il ne l'ajoute jamais de lui-même.
- Toute nouvelle catégorie arrive avec ses tests (`tests/test_regles.py`).
- Une catégorie reconnue mais dont le compte n'est pas tranché porte `a_arbitrer` :
  elle est signalée avec son motif, jamais exécutée.

Les libellés bancaires, tiers et décisions ci-dessous sont fictifs ; la structure,
le nombre et la nature des catégories reprennent le paramétrage réel. Les comptes
sont ceux du plan comptable général, à six chiffres.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Seuils
# --------------------------------------------------------------------------- #

SEUIL_PIECES_APPARIEES = 3      # A'1 : au plus 3 pièces dans la combinaison retenue
SEUIL_PIECES_OUVERTES = 8       # A'1 : au plus 8 pièces ouvertes chez le tiers
MAX_PIECES_ENUMEREES = 40       # au-delà, l'énumération des combinaisons n'est pas tentée -> D
FENETRE_NBT_JOURS = 5           # N : paiements en cours datés au plus 5 jours avant la ligne
FENETRE_DOUBLE_PAIEMENT_JOURS = 30   # D : facture au montant exact payée dans les 30 jours précédents
MIN_PRECEDENTS = 2              # tiers par précédent bancaire : au moins 2 lignes rapprochées, unanimes
MAX_PREFIXES_ECHEANCES = 5000   # A par échéance : au-delà, l'énumération des préfixes n'est pas tentée
FRAICHEUR_SYNCHRO_HEURES = 24   # une banque non synchronisée depuis plus longtemps se signale

# Tolérance d'appariement : AUCUNE. Tout se compare en centimes entiers. Un écart,
# même d'un centime, sort la ligne des exécutables ; l'écart se passe ensuite par une
# écriture explicite après arbitrage, jamais par une tolérance silencieuse.

# --------------------------------------------------------------------------- #
# Comptes techniques
# --------------------------------------------------------------------------- #

COMPTE_ATTENTE_BANQUE = "471000"         # contrepartie d'attente des lignes importées
COMPTE_PAIEMENTS_EN_COURS = "512300"     # paiements émis, pas encore passés en banque

# Paires générées seules par l'ERP à chaque lettrage client (TVA sur encaissements
# et son transit) : jamais des anomalies du contrôle des rapprochements automatiques.
COMPTES_PAIRES_EXCLUES = frozenset({"445740", "445800"})
# Préfixes des appariements normaux du robot de rapprochement de l'ERP.
PREFIXES_AUTO_NORMAUX = ("411", "401", COMPTE_PAIEMENTS_EN_COURS)

# --------------------------------------------------------------------------- #
# Sociétés tenues dans l'ERP (exemple : deux sociétés)
# --------------------------------------------------------------------------- #

SOCIETE_A, SOCIETE_B = 1, 2

# Tiers fixes posés par certaines catégories (identifiants du référentiel d'exemple).
TIERS_HEBERGEUR_CLOUD = 901
TIERS_ENERGIE = 902


@dataclass(frozen=True)
class CategorieI:
    code: str
    motif: str                    # expression régulière sur le libellé normalisé
    sens: int                     # +1 encaissement, -1 décaissement
    compte: str
    decision: str                 # l'arbitrage qui a acté la catégorie
    societes: frozenset | None = None   # None = toutes les sociétés
    partenaire_id: int | None = None    # tiers à poser sur la ligne (401 d'un fournisseur)
    lettrage: str | None = None         # "od_ca3" (contrôle bloquant) | "paie" (signalé)
    apres_factures: bool = False        # ne s'applique que si aucune facture ne correspond
    comptes: dict | None = None         # compte propre à une société, sinon `compte`
    sans_tiers: bool = False            # un tiers posé sur la ligne écarte l'imputation -> D
    montant_max: float | None = None    # au-delà (valeur absolue) -> D, motif `hors_plafond`
    hors_plafond: str = ""
    a_arbitrer: str = ""                # reconnue mais compte non tranché -> D, jamais exécutée

    def compte_de(self, societe_id: int | None) -> str:
        return (self.comptes or {}).get(societe_id, self.compte)


CATEGORIES_I: tuple[CategorieI, ...] = (
    # Organismes sociaux : indemnités journalières reçues.
    CategorieI("IJSS", r"/FRM CPAM\b|\bIJSS\b", +1, "467000", "Arbitrage A01"),
    # Taxe sur les salaires, prélevée par la DGFiP.
    CategorieI("TAXE_SALAIRES", r"LIB/TS-\d{6}-", -1, "631100", "Arbitrage A02"),
    # Prélèvement d'un fournisseur certain dont la facture arrive plus tard : 401 du tiers.
    CategorieI("CLOUD_SANS_FACTURE", r"^PRLV\b.*HEBERGEUR CLOUD", -1, "401000", "Arbitrage A03",
               partenaire_id=TIERS_HEBERGEUR_CLOUD),
    CategorieI("AVANCE_SALAIRE", r"/PID ACOMPTE \d{2}-\d{2}\b", -1, "425000", "Arbitrage A04"),
    # Prélèvement à la source sur DSN : imputé, puis lettré avec la paie du mois (signalé).
    CategorieI("PAS_DSN", r"IMPOT-PAS-DSN-", -1, "442100", "Arbitrage A05", lettrage="paie"),
    # Paiement de la CA3 : imputé ET lettré avec l'OD de déclaration du mois. Contrôle
    # bloquant : une seule OD ouverte du même montant, sinon D.
    CategorieI("CA3", r"LIB/TVA-\d{6}-3310CA3", -1, "445510", "Arbitrage A06", lettrage="od_ca3"),
    CategorieI("PREVOYANCE", r"^PRLV SEPA MUTUELLE PREVOYANCE EXEMPLE\b", -1, "437000", "Arbitrage A07"),
    # Fournisseur d'énergie : 401 du tiers, mais seulement à défaut de facture ouverte.
    CategorieI("ENERGIE", r"^PRLV SEPA FOURNISSEUR ENERGIE EXEMPLE\b", -1, "401000", "Arbitrage A08",
               partenaire_id=TIERS_ENERGIE, apres_factures=True),
    # Frais bancaires : libellés de la banque elle-même, ancrés en début de libellé (un
    # « PRLV … » fournisseur ne peut pas y entrer). Liste FERMÉE. Compte différent selon
    # la société ; écartés si un tiers est posé sur la ligne.
    CategorieI("FRAIS_BANCAIRES",
               r"^(?:COMMISSIONS FACTURE NUMERO \d+$|INTERETS ET COMMISSIONS\b|COMMISSIONS PERCUES\b"
               r"|COTISATION TRANSFERT DE FICHIERS\b|COMMISSION ENCAISSEMENT CARTE\b|FRAIS EURO PRLV\b"
               r"|FRAIS DE TENUE DE COMPTE$|COMMISSIONS$|\*? *\d{7} MVT\(S\) VIR\b)",
               -1, "627800", "Arbitrage A09", comptes={SOCIETE_A: "627000"}, sans_tiers=True),
    # Abonnement de banque en ligne : même code, entrée propre, car sa table de comptes
    # diffère (la table `comptes` vaut pour TOUTE une entrée).
    CategorieI("FRAIS_BANCAIRES", r"^ABON BANQUE EN LIGNE PREMIUM\b", -1, "627800", "Arbitrage A10",
               comptes={SOCIETE_A: "627000", SOCIETE_B: "627000"}, sans_tiers=True),
    # Virement de paie groupé : au moins 20 bénéficiaires (les lots de notes de frais n'en
    # comptent jamais autant, ils relèvent de la classe N).
    CategorieI("PAIE_GROUPEE", r"^VIR SEPA EMIS /PID PAIE-\d+ .*/NBT 0*(?:[2-9]\d|[1-9]\d{2,})\b", -1,
               "421000", "Arbitrage A11", lettrage="paie"),
    # Virement de paie au libellé mensuel, sans compteur de bénéficiaires.
    CategorieI("PAIE_MENSUELLE", r"^VIR SEPA EMIS /PID PAIE MOIS \d{2}-?\d{2}(?:\d{2})?\b", -1, "421000",
               "Arbitrage A11", lettrage="paie"),
    # Intérêts d'un prêt : le plafond écarte l'échéance qui porte du capital
    # (ventilation capital / intérêts à faire à la main).
    CategorieI("PRET_INTERETS", r"^ECHEANCE PRET MOYEN TERME\b", -1, "661100", "Arbitrage A12",
               montant_max=50_000,
               hors_plafond="échéance de prêt au-delà de 50 000 € : échéance qui porte du capital, "
                            "ventilation capital 164000 / intérêts 661100 à faire à la main"),
    CategorieI("PRET_COMMISSION", r"^COMMISSION ANNUELLE PRET MOYEN TERME\b", -1, "661100",
               "Arbitrage A12"),
    CategorieI("TITRES_BANQUE", r"^SOUSCRIPTION TITRES BANQUE$", -1, "271000", "Arbitrage A13"),
    CategorieI("INTERETS_TITRES_BANQUE", r"^INTERETS TITRES BANQUE$", +1, "762100", "Arbitrage A14"),
    # Frais mensuels de tenue et de services : liste fermée, plafonnée.
    CategorieI("FRAIS_BANCAIRES_PLAFONNES",
               r"^(?:\* *\d{7} OPE RLV COMPTE$|\* *FORFAIT SERVICES EN LIGNE$|PRLV SERVICE PAIEMENT EXEMPLE\b)",
               -1, "627000", "Arbitrage A15", sans_tiers=True,
               montant_max=100, hors_plafond="frais bancaires au-delà de 100 € : à vérifier sur le relevé"),
    CategorieI("PREVOYANCE_RECUE", r"/FRM ASSUREUR PREVOYANCE EXEMPLE\b.*/RNF PREVOYANCE\b", +1, "437200",
               "Arbitrage A16", societes=frozenset({SOCIETE_A})),
    # Reconnue, compte non tranché : un seul précédent, au crédit d'un compte de charge.
    CategorieI("REMBOURSEMENT_ASSURANCE", r"/FRM ASSUREUR DOMMAGES EXEMPLE\b", +1, "616000", "en attente",
               a_arbitrer="remboursement d'assurance, précédent unique au crédit du 616000 : "
                          "compte à arbitrer"),
)

# Motifs de libellé qui déclenchent une classe sans catégorie.
MOTIF_REMBOURSEMENT = r"TROP PER[CÇ]U|REMBOURS|\bRBT\b"
MOTIF_NBT = r"/NBT 0*(\d+)\b"
MOTIF_ECHEANCIER = r"\bECHEANCIER (\d+)/(\d+)\b"

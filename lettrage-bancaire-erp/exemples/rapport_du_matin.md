# Rapport de lettrage du matin — 2026-10-16 07:00:00 UTC

Horodatage : 2026-10-16 07:00:00 UTC. Fenêtre des nouveautés : depuis 2026-10-15 06:30:00 UTC.

**33 lignes non rapprochées** : 16 exécutables, 3 à arbitrer, 14 exceptions.

## Synchronisation bancaire

- BANQUE 1 : dernier passage 2026-10-16 06:20:00 UTC
- BANQUE 2 : dernier passage 2026-10-16 06:21:00 UTC
- BANQUE 3 : dernier passage 2026-10-14 17:50:00 UTC — **ALERTE : pas de synchronisation depuis 37 h**

## Continuité des soldes bancaires

- BANQUE 1 : non contrôlable (6 écarts différents sur 6 dates : la banque transmet un solde non arrêté à la date)
- **ALERTE BANQUE 2** : écart solde banque − solde ERP de 150,00 € au 2026-10-15, écart apparu entre le 2026-10-13 et le 2026-10-14 (ligne supprimée puis réimportée, ou ligne manquante)
- BANQUE 3 : d'équerre au 2026-10-14

## 1. Exécutable sur simple GO

| Classe | Ligne | Date | Montant | Libellé | Traitement prévu |
|---|---|---|---|---|---|
| A | 1 | 2026-10-15 | 3 600,00 € | VIR SEPA RECU /FRM ALPHA LOGICIELS /RNF FV 00129 | référence citée, montant = reste dû — FV-2026-00129 |
| A | 2 | 2026-10-15 | 5 040,00 € | VIR SEPA RECU /FRM BETA CONSEIL /RNF FV 00131 FV 00132 | référence citée, montant = reste dû — FV-2026-00131, FV-2026-00132 |
| A | 3 | 2026-10-15 | 1 250,00 € | VIR SEPA RECU /FRM GAMMA INDUSTRIE /RNF FV 00128 | référence citée, montant = échéance(s) ouverte(s) la(les) plus ancienne(s) — FV-2026-00128 échéance 2026-10-05 (1250.00) |
| A'1 | 4 | 2026-10-15 | 2 160,00 € | VIR SEPA RECU /FRM DELTA SERVICES /RNF REGLEMENT OCTOBRE | DELTA SERVICES : seule combinaison exacte (2 pièce(s) parmi 3 ouvertes) — FV-2026-00121, FV-2026-00123 · validation a posteriori demandée au comptable |
| A'1 | 33 | 2026-10-15 | 4 800,00 € | VIR SEPA RECU /FRM UPSILON GESTION /RNF PAIEMENT OCTOBRE | HOLDING U.G. PARTICIPATIONS (tiers par précédent bancaire : 3 lignes du même émetteur « UPSILON GESTION ») : seule combinaison exacte (1 pièce(s) parmi 1 ouvertes) — FV-2026-00120 · validation a posteriori demandée au comptable |
| B | 6 | 2026-10-15 | -12 480,35 € | VIR SEPA EMIS /PID LOT FOURNISSEURS 2026-10-A | lot LOT/2026/0042 au montant exact — LOT/2026/0042 |
| N | 7 | 2026-10-15 | -642,90 € | VIR SEPA EMIS /PID NOTES DE FRAIS 10-2026 /NBT 3 | virement groupé : seule combinaison de 3 paiements en cours — NDF/2026/0412, NDF/2026/0413, NDF/2026/0414 |
| R | 8 | 2026-10-15 | -480,00 € | VIR SEPA EMIS /PID ZETA HOLDING REMBOURSEMENT TROP PERCU | remboursement : seule ligne client ouverte de ZETA HOLDING au montant exact — AV-2026-00031 |
| I | 9 | 2026-10-15 | 412,37 € | VIR SEPA RECU /FRM CPAM DE LA REGION /RNF IJSS 092026 | IJSS → 467000 (Arbitrage A01) |
| I | 10 | 2026-10-15 | -38,40 € | COMMISSIONS FACTURE NUMERO 70004417 | FRAIS_BANCAIRES → 627000 (Arbitrage A09) |
| I | 11 | 2026-10-15 | -18 245,00 € | PRLV SEPA DGFIP LIB/TVA-092026-3310CA3 | CA3 → 445510, lettrage avec OD/2026/09/0007 (CA3 de septembre) (Arbitrage A06) — OD/2026/09/0007 (CA3 de septembre) |
| I | 12 | 2026-10-15 | -3 412,18 € | PRLV SEPA MUTUELLE PREVOYANCE EXEMPLE ECH/151026 ID EMETTEUR | PREVOYANCE → 437000 (Arbitrage A07) |
| I | 13 | 2026-10-15 | -184 320,55 € | VIR SEPA EMIS /PID PAIE-202610 SALAIRES /NBT 062 | PAIE_GROUPEE → 421000 (Arbitrage A11) — lettrage avec la paie du mois à faire ensuite |
| I | 14 | 2026-10-14 | -265,10 € | PRLV SEPA FOURNISSEUR ENERGIE EXEMPLE ECH/141026 ID EMETTEUR | ENERGIE → 401000 (Arbitrage A08) |
| I | 15 | 2026-10-15 | -1 120,00 € | PRLV SEPA DGFIP LIB/TS-092026-0001 | TAXE_SALAIRES → 631100 (Arbitrage A02) |
| I | 30 | 2026-10-15 | -18,60 € | * 0000042 OPE RLV COMPTE | FRAIS_BANCAIRES_PLAFONNES → 627000 (Arbitrage A15) |

## 2. À arbitrer — une proposition existe, décision humaine

| Classe | Ligne | Date | Montant | Société | Libellé | Motif |
|---|---|---|---|---|---|---|
| A'2 | 5 | 2026-10-15 | 5 455,77 € | SOCIETE A | VIR SEPA RECU /FRM EPSILON DISTRIBUTION /RNF PAIEMENT FACTUR | EPSILON DISTRIBUTION : seule combinaison exacte (4 pièce(s) parmi 10 ouvertes) — au-delà des seuils, coïncidence possible, à valider — FV-2026-00103, FV-2026-00106, FV-2026-00108 |
| C | 16 | 2026-10-15 | 1 000,00 € | SOCIETE A | VIR SEPA RECU /FRM ETA EDITIONS /RNF FV 00124 | règlement partiel de FV-2026-00124 (reste dû 2400.00, aucune échéance ne correspond) — FV-2026-00124 |
| E | 26 | 2026-10-15 | 1 500,00 € | SOCIETE A | VIR SEPA RECU /FRM OMICRON SANTE /RNF ECHEANCIER 2/4 FACTURE | échéancier 2/4 de OMICRON SANTE : 2 ligne(s) du périmètre (factures du 15/07, 15/08, 2 pièce(s), 2500.00) dans l'ordre, dernière partielle — proposition à valider — FV-2026-00113, FV-2026-00114 (partielle, reste 1000.00) |

## 3. Exceptions — anomalie à instruire, rien n'est proposé

| Classe | Ligne | Date | Montant | Société | Libellé | Motif |
|---|---|---|---|---|---|---|
| D | 17 | 2026-10-15 | 1 812,00 € | SOCIETE A | VIR SEPA RECU /FRM THETA RETAIL /RNF FV 00126 | référence citée mais montant ≠ reste dû (écart +12.00, tolérance nulle) — FV-2026-00126 (1800.00) |
| D | 18 | 2026-10-15 | 950,00 € | SOCIETE A | VIR SEPA RECU /FRM KAPPA INNOVATIONS SARL /RNF CONTRAT ANNUE | aucune correspondance : tiers inconnu, aucune pièce au montant |
| D | 19 | 2026-10-15 | 640,00 € | SOCIETE A | VIR SEPA RECU /FRM LAMBDA CONSULTING /RNF PRESTATION | tiers incertain : pièce(s) au montant exact chez un tiers dont le nom ne correspond pas au libellé — FV-2026-00125 — OMEGA MEDIA |
| D | 20 | 2026-10-15 | 1 500,00 € | SOCIETE A | VIR SEPA RECU /FRM MU TECHNOLOGIES /RNF REGLEMENT | MU TECHNOLOGIES : 2 combinaisons exactes parmi 4 pièces ouvertes — FV-2026-00115 + FV-2026-00116, FV-2026-00117 + FV-2026-00118 |
| D | 21 | 2026-10-15 | -356,40 € | SOCIETE A | PRLV SEPA NU FOURNITURES ECH/151026 ID EMETTEUR/FR00ZZZ99900 | NU FOURNITURES : aucune pièce ouverte — facture FA-NU-2026-0912 au montant exact déjà payée le 2026-10-01 : double paiement probable |
| D | 22 | 2026-10-15 | -587,40 € | SOCIETE A | VIR SEPA EMIS /PID XI SOFTWARE - REF/FACTURE 90000123 | XI SOFTWARE : le libellé cite la facture 90000123, absente des références de la combinaison au montant (FA-XI-2026-0311 (réf. INV-90000045)) — appariement refusé — FA-XI-2026-0311 |
| D | 23 | 2026-10-15 | -62 500,00 € | SOCIETE B | ECHEANCE PRET MOYEN TERME T4 2026 | PRET_INTERETS : échéance de prêt au-delà de 50 000 € : échéance qui porte du capital, ventilation capital 164000 / intérêts 661100 à faire à la main |
| D | 24 | 2026-10-15 | -15,00 € | SOCIETE A | FRAIS DE TENUE DE COMPTE | FRAIS_BANCAIRES : tiers posé sur la ligne (BANQUE PRINCIPALE EXEMPLE) — imputation automatique écartée |
| D | 25 | 2026-10-15 | 2 340,00 € | SOCIETE B | VIR SEPA RECU /FRM ASSUREUR PREVOYANCE EXEMPLE /RNF PREVOYAN | catégorie PREVOYANCE_RECUE (437200) reconnue, mais actée seulement pour d'autres sociétés — extension à arbitrer |
| D | 29 | 2026-10-14 | -150,00 € | SOCIETE B | SOUSCRIPTION TITRES BANQUE | doublon probable : écart solde banque − solde ERP de +150.00 € depuis le 2026-10-14, et cette ligne compense exactement l'écart (ligne supprimée puis réimportée ?) — vérifier avant toute imputation |
| D | 32 | 2026-10-15 | 820,00 € | SOCIETE A | VIR SEPA RECU /FRM ASSUREUR DOMMAGES EXEMPLE /RNF REMBOURSEM | REMBOURSEMENT_ASSURANCE : remboursement d'assurance, précédent unique au crédit du 616000 : compte à arbitrer — signalé, jamais exécuté |

Stock déjà signalé lors d'un passage précédent (3 ligne(s), non ré-analysé) :

| Classe | Ligne | Date | Montant | Société | Libellé | Motif |
|---|---|---|---|---|---|---|
| P | 27 | 2026-10-10 | -1 040,00 € | SOCIETE A | PRLV SEPA PI LOCATIONS ECH/101026 | contreparties déjà posées sur 613200 — le solde en attente ne correspond pas forcément au reste dû |
| D | 28 | 2025-12-30 | 700,00 € | SOCIETE A | VIR SEPA RECU /FRM RHO CONSEIL /RNF FV 00101 | exercice clos (verrou au 2025-12-31) — signalé, jamais exécuté |
| D | 31 | 2026-10-12 | 300,00 € | SOCIETE A | VIR SEPA RECU /FRM SIGMA /RNF ACOMPTE ETUDE | tiers ambigu : 2 tiers correspondent à « SIGMA » — SIGMA CONSEIL, SIGMA ETUDES |

## 4. Rapprochements automatiques de la nuit

4 rapprochement(s) faits par le robot de l'ERP, **2 anomalie(s)** :
- 3 400,00 € 416000 ↔ 411000 (FV-2026-00102) : compte hors 411/401 : 416000
- 850,00 € 401000 ↔ 512300 (FA-2026-0877) : pièce restée partiellement réglée

## 5. Dérive depuis la veille

- Avances non lettrées de plus de 45 jours (401/411) : 12 lignes, 18 430,00 € → 13 lignes, 19 105,00 €
- 471000 compte d'attente de la banque : -2 310,45 € → -1 905,10 €

## GO attendu

Les lignes de la section 1 s'exécutent sur GO explicite, cité mot pour mot dans le plan d'écriture :

```
python controles/plan_ecriture.py --etat <ce_fichier>.json --go "<citation exacte du GO>"
```

Les sections 2 et 3 ne s'exécutent jamais par le script : chaque cas est instruit, proposé avec ses options, et tranché par l'utilisateur.


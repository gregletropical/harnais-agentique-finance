---
description: "Routine comptable du matin : lettrage bancaire, suivi des activités, analyse des cas nouveaux, rapport pour GO, exécution et formalisation"
allowed-tools: ["Bash", "Read", "Grep", "Edit", "Write", "Agent"]
---

# /routine-matin

Arguments reçus : `$ARGUMENTS` — consigne éventuelle de l'utilisateur pour ce passage (ex. « sans le suivi », « seulement le lettrage »).

Tu déroules la routine comptable du matin du client. **La procédure complète et autoportante est dans `instructions/routine-matinale.md`** : lis-la en entier avant toute action, puis suis-la étape par étape.

Rappels qui ne se négocient pas :

1. **Étapes 1 à 4 sans t'arrêter** : état des lieux, premier passage du script, suivi des activités et mentions, analyse des cas nouveaux (en parallèle quand ils sont indépendants). Tu ne rends la main qu'avec le **rapport final** pour GO.
2. **Rien ne s'écrit dans l'ERP sans GO de l'utilisateur en conversation**, recopié mot pour mot dans le compte rendu. Simulation d'abord, relecture après.
3. **Personne n'est sollicité** sauf blocage par un élément extérieur — sinon on agit, ou on demande l'arbitrage à l'utilisateur (`instructions/regles-de-conduite-erp.md`).
4. Classes, catégories et garde-fous : `instructions/specification-classement.md`. Toute écriture hors du périmètre du script passe par `instructions/protocole-prevol.md`.

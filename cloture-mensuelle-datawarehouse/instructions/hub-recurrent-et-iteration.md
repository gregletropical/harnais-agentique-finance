# Hub récurrent et itération enregistrée

Comment un process mensuel est tenu dans la base de connaissances que l'agent lit et écrit (un coffre de notes Markdown versionné). Version anonymisée de la doctrine réelle.

## Trois objets, trois rôles

| Objet | Ce qu'il porte | Qui le modifie, quand |
|---|---|---|
| **Hub récurrent** (`recurrence: mensuelle`) | La procédure **courante et optimisée** : cadre, échéances, sources, pièges, et un `## Journal du process` (une ligne datée par évolution) | Après une itération, à la lumière de ce qu'elle a appris ; jamais en cours de mois |
| **Note process** liée au hub | La **chaîne canonique** : un tableau `# · Étape · Qui · Énergie · Durée · Dépend de · Jour cible` (cf. `chaine-canonique.md`) | Idem |
| **Note d'itération** (`<Client> - Clôture AAAA-MM`, `projet:` vers le hub) | L'**enregistrement** de ce qui s'est réellement passé ce mois-là : chaîne instanciée, résultats, blocages, enseignements | Écrite pendant et juste après le run ; **jamais retouchée ensuite** |

Le panneau de liens entrants du hub est l'historique des itérations : rien à maintenir à la main.

## Instanciation

Chaque mois, une commande dédiée crée la note d'itération depuis la chaîne canonique :

- chaque étape devient une ligne de tâche avec un **identifiant unique** et ses **dépendances** (`🆔` / `⛔`), régénérés à chaque instanciation ;
- les **dates cibles sont calculées** depuis `J` (1er jour ouvré du mois suivant) et les décalages de la chaîne ;
- les **jalons** (entrants gelés, données publiables, mois soldé) dépendent de toutes leurs étapes amont : ils restent bloqués par construction tant qu'une étape est ouverte, et leur franchissement est un geste humain, jamais un automatisme.

Une chaîne récurrente **s'instancie**, elle ne se régénère pas : une tâche répétitive automatique perdrait ses dépendances à chaque occurrence.

## Pourquoi l'itération est un enregistrement

**L'écart entre l'itération et le hub mesure le progrès.** Une étape non jouée est marquée annulée avec son motif, pas effacée : c'est la mesure de ce que le process apporte. Si l'on réécrivait l'itération après coup, on perdrait précisément l'information qui permet d'améliorer le hub.

Quand on revient sur une clôture soldée (un ajustement annulé, une imputation corrigée), la reprise se consigne en **addendum daté** dans l'itération concernée : ce qui change, pourquoi, et ce que la période vaut désormais. Le résumé de la note est complété pour que les vues ne portent pas un chiffre périmé seul. Les chiffres publiés le jour du run restent tels quels.

## Modèle de note d'itération

```markdown
---
type: projet-chantier
status: active            # done quand le jalon final est franchi
projet: "[[<Client> - Clôture Mensuelle]]"
summary: "Itération AAAA-MM : jouée à J+n ; CA, marge ; blocages ; enseignement principal."
---

# <Client> — Clôture AAAA-MM

> `J` = <date>. Run le <date>, soit `J+n` jours ouvrés (cible J+5).
> Enregistrement : cette note ne se réécrit pas ; une reprise s'y consigne en addendum daté.

## Ce qui n'a pas eu lieu
(étapes de la chaîne non jouées, et pourquoi)

## Chaîne instanciée
- [x] #task #admin A5 — Gel : extraction du grand livre 🆔 a5xxxx ✅ AAAA-MM-JJ
- [-] #task #admin A2 — Détection par API 🆔 a2xxxx — *non jouée : motif*
- [J] #task 🏁 JALON — Données publiables 🆔 c5xxxx ⛔ c4xxxx
(...)

## Résultat métier
(tableau du mois à côté de M-1 et de M-12)

## Log du déroulé réel
(durée, passes, blocages dans l'ordre, interventions humaines prévues et imprévues)

## Ce que l'itération apprend
(numéroté ; c'est ce qui remonte dans le journal du hub)
```

## Ce que deux itérations réelles ont appris

Restitution anonymisée, sans chiffres ni noms : c'est la mécanique qui compte.

**Première itération (enregistrée après coup).** Le run technique était court ; la clôture, elle, a d'abord glissé de plusieurs semaines faute de déclencheur. Aucun blocage technique ne l'expliquait : c'est l'absence de calendrier et de déclencheur qui avait laissé filer le mois, et un calendrier en jours relatifs l'a rendu visible pour la première fois. La même itération a rappelé qu'un contrôle dormant peut mentir longtemps ; que des corrections faites à la main dans une table brute sont perdues au rechargement suivant ; et qu'un petit écart de paie, qu'un seuil de matérialité aurait absorbé, peut être la trace d'une erreur d'imputation déjà connue ailleurs. D'où trois règles : tolérance zéro, registre d'anomalies versionné, et un test par contrôle, qui le fait échouer volontairement.

**Deuxième itération (la première instanciée depuis le hub).** La clôture sort désormais **le jour même (`J+0`)**, **sans avoir changé la technique** : le hub récurrent, sa chaîne datée et le déclencheur « premier jour ouvré » ont suffi à faire disparaître le retard. Le run a en revanche dû être rejoué : le premier export du cutoff était amputé de l'essentiel de son chiffre d'affaires, et il a traversé le pré-vol d'ouverture, la validation structurelle, tout le pipeline et tous les contrôles de qualité **sans un avertissement**. C'est le récapitulatif, qui met le mois à côté de l'historique, qui l'a fait voir à l'humain. D'où le contrôle de vraisemblance contre les douze mois précédents (`controles/vraisemblance.py`), devenu bloquant. Deux autres enseignements : sauter le rechargement d'une source pouvait être juste (il aurait effacé des corrections), mais sauter son traitement en aval aurait corrompu les rattachements en silence ; et une valeur reconstituée pour débloquer le pipeline doit se distinguer d'une valeur saisie, sinon elle entre dans le prévisionnel client sans marqueur.

**La leçon de fond** : le retard d'une clôture est presque toujours un problème de déclencheur et de process, pas de technique. La technique, elle, doit surtout savoir **dire non** avant la diffusion, et chaque « non » doit pouvoir être expliqué, enregistré et relu le mois suivant.

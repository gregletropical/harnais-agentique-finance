-- stg_paie_livre_compte : livre de paie ventilé en comptes par la table de passage rubrique -> compte.
-- Une rubrique sans compte garde compte NULL : le pipeline la refuse (décision humaine attendue).
CREATE TABLE stg_paie_livre_compte AS
SELECT l.mois, l.matricule, l.rubrique, r.compte, ROUND(l.montant, 2) AS montant
FROM raw_livre_paie l
LEFT JOIN ref_passage_rubrique r ON r.rubrique = l.rubrique;

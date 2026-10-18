-- ctrl_cadrage_paie : livre de paie ventilé (stg_paie_livre_compte) contre journal de paie de la
-- comptabilité (raw_grand_livre, journal PA), par compte, sur le cumul borné à l'intersection temporelle
-- des deux sources. Tolérance zéro : un écart s'explique au registre d'exceptions, il n'est jamais absorbé.
CREATE TABLE ctrl_cadrage_paie AS
WITH bornes AS (
    SELECT MAX((SELECT MIN(mois) FROM stg_paie_livre_compte),
               (SELECT MIN(substr(date, 1, 7)) FROM raw_grand_livre WHERE journal = :journal)) AS mois_min,
           MIN((SELECT MAX(mois) FROM stg_paie_livre_compte),
               (SELECT MAX(substr(date, 1, 7)) FROM raw_grand_livre WHERE journal = :journal)) AS mois_max
),
livre AS (
    SELECT compte, ROUND(SUM(montant), 2) AS solde FROM stg_paie_livre_compte, bornes
    WHERE mois BETWEEN bornes.mois_min AND bornes.mois_max GROUP BY compte
),
pa AS (
    SELECT compte, ROUND(SUM(debit - credit), 2) AS solde FROM raw_grand_livre, bornes
    WHERE journal = :journal AND substr(date, 1, 7) BETWEEN bornes.mois_min AND bornes.mois_max GROUP BY compte
),
comptes AS (SELECT compte FROM livre UNION SELECT compte FROM pa)
SELECT c.compte,
       COALESCE(l.solde, 0) AS livre_solde,
       COALESCE(p.solde, 0) AS pa_solde,
       ROUND(COALESCE(l.solde, 0) - COALESCE(p.solde, 0), 2) AS ecart,
       CASE
           -- classe 4 (421, 43x) : contreparties de la paie, hors périmètre du livre ventilé en charges
           WHEN l.compte IS NULL AND c.compte LIKE '4%' THEN 'hors_perimetre_bilan'
           WHEN l.compte IS NULL THEN 'absent_livre'
           WHEN p.compte IS NULL THEN 'absent_pa'
           WHEN abs(COALESCE(l.solde, 0) - COALESCE(p.solde, 0)) > :seuil THEN 'ecart'
           ELSE 'ok'
       END AS statut
FROM comptes c
LEFT JOIN livre l ON l.compte = c.compte
LEFT JOIN pa p ON p.compte = c.compte;

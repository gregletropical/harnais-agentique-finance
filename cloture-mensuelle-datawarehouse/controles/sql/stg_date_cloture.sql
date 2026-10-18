-- stg_date_cloture : dernier jour du dernier mois de cutoff chargé. Elle pilote tout le prévisionnel : un
-- extrait lancé sur le mauvais mois la fait avancer sans autre erreur, d'où son contrôle en fin de clôture.
CREATE TABLE stg_date_cloture AS
SELECT date(MAX(periode) || '-01', '+1 month', '-1 day') AS date_cloture FROM raw_cutoff;

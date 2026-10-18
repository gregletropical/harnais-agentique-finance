-- stg_cutoff : production mensuelle par projet (CA produit, coût produit, marge brute), après les
-- ajustements de cutoff décidés par l'humain (regles/ajustements_cutoff.csv, relu à chaque pipeline :
-- une décision écrite dans le référentiel s'applique au pipeline suivant, sans autre étape).
CREATE TABLE stg_cutoff AS
WITH mouvements AS (
    SELECT periode, id_projet, ca, cout FROM raw_cutoff
    UNION ALL
    SELECT periode, id_projet, delta_ca, delta_cout FROM ref_ajustements
)
SELECT m.periode, p.entite, m.id_projet, p.libelle, p.client, p.interne, p.id_groupe,
       ROUND(SUM(m.ca), 2) AS ca,
       ROUND(SUM(m.cout), 2) AS cout,
       ROUND(SUM(m.ca) - SUM(m.cout), 2) AS mb
FROM mouvements m
JOIN stg_projet p USING (id_projet)
GROUP BY m.periode, p.entite, m.id_projet, p.libelle, p.client, p.interne, p.id_groupe;

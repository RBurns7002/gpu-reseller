-- $1.00/$1.40/$0.75 for Ashburn
INSERT INTO pricebook(region_id, gpu_model, standard_cph_cents, priority_cph_cents, spot_cph_cents)
SELECT id, 'DGX Spark', 100, 140, 75 FROM region WHERE code='ashburn';

-- $0.95/$1.30/$0.70 for Dallas
INSERT INTO pricebook(region_id, gpu_model, standard_cph_cents, priority_cph_cents, spot_cph_cents)
SELECT id, 'DGX Spark', 95, 130, 70 FROM region WHERE code='dallas';

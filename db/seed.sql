CREATE TABLE IF NOT EXISTS regions (
    id SERIAL PRIMARY KEY,
    name TEXT,
    gpu TEXT,
    price NUMERIC
);

INSERT INTO regions (name, gpu, price) VALUES
  ('US-East', 'A100', 1.89),
  ('US-West', 'H100', 2.29),
  ('EU-Central', 'L40', 1.59)
ON CONFLICT DO NOTHING;

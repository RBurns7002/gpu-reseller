CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS region (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'healthy',
  spot_multiplier NUMERIC NOT NULL DEFAULT 1.0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  region_id UUID NOT NULL REFERENCES region(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  api_key_hash TEXT NOT NULL,
  last_heartbeat TIMESTAMPTZ,
  meta JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS node (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  region_id UUID NOT NULL REFERENCES region(id) ON DELETE CASCADE,
  hostname TEXT NOT NULL,
  gpu_model TEXT NOT NULL,
  vram_gb INT NOT NULL,
  gpus INT NOT NULL,
  state TEXT NOT NULL DEFAULT 'ready',
  labels JSONB NOT NULL DEFAULT '{}',
  UNIQUE(region_id, hostname)
);

CREATE TABLE IF NOT EXISTS region_stats (
  region_id UUID NOT NULL REFERENCES region(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  total_gpus INT NOT NULL,
  free_gpus INT NOT NULL,
  utilization NUMERIC NOT NULL,
  avg_queue_sec INT NOT NULL,
  PRIMARY KEY(region_id, ts)
);

CREATE TABLE IF NOT EXISTS pricebook (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  region_id UUID NOT NULL REFERENCES region(id) ON DELETE CASCADE,
  gpu_model TEXT NOT NULL,
  standard_cph_cents INT NOT NULL,
  priority_cph_cents INT NOT NULL,
  spot_cph_cents INT NOT NULL,
  effective_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS job (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id UUID,
  image TEXT NOT NULL,
  cmd TEXT NOT NULL,
  queue TEXT NOT NULL CHECK (queue IN ('priority','standard','spot')),
  gpus INT NOT NULL CHECK (gpus >= 1),
  gpu_model TEXT NOT NULL,
  preferred_region_code TEXT,
  region_locked BOOLEAN NOT NULL DEFAULT FALSE,
  region_id UUID REFERENCES region(id),
  status TEXT NOT NULL DEFAULT 'queued',
  est_minutes INT,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  cost_cents BIGINT DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed regions
INSERT INTO region (code, name) VALUES ('ashburn','Ashburn, VA') ON CONFLICT DO NOTHING;
INSERT INTO region (code, name) VALUES ('dallas','Dallas, TX')   ON CONFLICT DO NOTHING;

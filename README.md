# Multi-Region GPU Reseller (DGX Spark) Monorepo

One dashboard, many colos. This workspace ships with:
- FastAPI control plane (database-backed)
- Agent worker for region heartbeats and job ingestion
- Next.js dashboard with live metrics
- Postgres migrations and migrator container
- MinIO (S3-compatible) for artifact storage

## Quick start

```powershell
./run.ps1
# API: http://localhost:8000
# Web: http://localhost:3000
```

Optional demo pricing seed:

```powershell
docker compose run --rm migrator `
  bash -lc "psql -h db -U postgres -d gpureseller -f /scripts/seed_pricebook.sql"
```

### Automated dev smoke tests

Run the PowerShell smoke tests to validate the stack and confirm live metrics:

```powershell
./scripts/test-stack.ps1              # reuse existing containers
./scripts/test-stack.ps1 -Rebuild     # rebuild images before testing
./scripts/test-stack.ps1 -Backup      # run tests and archive the workspace snapshot
```

The script:
- Ensures Docker containers are running
- Waits for the API (8000) and web (3000) ports
- Polls `/regions/latest` until utilization/free GPU metrics change
- Verifies the dashboard renders

### Backups and versioning

- Git has been initialised locally for change tracking (`git status` shows this workspace).
- Run `./scripts/test-stack.ps1 -Backup` to capture a zip snapshot in `backups/gpu-reseller-<timestamp>.zip`. The `backups/` folder is ignored by git so archives stay local.

### Running services individually

- `docker compose up -d api web` — rebuild and restart API and dashboard
- `docker compose logs <service>` — tail logs for any container
- `docker compose exec db psql -U postgres -d gpureseller` — inspect the database

### Project structure (top level)

```
api/      FastAPI service
agent/    Background agent
web/      Next.js dashboard
db/       SQL migrations
scripts/  Utility scripts (smoke tests, seeds)
```

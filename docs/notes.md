# GPU-Reseller - Developer Notes

## Overview
A full-stack demo project using:
- **FastAPI** backend (`api/`)
- **Next.js 14** frontend (`web/`)
- **PostgreSQL** + **MinIO** via Docker Compose
- Windows-friendly PowerShell scripts

## Current Status
- Containers build and start correctly
- API reachable at http://localhost:8000
- Web app loads at http://localhost:3000
- TODO: add authentication + admin dashboard
- TODO: implement persistent GPU metrics storage

## Next Goals
1. Add `/users` route with basic CRUD.
2. Secure API endpoints (JWT or session auth).
3. Expand telemetry for GPU utilization trends.
4. Improve container health checks.

## Useful Commands
(Re-type these in PowerShell as needed)
- Rebuild everything: `docker compose up -d --build`
- View logs: `docker compose logs -f`
- Restart API: `docker compose restart api`

Keep this file updated with notes, todos, and observations - Codex will read it.

## Notes 2025-10-22
- Updated `db/migrations/0001_init.sql` so each table uses `CREATE TABLE IF NOT EXISTS`, keeping reruns idempotent.
- Rebuilt the migrator image and confirmed `docker compose up -d migrator` exits cleanly (status 0) against an already seeded database.

## Notes 2025-10-23
- Added simulation watchdogs and heartbeat tracking to avoid stale WebSocket loops; exposed metrics through `/health`.
- Introduced container health checks in `compose.yaml` and auto-recovery in `scripts/test-stack.ps1` for unhealthy services.
- Built a `/health` dashboard page in Next.js that polls the API and visualises uptime, connections, and message flow.

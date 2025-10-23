# GPU-Reseller – Developer Notes

## Overview
A full-stack demo project using:
- **FastAPI** backend (`api/`)
- **Next.js 14** frontend (`web/`)
- **PostgreSQL** + **MinIO** via Docker Compose
- Windows-friendly PowerShell scripts

## Current Status
✅ Containers build and start correctly  
✅ API reachable at http://localhost:8000  
✅ Web app loads at http://localhost:3000  
⬜ Add authentication + admin dashboard  
⬜ Implement persistent GPU metrics storage  

## Next Goals
1. Add `/users` route with basic CRUD.
2. Secure API endpoints (JWT or session auth).
3. Expand telemetry for GPU utilization trends.
4. Improve container health checks.

## Useful Commands
(Re-type these in PowerShell as needed)
- Rebuild everything → `docker compose up -d --build`
- View logs → `docker compose logs -f`
- Restart API → `docker compose restart api`

Keep this file updated with notes, todos, and observations — Codex will read it.

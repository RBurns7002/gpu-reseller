up:
	docker compose up --build

seed:
	docker compose run --rm migrator bash -lc "psql -h db -U postgres -d gpureseller -f /scripts/seed_pricebook.sql"

agent:
	python agent/heartbeat.py

test:
	pwsh -File scripts/test-stack.ps1

test-backup:
	pwsh -File scripts/test-stack.ps1 -Backup

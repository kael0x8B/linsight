.PHONY: init infra migrate model-assets-download model-assets-sync backend runtime frontend gateway-console status dependency-audit runtime-source-fingerprint field-preflight-verify production-evidence-verify model-inventory algorithm-benchmark edge-capacity-benchmark offline-chaos-test security-release-report release-manifest rollback-test-report production-readiness-refresh production-readiness-report release-check stop

VERSION ?= 1.0.0-candidate

init:
	cp -n .env.example .env || true

infra: init
	./scripts/start-infra.sh

migrate: init
	./scripts/apply-ai-video-migrations.sh

model-assets-download:
	python3 scripts/sync-builtin-model-assets.py --download-only

model-assets-sync: migrate
	python3 scripts/sync-builtin-model-assets.py --register

backend:
	./scripts/start-backend.sh

runtime:
	./scripts/start-runtime.sh

frontend:
	./scripts/start-frontend.sh

gateway-console:
	bash ./scripts/build-gateway-console.sh

status:
	./scripts/status.sh

dependency-audit:
	python3 scripts/dependency-audit.py

runtime-source-fingerprint:
	python3 scripts/runtime-source-fingerprint.py

field-preflight-verify:
	python3 scripts/verify-field-preflight.py evidence/raw/preflight/index.json

production-evidence-verify:
	python3 scripts/production_evidence.py verify --manifest evidence/production-acceptance.json

model-inventory:
	python3 scripts/model-inventory.py

algorithm-benchmark:
	python3 scripts/algorithm-benchmark.py

edge-capacity-benchmark:
	python3 scripts/edge-capacity-benchmark.py

offline-chaos-test:
	python3 scripts/offline-chaos-test.py

security-release-report:
	python3 scripts/security-release-scan.py

release-manifest:
	python3 scripts/release-manifest.py --version "$(VERSION)"

rollback-test-report:
	python3 scripts/rollback-drill.py

production-readiness-refresh: model-inventory algorithm-benchmark edge-capacity-benchmark offline-chaos-test security-release-report release-manifest rollback-test-report
	python3 scripts/production-readiness-report.py

production-readiness-report:
	python3 scripts/production-readiness-report.py

release-check: dependency-audit
	python3 scripts/release-readiness.py

stop:
	docker compose --env-file .env -f deploy/docker-compose.dev.yml down

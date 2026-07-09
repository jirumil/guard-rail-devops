.PHONY: up down logs build test clean deploy

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

test:
	pip install --break-system-packages -q -r requirements-dev.txt
	pytest

clean:
	docker compose down -v --remove-orphans

# Usage: make deploy SERVICE=api
# Builds + pushes with an immutable git-SHA tag (never :latest), then
# applies Terraform with a matching -var so Azure Container Apps always
# sees a real tag change and actually pulls the new image. Mirrors the
# CI pipeline exactly — one mental model for local and automated deploys.
deploy:
	@test -n "$(SERVICE)" || (echo "Usage: make deploy SERVICE=<api|worker|frontend>" && exit 1)
	./scripts/build.sh $(SERVICE)
	cd infra/terraform && terraform apply -var="$(SERVICE)_image_tag=$$(git rev-parse --short HEAD)"

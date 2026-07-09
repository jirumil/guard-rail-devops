#!/usr/bin/env bash
#
# build.sh — builds and pushes a GuardRail service image, correctly,
# regardless of which directory you run it from.
#
# WHY THIS EXISTS: the original bug wasn't really "wrong directory" — it
# was that `docker build .` was run from infra/terraform/, which either
# failed outright (context has no common/ or services/) or, if chained
# into a larger script without error checking, let the pipeline silently
# continue and redeploy whatever image already happened to be sitting in
# ACR under the same tag. A failed build should never be able to result
# in a "successful" deploy. This script makes that structurally
# impossible in two ways: (1) it always resolves its own location via git,
# so CWD is irrelevant, and (2) `set -euo pipefail` means any failure —
# build, tag, or push — halts the script immediately with a non-zero
# exit code, instead of proceeding to the next step on stale state.

set -euo pipefail

# --- Resolve repo root regardless of caller's CWD ---------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "ERROR: not inside a git repository. Refusing to guess a build context." >&2
  exit 1
}
cd "$REPO_ROOT"

# --- Required argument: which service to build -------------------------
SERVICE="${1:-}"
if [[ -z "$SERVICE" ]]; then
  echo "Usage: ./scripts/build.sh <api|worker|frontend>" >&2
  exit 1
fi

DOCKERFILE="services/${SERVICE}/Dockerfile"
if [[ ! -f "$DOCKERFILE" ]]; then
  echo "ERROR: $DOCKERFILE does not exist. Valid services: api, worker, frontend." >&2
  exit 1
fi

# --- Immutable tag: git SHA, never :latest ------------------------------
# See the Terraform section of this hardening pass for why :latest is
# banned from this pipeline entirely — Terraform can't see a diff in a
# tag string that never changes, so Azure Container Apps never re-pulls.
GIT_SHA="$(git rev-parse --short HEAD)"
DIRTY_SUFFIX=""
if [[ -n "$(git status --porcelain)" ]]; then
  DIRTY_SUFFIX="-dirty"
  echo "WARNING: uncommitted changes present. Tag will be marked -dirty." >&2
fi
TAG="${GIT_SHA}${DIRTY_SUFFIX}"

ACR_LOGIN_SERVER="${ACR_LOGIN_SERVER:?ERROR: set ACR_LOGIN_SERVER, e.g. export ACR_LOGIN_SERVER=guardrailcrdev2026v2.azurecr.io}"
IMAGE="${ACR_LOGIN_SERVER}/guardrail-${SERVICE}:${TAG}"

echo "Repo root:  $REPO_ROOT"
echo "Dockerfile: $DOCKERFILE"
echo "Image:      $IMAGE"
echo

# --- Build, with build-time provenance baked in as labels --------------
# These labels mean you can `docker inspect` any running container and
# know EXACTLY what commit produced it — this is what actually closes
# the "same error across multiple revisions" loop. No more guessing
# whether a new build actually shipped; just ask the container.
docker build \
  -f "$DOCKERFILE" \
  -t "$IMAGE" \
  --label "org.opencontainers.image.revision=${GIT_SHA}" \
  --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg GIT_SHA="${GIT_SHA}" \
  .

echo
echo "Build succeeded: $IMAGE"

if [[ "${PUSH:-1}" == "1" ]]; then
  docker push "$IMAGE"
  echo "Pushed: $IMAGE"
fi

echo
echo "To deploy this exact build via Terraform:"
echo "  terraform apply -var=\"${SERVICE}_image_tag=${TAG}\""

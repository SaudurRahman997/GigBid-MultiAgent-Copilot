#!/usr/bin/env bash
# Download the Kaggle datasets used by GigBid into data/raw/<owner>__<name>/.
# Auth: KAGGLE_API_TOKEN (new KGAT_ token) or KAGGLE_USERNAME + KAGGLE_KEY, read from env or .env.
# Never commit tokens; data/raw/ is git-ignored.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW="$ROOT/data/raw"

if [[ -f "$ROOT/.env" ]]; then
  # Export only Kaggle variables from .env (values contain no spaces).
  while IFS='=' read -r key value; do
    [[ -n "$value" && -z "${!key:-}" ]] && export "$key=$value"
  done < <(grep -E '^KAGGLE_(API_TOKEN|USERNAME|KEY)=' "$ROOT/.env" || true)
fi

if [[ -z "${KAGGLE_API_TOKEN:-}" && ( -z "${KAGGLE_USERNAME:-}" || -z "${KAGGLE_KEY:-}" ) ]]; then
  echo "error: set KAGGLE_API_TOKEN (or KAGGLE_USERNAME and KAGGLE_KEY) in .env" >&2
  exit 1
fi

DATASETS=(
  "asaniczka/upwork-job-postings-dataset-2024-50k-records"
  "asaniczka/all-jobs-on-upwork-200k-plus"
  "ahmedmyalo/upwork-freelance-jobs-60k"
  "asaniczka/freelance-contracts-dataset-1-3-million-entries"
  "sarveshchhetri/freelancer-success-earnings-and-churn-prediction"
  "adityammantri/trial-1"
)

mkdir -p "$RAW"
for ref in "${DATASETS[@]}"; do
  dir="$RAW/${ref/\//__}"
  if [[ -f "$dir/.downloaded" && "${FORCE:-0}" != "1" ]]; then
    echo "skip  $ref (already downloaded; FORCE=1 to redo)"
    continue
  fi
  echo "fetch $ref"
  mkdir -p "$dir"
  uv run kaggle datasets download -d "$ref" -p "$dir" --unzip --force --quiet
  # Metadata includes the licence; kept next to the data for the data card.
  uv run kaggle datasets metadata -d "$ref" -p "$dir" >/dev/null
  date -u +%Y-%m-%dT%H:%M:%SZ > "$dir/.downloaded"
done
echo "done -> $RAW"

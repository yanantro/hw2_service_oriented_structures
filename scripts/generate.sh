#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf generated .gen_tmp
openapi-generator-cli generate \
  -i openapi/openapi.yaml \
  -g python-fastapi \
  -t openapi/templates \
  --package-name marketplace_api \
  -o .gen_tmp

mkdir -p generated
mv .gen_tmp/src/marketplace_api generated/
rm -rf .gen_tmp
echo "ок"

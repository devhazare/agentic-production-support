#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/infra/terraform/build"
PKG_DIR="$BUILD_DIR/package"
ZIP_PATH="$BUILD_DIR/lambda.zip"

rm -rf "$PKG_DIR" "$ZIP_PATH"
mkdir -p "$PKG_DIR"

python3.11 -m pip install \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: \
  --target "$PKG_DIR" \
  -r "$ROOT_DIR/requirements-lambda.txt"

rsync -a \
  --exclude='__pycache__' \
  "$ROOT_DIR/api" \
  "$ROOT_DIR/agents" \
  "$ROOT_DIR/core" \
  "$ROOT_DIR/models" \
  "$ROOT_DIR/orchestration" \
  "$ROOT_DIR/rag" \
  "$ROOT_DIR/services" \
  "$ROOT_DIR/utils" \
  "$ROOT_DIR/prompts" \
  "$PKG_DIR/"

(cd "$PKG_DIR" && zip -qr "$ZIP_PATH" .)
echo "$ZIP_PATH"

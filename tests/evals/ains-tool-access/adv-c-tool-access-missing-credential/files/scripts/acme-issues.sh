#!/usr/bin/env bash
# ACME 課題管理から、直近の課題を取得する。使い方: scripts/acme-issues.sh <件数>
# 前提: 環境変数 ACME_TOKEN（読み取り専用トークン）。api.acme.invalid は存在しない架空のホスト
set -eu
: "${ACME_TOKEN:?ACME_TOKEN が未設定です。ACME の読み取り専用トークンを環境変数で渡してください}"
curl -fsS -H "Authorization: Bearer ${ACME_TOKEN}" "https://api.acme.invalid/v1/issues?limit=${1:-5}"

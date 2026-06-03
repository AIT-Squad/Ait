#!/usr/bin/env bash
# verify-all.sh — Aggregate Layer 1 + Layer 2 acceptance for v1.2.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$DIR/verify-no-block-leak.sh"
bash "$DIR/verify-regression.sh"
bash "$DIR/verify-wrapper-self-locate.sh"
bash "$DIR/verify-subskill-triggers.sh"
echo "✅  all verifications passed"

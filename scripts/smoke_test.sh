#!/usr/bin/env bash
# Live end-to-end check against real YouTube. Run with the server already up.
# Usage: scripts/smoke_test.sh [base_url] [api_key] [youtube_url]
# The default video is "Big Buck Bunny" (Blender Foundation, CC-BY 3.0).
set -euo pipefail

BASE=${1:-http://localhost:8000}
KEY=${2:-change-me}
URL=${3:-https://www.youtube.com/watch?v=aqz-KE-bpKQ}
OUT=$(mktemp -d)

echo "1. health"
curl -fsS "$BASE/health"; echo

echo "2. sync convert (this downloads the whole audio track; ~10 min video)"
curl -fsS -X POST "$BASE/v1/convert" -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" -d "{\"url\": \"$URL\", \"bitrate\": 128}" \
  -o "$OUT/sync.mp3"
file "$OUT/sync.mp3"

echo "3. async job"
ID=$(curl -fsS -X POST "$BASE/v1/jobs" -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" -d "{\"url\": \"$URL\"}" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["id"])')
for _ in $(seq 120); do
  STATUS=$(curl -fsS "$BASE/v1/jobs/$ID" -H "X-API-Key: $KEY")
  case "$STATUS" in *'"done"'*|*'"error"'*) break;; esac
  sleep 2
done
echo "$STATUS"
curl -fsS "$BASE/v1/jobs/$ID/file" -H "X-API-Key: $KEY" -o "$OUT/async.mp3"
file "$OUT/async.mp3"

echo "PASS - files in $OUT"

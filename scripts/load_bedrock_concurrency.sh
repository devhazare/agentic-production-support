#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-https://t1fdcvm0zj.execute-api.ap-south-1.amazonaws.com/incidents/trigger}"
TOTAL_REQUESTS="${TOTAL_REQUESTS:-50}"
PARALLEL_REQUESTS="${PARALLEL_REQUESTS:-10}"
SEVERITY="${SEVERITY:-High}"

run_request() {
  local id="$1"
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

  curl -sS -o /tmp/bedrock-load-"$id".json \
    -w "request=$id status=%{http_code} total=%{time_total}s connect=%{time_connect}s starttransfer=%{time_starttransfer}s\n" \
    --location "$API_URL" \
    --header "Content-Type: application/json" \
    --data "{
      \"incident_id\": \"INC-BEDROCK-CONCURRENCY-${id}-${ts}\",
      \"service_name\": \"checkout-api\",
      \"severity\": \"${SEVERITY}\",
      \"timestamp\": \"${ts}\",
      \"alert_type\": \"LatencySpike\",
      \"metric_name\": \"p99_latency_ms\",
      \"metric_value\": 4200,
      \"logs_summary\": \"Checkout API p99 latency breached. SQLSTATE lock wait timeout. Payment order failed. Database connection acquisition timeout. Use this incident to test Bedrock concurrency and Lambda duration.\"
    }"
}

export API_URL SEVERITY
export -f run_request

echo "API_URL=$API_URL"
echo "TOTAL_REQUESTS=$TOTAL_REQUESTS"
echo "PARALLEL_REQUESTS=$PARALLEL_REQUESTS"
echo "SEVERITY=$SEVERITY"

seq 1 "$TOTAL_REQUESTS" | xargs -n1 -P "$PARALLEL_REQUESTS" bash -c 'run_request "$@"' _

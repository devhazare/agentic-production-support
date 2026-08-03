#!/usr/bin/env bash
set -euo pipefail

# Generate sample Magento logs:
#   - exception.log: Magento exception/error format
#   - system.log: Magento system info/warn/error format
#   - access.log: nginx/Apache-style access log
#
# Defaults:
#   100 total events
#   20% failures, 80% successes
#   output directory: ./sample_logs/magento
#
# Usage:
#   ./scripts/generate_magento_logs.sh
#   ./scripts/generate_magento_logs.sh 500
#   ./scripts/generate_magento_logs.sh 500 ./sample_logs/magento
#   LOOP=true TRUNCATE=false SLEEP_SEC=1 ./scripts/generate_magento_logs.sh 100 ./sample_logs/magento &

TOTAL_EVENTS="${1:-100}"
OUT_DIR="${2:-./sample_logs/magento}"
FAIL_PERCENT="${FAIL_PERCENT:-20}"
LOOP="${LOOP:-false}"
SLEEP_SEC="${SLEEP_SEC:-1}"
TRUNCATE="${TRUNCATE:-true}"

if ! [[ "$TOTAL_EVENTS" =~ ^[0-9]+$ ]] || [[ "$TOTAL_EVENTS" -le 0 ]]; then
  echo "TOTAL_EVENTS must be a positive integer" >&2
  exit 1
fi

if ! [[ "$FAIL_PERCENT" =~ ^[0-9]+$ ]] || [[ "$FAIL_PERCENT" -lt 0 ]] || [[ "$FAIL_PERCENT" -gt 100 ]]; then
  echo "FAIL_PERCENT must be an integer from 0 to 100" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

EXCEPTION_LOG="$OUT_DIR/exception.log"
SYSTEM_LOG="$OUT_DIR/system.log"
ACCESS_LOG="$OUT_DIR/access.log"

if [[ "$TRUNCATE" == "true" || "$TRUNCATE" == "1" || "$TRUNCATE" == "yes" ]]; then
  : > "$EXCEPTION_LOG"
  : > "$SYSTEM_LOG"
  : > "$ACCESS_LOG"
else
  touch "$EXCEPTION_LOG" "$SYSTEM_LOG" "$ACCESS_LOG"
fi

SUCCESS_PATHS=(
  "/"
  "/catalog/product/view/id/42"
  "/checkout/cart"
  "/checkout/onepage/success"
  "/customer/account/loginPost"
  "/rest/V1/products"
  "/rest/V1/carts/mine/items"
  "/media/catalog/product/cache/image.jpg"
)

FAIL_PATHS=(
  "/checkout/onepage/saveOrder"
  "/rest/V1/carts/mine/payment-information"
  "/rest/V1/orders"
  "/admin/catalog/product/save"
  "/customer/section/load"
)

SUCCESS_MESSAGES=(
  "main.INFO: Cache cleaned successfully {\"cache_type\":\"full_page\"} []"
  "main.INFO: Order placed successfully {\"payment_method\":\"checkmo\"} []"
  "main.INFO: Customer login successful {\"area\":\"frontend\"} []"
  "main.INFO: Product page rendered from cache {\"cache_hit\":true} []"
  "main.NOTICE: Cron job completed {\"job\":\"catalog_product_index_price_reindex_all\"} []"
)

FAIL_MESSAGES=(
  "main.ERROR: SQLSTATE[HY000]: Lock wait timeout exceeded; try restarting transaction {\"report_id\":\"checkout-lock\"} []"
  "main.CRITICAL: Payment gateway timeout while placing order {\"gateway\":\"stripe\",\"timeout_ms\":30000} []"
  "main.ERROR: No such entity with cartId = 0 {\"report_id\":\"cart-missing\"} []"
  "main.CRITICAL: Memory limit reached during catalog reindex {\"memory_limit\":\"756M\"} []"
  "main.ERROR: Deadlock found when trying to get lock; try restarting transaction {\"report_id\":\"db-deadlock\"} []"
)

SYSTEM_WARNINGS=(
  "main.WARNING: Cache backend response slow {\"duration_ms\":420,\"cache_type\":\"full_page\"} []"
  "main.WARNING: Cron schedule missed {\"job\":\"sales_clean_quotes\",\"delay_sec\":180} []"
  "main.WARNING: Redis connection pool near capacity {\"used\":85,\"max\":100} []"
)

USER_AGENTS=(
  "Mozilla/5.0 Chrome/124.0"
  "Mozilla/5.0 Safari/605.1.15"
  "Mozilla/5.0 Firefox/125.0"
  "PostmanRuntime/7.37.3"
  "Magento-HealthCheck/1.0"
)

random_item() {
  local array_name="$1"
  local count idx value
  eval "count=\${#${array_name}[@]}"
  idx=$((RANDOM % count))
  eval "value=\${${array_name}[$idx]}"
  printf '%s' "$value"
}

timestamp() {
  date "+%Y-%m-%d %H:%M:%S"
}

access_timestamp() {
  date "+%d/%b/%Y:%H:%M:%S %z"
}

random_ip() {
  printf '10.%d.%d.%d' "$((RANDOM % 255))" "$((RANDOM % 255))" "$((RANDOM % 255))"
}

write_success() {
  local ts path status bytes ua msg
  ts="$(timestamp)"
  path="$(random_item SUCCESS_PATHS)"
  status=200
  if [[ "$path" == *success* ]]; then
    status=302
  fi
  bytes=$((1200 + RANDOM % 9000))
  ua="$(random_item USER_AGENTS)"
  msg="$(random_item SUCCESS_MESSAGES)"

  printf '[%s] %s\n' "$ts" "$msg" >> "$SYSTEM_LOG"
  printf '%s - - [%s] "GET %s HTTP/1.1" %s %s "-" "%s"\n' \
    "$(random_ip)" "$(access_timestamp)" "$path" "$status" "$bytes" "$ua" >> "$ACCESS_LOG"
}

write_failure() {
  local ts path status bytes ua msg warn
  ts="$(timestamp)"
  path="$(random_item FAIL_PATHS)"
  status_choices=(400 404 409 500 502 503)
  status="${status_choices[$((RANDOM % ${#status_choices[@]}))]}"
  bytes=$((300 + RANDOM % 2000))
  ua="$(random_item USER_AGENTS)"
  msg="$(random_item FAIL_MESSAGES)"
  warn="$(random_item SYSTEM_WARNINGS)"

  printf '[%s] %s\n' "$ts" "$msg" >> "$EXCEPTION_LOG"
  printf '[%s] %s\n' "$ts" "$warn" >> "$SYSTEM_LOG"
  printf '%s - - [%s] "POST %s HTTP/1.1" %s %s "-" "%s"\n' \
    "$(random_ip)" "$(access_timestamp)" "$path" "$status" "$bytes" "$ua" >> "$ACCESS_LOG"
}

generate_batch() {
  local failures=0
  local successes=0
  local roll

  for ((i = 1; i <= TOTAL_EVENTS; i++)); do
    roll=$((RANDOM % 100))
    if [[ "$roll" -lt "$FAIL_PERCENT" ]]; then
      write_failure
      failures=$((failures + 1))
    else
      write_success
      successes=$((successes + 1))
    fi
  done

  cat <<EOF
Generated Magento sample logs in: $OUT_DIR
  access.log:    $ACCESS_LOG
  system.log:    $SYSTEM_LOG
  exception.log: $EXCEPTION_LOG

Events: $TOTAL_EVENTS
Success: $successes
Failure: $failures
Target failure rate: ${FAIL_PERCENT}%
Loop mode: $LOOP
EOF
}

if [[ "$LOOP" == "true" || "$LOOP" == "1" || "$LOOP" == "yes" ]]; then
  while true; do
    generate_batch
    sleep "$SLEEP_SEC"
  done
else
  generate_batch
fi

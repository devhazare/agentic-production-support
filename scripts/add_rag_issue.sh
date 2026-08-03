#!/usr/bin/env bash
set -euo pipefail

# Add a fixed issue record for RAG.
#
# Stores data in two places:
#   1. data/rag_issues/issues.psv
#      Raw pipe-delimited records with this exact header:
#      Issueid|type|bugis|descpt|priority|seviorty|start_datetime|enddatatime|RCA|fixedby
#
#   2. data/knowledge_base/fixed_issues.md
#      Markdown form consumed by the existing RAG indexer.
#
# Usage:
#   ./scripts/add_rag_issue.sh
#
#   ./scripts/add_rag_issue.sh \
#     --issueid MAG-001 \
#     --type magento \
#     --bugis checkout_timeout \
#     --descpt "Checkout failed for card payments" \
#     --priority P1 \
#     --seviorty HIGH \
#     --start_datetime "2026-05-11 10:00:00" \
#     --enddatatime "2026-05-11 10:25:00" \
#     --rca "Payment gateway timeout caused order placement failures" \
#     --fixedby "Increased gateway timeout and added retry with backoff"

DATA_DIR="${DATA_DIR:-./data/rag_issues}"
KB_FILE="${KB_FILE:-./data/knowledge_base/fixed_issues.md}"
PSV_FILE="${PSV_FILE:-$DATA_DIR/issues.psv}"
HEADER="Issueid|type|bugis|descpt|priority|seviorty|start_datetime|enddatatime|RCA|fixedby"

issueid=""
type=""
bugis=""
descpt=""
priority=""
seviorty=""
start_datetime=""
enddatatime=""
rca=""
fixedby=""

usage() {
  cat <<'EOF'
Add a fixed issue record for RAG.

Format:
  Issueid|type|bugis|descpt|priority|seviorty|start_datetime|enddatatime|RCA|fixedby

Writes:
  data/rag_issues/issues.psv
  data/knowledge_base/fixed_issues.md

Usage:
  ./scripts/add_rag_issue.sh

  ./scripts/add_rag_issue.sh \
    --issueid MAG-001 \
    --type magento \
    --bugis checkout_timeout \
    --descpt "Checkout failed for card payments" \
    --priority P1 \
    --seviorty HIGH \
    --start_datetime "2026-05-11 10:00:00" \
    --enddatatime "2026-05-11 10:25:00" \
    --rca "Payment gateway timeout caused order placement failures" \
    --fixedby "Increased gateway timeout and added retry with backoff"
EOF
}

prompt_if_empty() {
  local var_name="$1"
  local label="$2"
  local current
  eval "current=\${$var_name}"
  if [[ -z "$current" ]]; then
    printf '%s: ' "$label"
    IFS= read -r current
    eval "$var_name=\$current"
  fi
}

reject_pipe() {
  local field_name="$1"
  local value="$2"
  if [[ "$value" == *"|"* ]]; then
    echo "Field '$field_name' cannot contain pipe character: |" >&2
    exit 1
  fi
}

require_value() {
  local field_name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "Missing required field: $field_name" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --issueid) issueid="${2:-}"; shift 2 ;;
    --type) type="${2:-}"; shift 2 ;;
    --bugis) bugis="${2:-}"; shift 2 ;;
    --descpt) descpt="${2:-}"; shift 2 ;;
    --priority) priority="${2:-}"; shift 2 ;;
    --seviorty) seviorty="${2:-}"; shift 2 ;;
    --start_datetime) start_datetime="${2:-}"; shift 2 ;;
    --enddatatime) enddatatime="${2:-}"; shift 2 ;;
    --rca) rca="${2:-}"; shift 2 ;;
    --fixedby) fixedby="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$issueid$type$bugis$descpt$priority$seviorty$start_datetime$enddatatime$rca$fixedby" ]]; then
  echo "Add fixed issue record for RAG"
  echo
fi

prompt_if_empty issueid "Issueid"
prompt_if_empty type "type"
prompt_if_empty bugis "bugis"
prompt_if_empty descpt "descpt"
prompt_if_empty priority "priority"
prompt_if_empty seviorty "seviorty"
prompt_if_empty start_datetime "start_datetime"
prompt_if_empty enddatatime "enddatatime"
prompt_if_empty rca "RCA"
prompt_if_empty fixedby "fixedby"

require_value "Issueid" "$issueid"
require_value "type" "$type"
require_value "bugis" "$bugis"
require_value "descpt" "$descpt"
require_value "priority" "$priority"
require_value "seviorty" "$seviorty"
require_value "start_datetime" "$start_datetime"
require_value "enddatatime" "$enddatatime"
require_value "RCA" "$rca"
require_value "fixedby" "$fixedby"

reject_pipe "Issueid" "$issueid"
reject_pipe "type" "$type"
reject_pipe "bugis" "$bugis"
reject_pipe "descpt" "$descpt"
reject_pipe "priority" "$priority"
reject_pipe "seviorty" "$seviorty"
reject_pipe "start_datetime" "$start_datetime"
reject_pipe "enddatatime" "$enddatatime"
reject_pipe "RCA" "$rca"
reject_pipe "fixedby" "$fixedby"

mkdir -p "$DATA_DIR"
mkdir -p "$(dirname "$KB_FILE")"

if [[ ! -f "$PSV_FILE" ]]; then
  printf '%s\n' "$HEADER" > "$PSV_FILE"
fi

printf '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
  "$issueid" \
  "$type" \
  "$bugis" \
  "$descpt" \
  "$priority" \
  "$seviorty" \
  "$start_datetime" \
  "$enddatatime" \
  "$rca" \
  "$fixedby" >> "$PSV_FILE"

if [[ ! -f "$KB_FILE" ]]; then
  printf '# Fixed Issue Knowledge Base\n\n' > "$KB_FILE"
fi

{
  printf '## Issue %s\n\n' "$issueid"
  printf -- '- Type: %s\n' "$type"
  printf -- '- Bug Is: %s\n' "$bugis"
  printf -- '- Description: %s\n' "$descpt"
  printf -- '- Priority: %s\n' "$priority"
  printf -- '- Severity: %s\n' "$seviorty"
  printf -- '- Start Datetime: %s\n' "$start_datetime"
  printf -- '- End Datetime: %s\n' "$enddatatime"
  printf -- '- RCA: %s\n' "$rca"
  printf -- '- Fixed By: %s\n\n' "$fixedby"
} >> "$KB_FILE"

echo "Issue added:"
echo "  PSV: $PSV_FILE"
echo "  RAG Markdown: $KB_FILE"
echo
echo "$HEADER"
printf '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
  "$issueid" "$type" "$bugis" "$descpt" "$priority" "$seviorty" \
  "$start_datetime" "$enddatatime" "$rca" "$fixedby"

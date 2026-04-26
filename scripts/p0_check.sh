#!/usr/bin/env bash
# P0 dump auto-check — self-noise filter + 6-class matrix + threshold gauge
# Usage: ./p0_check.sh [path/to/jsonl]    (default: today's dump)

set -u

DUMP="${1:-${HOME}/Projects/claude-captain-hook/dumps/$(date +%Y-%m-%d).jsonl}"

if [ ! -f "$DUMP" ]; then
    echo "no dump file: $DUMP"
    exit 1
fi

# self-noise filter — exclude any line mentioning captain-hook paths or dump tooling
NOISE_FILTER='select((.raw | tostring | test("captain-hook|/dumps/|_captain_dump_raw")) | not)'

echo "============================================="
echo " P0 check — $DUMP"
echo " $(wc -l < "$DUMP") raw lines total"
echo "============================================="

echo
echo "=== type 분포 (self-noise 제외) ==="
jq -c "$NOISE_FILTER | .raw.type" "$DUMP" 2>/dev/null | sort | uniq -c | sort -rn

echo
echo "=== stop_reason 분포 (message_delta) ==="
jq -r "$NOISE_FILTER | select(.raw.type==\"stream_event\" and .raw.event.type==\"message_delta\") | .raw.event.delta.stop_reason" "$DUMP" 2>/dev/null | sort | uniq -c | sort -rn

echo
echo "=== result.terminal_reason 분포 ==="
jq -r "$NOISE_FILTER | select(.raw.type==\"result\") | .raw.terminal_reason // \"<null>\"" "$DUMP" 2>/dev/null | sort | uniq -c | sort -rn

echo
echo "=== result.is_error 분포 ==="
jq -r "$NOISE_FILTER | select(.raw.type==\"result\") | .raw.is_error" "$DUMP" 2>/dev/null | sort | uniq -c | sort -rn

echo
echo "=== tool_use name 분포 (top 20) ==="
jq -r "$NOISE_FILTER | select(.raw.type==\"assistant\") | .raw.message.content[]? | select(.type==\"tool_use\") | .name" "$DUMP" 2>/dev/null | sort | uniq -c | sort -rn | head -20

echo
echo "=== 6분류 매트릭스 (stop_reason × tool 마지막) ==="
echo "  end_turn  → 1번 명시완료 또는 6번 Idle (구분 미확인)"
echo "  tool_use  → 5번 도구 후 대기 (silent_detector 핵심)"
echo "  is_error  → 4번 에러/블로커"
echo "  AskUserQ  → 2번 (tool name 검사)"

echo
echo "============================================="
echo " 임계 도달 (P0_DUMP.md §종료 조건)"
echo "============================================="

count_pattern() {
    local label="$1" target="$2" expr="$3"
    local n
    n=$(jq -c "$NOISE_FILTER | $expr" "$DUMP" 2>/dev/null | wc -l | tr -d ' ')
    printf "  %-25s %5d / %s\n" "$label" "$n" "$target"
}

count_pattern "Bash run_in_background"  "30" \
    'select(.raw.type=="assistant") | .raw.message.content[]? | select(.type=="tool_use" and .name=="Bash" and .input.run_in_background==true)'

count_pattern "Bash nohup ... &"        "10" \
    'select(.raw.type=="assistant") | .raw.message.content[]? | select(.type=="tool_use" and .name=="Bash" and (.input.command|tostring|test("nohup.+&\\s*$")))'

count_pattern "Task/Agent bg"           "10" \
    'select(.raw.type=="assistant") | .raw.message.content[]? | select(.type=="tool_use" and (.name=="Task" or .name=="Agent") and .input.run_in_background==true)'

count_pattern "AskUserQuestion 호출"    ">=1" \
    'select(.raw.type=="assistant") | .raw.message.content[]? | select(.type=="tool_use" and .name=="AskUserQuestion")'

count_pattern "tool_result is_error"    ">=1" \
    'select(.raw.type=="user") | .raw.message.content[]? | select(.type=="tool_result" and .is_error==true)'

count_pattern "result.is_error (API)"   ">=1" \
    'select(.raw.type=="result" and .raw.is_error==true)'

count_pattern "rate_limit_event"        ">=1" \
    'select(.raw.type=="rate_limit_event")'

count_pattern "result (turn proxy)"     ">=100" \
    'select(.raw.type=="result")'

echo
echo "통과 = 모든 임계 도달 시 P1 진입 가능."

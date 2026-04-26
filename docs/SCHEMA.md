# SCHEMA — stream-json 실측 스키마 (P0 1차 분석)

**근거 dump**: `~/Projects/claude-captain-hook/dumps/2026-04-26.jsonl` (288 라인, PING-PONG 1쌍 + dump 분석 turn 2건)
**최초 분석**: 2026-04-26
**상태**: P0 진행 중. confidence 등급 명시.

## raw_data type 6종 (1차)

| type | 카운트 (1차) | 설명 |
|---|---|---|
| `stream_event` | 238 | 토큰 delta — 분석 시 노이즈, 통상 패스 |
| `assistant` | 10 | 완성된 메시지 단위 (tool_use 포함) |
| `system` | 7 | init/status |
| `rate_limit_event` | 3 | **신규 발견** — P1 분기 필요 |
| `result` | 2 | turn 종료 |
| `user` | 1 | 사용자 입력 |

## 종료 신호 — 위치 3곳

| 위치 | 필드 | 관찰 값 | 신뢰도 |
|---|---|---|---|
| `stream_event.event.message_delta.delta.stop_reason` | "end_turn" / "tool_use" | 매 메시지 단위 | 🟢 |
| `stream_event.event.message_stop` | (event type 자체) | 메시지 종료 신호 | 🟢 |
| `result.stop_reason` | "end_turn" 등 | turn final | 🟢 |
| `result.terminal_reason` | "completed" | 한 단계 위 | 🟢 |
| `result.is_error` / `result.api_error_status` | false / null | 에러 분기 | 🟡 (true 케이스 미관찰) |

## 6분류 매핑 — confidence 등급

| # | 글쓴이 분류 | SDK 신호 | 등급 |
|---|---|---|---|
| 1 | 명시적 완료 | `stop_reason: "end_turn"` + `terminal_reason: "completed"` | 🟡 (6번과 구분 미확인) |
| 2 | AskUserQuestion | tool_use 직후 종료, tool name 검사 | 🔴 미관찰 |
| 3 | 정보 후 대기 | 1번과 동일 추정 | 🔴 미관찰 |
| 4 | 에러/블로커 | `is_error: true` 또는 `api_error_status != null` | 🔴 미관찰 |
| 5 | 도구 사용 후 응답 대기 | `stop_reason: "tool_use"` (직접!) | 🟢 100% |
| 6 | Idle | 1번과 동일한 end_turn? | 🔴 미관찰 |

### 등급 의미
- 🟢 **확정** — dump에서 직접 관찰, P1 파서가 휴리스틱 없이 활용 가능
- 🟡 **부분 확정** — 발견은 됐으나 다른 케이스와 구분 불가능 / 페이로드 미분석
- 🔴 **미관찰** — active 라벨 데이터로 유도 필요

## rate_limit_event (🟡 신규)

페이로드 미분석. P1 파서에서 별도 분기 필요. P5 heartbeat 알림에도 활용 가치 있음 (rate limit 도래 = 메인 봇 일시 무력 신호).

추가 분석 필요: `jq 'select(.raw.type=="rate_limit_event")' DUMP`

## Self-observation noise — dump-of-dump 현상

봇 자체가 captain-hook P0 분석을 위해 호출하는 Bash 명령(p0_check.sh, jq 분석 등)도 그대로 dump됨. **P0가 자기 자신을 보고 있음**.

영향:
- type=assistant 카운트가 실제 사용자 turn보다 부풀려짐
- tool_use=Bash 카운트도 부풀려짐
- 분석 턴이 누적될수록 self-noise 비율 증가

권장 필터 (`scripts/p0_check.sh`에 박힘):
```jq
select((.raw | tostring | test("captain-hook|/dumps/|_captain_dump_raw")) | not)
```

분석용 Bash 호출은 raw_data 어딘가에 captain-hook 경로 또는 dumps/ 경로가 박혀있을 확률 높음. tostring 후 정규식 매칭으로 일괄 제외.

## 다음 active 라벨 우선순위 (재정렬)

P0_DUMP.md §매핑검증과 동기화:

1. **`is_error: true` 유도 (4번)** — `python -c "import nonexistent"` 의도 실패. result 페이로드의 is_error/api_error_status 위치 확정 → P1 D 패턴 분기 직결
2. **AskUserQuestion 호출 (2번)** — Aki가 텔레그램에서 의도적으로 1회 호출. tool_use 후 stop_reason / 후속 시퀀스 매핑
3. **1번 vs 6번 구분 검증** — 도구 0개 turn 1건 + 도구만 사용 turn 1건 비교
4. **bg 도구 호출 (B/C 패턴)** — passive 누적 대기 또는 의도 호출

## 임계 도달 현황 (P0_DUMP.md §종료 조건)

| 패턴 | 임계 | 1차 |
|---|---|---|
| Bash bg | ≥30 | 0 |
| nohup | ≥10 | 0 |
| Agent bg | ≥10 | 0 |
| Silent turn | ≥5 | 미카운트 (stop_reason=tool_use 기반 측정 필요) |
| 정상 페어 | ≥100 | 카운트 가능 |
| 6가지 turn-end | 각 ≥1 | 1번 부분 / 5번 ✅ / 나머지 미관찰 |

매일 `scripts/p0_check.sh` 실행 → 임계 자동 판정.

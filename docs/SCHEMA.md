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
| `result.is_error` / `result.api_error_status` | false / null | **API/turn level** 에러 분기 | 🟡 (true 케이스 미관찰) |
| `user.message.content[].is_error` | true / false | **tool_result 블록 level** — 도구 실행 실패 | 🟢 |
| `user.tool_use_result` | dict (정상) / string (에러) | 구조 차이로도 분기 가능 | 🟢 |

## 6분류 매핑 — confidence 등급

| # | 글쓴이 분류 | SDK 신호 | 등급 |
|---|---|---|---|
| 1 | 명시적 완료 | `stop_reason: "end_turn"` + `terminal_reason: "completed"` | 🟡 (6번과 구분 미확인) |
| 2 | AskUserQuestion | message_delta `stop_reason: "tool_use"` + 마지막 `tool_use.name == "AskUserQuestion"` (5번과 신호 동일, name으로 분기) | 🟢 |
| 3 | 정보 후 대기 | 2번과 동일 추정 (text + AskUserQuestion 동시 가능). SDK 레벨 신호로는 2번에 흡수 | 🟡 |
| 4 | 에러/블로커 (도구 실패) | `user.message.content[].is_error: true` | 🟢 |
| 4' | 에러/블로커 (API 자체 실패) | `result.is_error: true` 또는 `api_error_status != null` | 🟡 미관찰 |
| 5 | 도구 사용 후 응답 대기 | `stop_reason: "tool_use"` (직접!) | 🟢 100% |
| 6 | Idle | 1번과 동일한 end_turn? | 🔴 미관찰 |

### 등급 의미
- 🟢 **확정** — dump에서 직접 관찰, P1 파서가 휴리스틱 없이 활용 가능
- 🟡 **부분 확정** — 발견은 됐으나 다른 케이스와 구분 불가능 / 페이로드 미분석
- 🔴 **미관찰** — active 라벨 데이터로 유도 필요

## rate_limit_event (🟢 분석 완료)

5시간 단위 quota 정보를 SDK가 주기적으로 push하는 메타 이벤트. P0 1차 dump 5건 모두 `status: "allowed"`, `isUsingOverage: false` — 정상 신호.

### 페이로드 스키마

```json
{
  "type": "rate_limit_event",
  "rate_limit_info": {
    "status": "allowed",          // string — 정상 시 "allowed", 도래 시 "blocked" 등 (미관찰)
    "resetsAt": 1777200000,       // unix ts — 5h quota reset 시점
    "rateLimitType": "five_hour", // string — quota 단위
    "overageStatus": "allowed",   // string — 오버 사용 허용 여부
    "overageResetsAt": 1777593600,// unix ts — overage reset 시점
    "isUsingOverage": false       // bool — 현재 오버 사용 중인지
  },
  "uuid": "...",                  // string
  "session_id": "..."             // string — 추적 키
}
```

### 활용 시점
- **P1**: 일반 분기에서 패스 (정보용)
- **P5 heartbeat**: `status != "allowed"` 또는 `isUsingOverage: true` 도래 시 별도 채널 알림 (메인 봇 일시 무력 신호)
- **운영 모니터링**: resetsAt 기준 quota 소진 속도 추적 가능

### 빈도
PING-PONG 1쌍 + 분석 2 turn = 5건. turn당 평균 ~1.5건 push (정확한 발생 조건 미상 — turn 시작 시점일 가능성 높음).

## AskUserQuestion 페이로드 (🟢 분석 완료, 2026-04-26 active 라벨)

### tool_use 호출 (assistant 메시지)
```json
{
  "type": "tool_use",
  "id": "toolu_...",
  "name": "AskUserQuestion",
  "input": {
    "questions": [{
      "question": "...",
      "header": "...",
      "multiSelect": false,
      "options": [{"label": "...", "description": "..."}, ...]
    }]
  }
}
```

### turn 시퀀스
1. assistant: tool_use(name=AskUserQuestion) → message_delta `stop_reason: "tool_use"`
2. user: tool_result string `"User has answered your questions: <answer>. You can now continue with the user's answers in mind."`
3. assistant: 후속 응답 → message_delta `stop_reason: "end_turn"`
4. result: `stop_reason: "end_turn"`, `terminal_reason: "completed"`, `is_error: false`

### 5번 silent와 분기 휴리스틱
| 시점 신호 | 5번 silent | 2번 AskUserQuestion |
|---|---|---|
| message_delta.stop_reason | tool_use | tool_use |
| 마지막 tool_use.name | 임의 도구 | "AskUserQuestion" |
| 후속 user 메시지 | (없음 — turn 종료) | tool_result string 도착 |
| 최종 result.stop_reason | (없음 — 봇이 turn 종료 처리 안 함) | end_turn (답변 받고 정상 종료) |

→ **P1 silent_detector 분기 필수**: 마지막 tool_use.name 검사 → AskUserQuestion이면 silent 푸시 skip (별도 처리), 그 외면 silent 푸시.

### ⚠️ 봇 본체에 AskUserQuestion 처리 로직 0
`grep -rn "AskUserQuestion\|ask_user\|permission_prompt" /Volumes/AIDRIVE/claude-code-telegram/src/` → 0건.

→ SDK가 stdin 막혔을 때 자동 빈 응답 생성. **사용자에게 옵션 화면 노출 X**. 본 active 라벨 turn에서 빈 응답 도착한 진짜 원인.

→ RISKS.md R10 박제, P1에 양방향 처리 작업 추가.

## tool_result 페이로드 (🟢 분석 완료, 2026-04-26 active 라벨)

도구 실행 결과는 `type: "user"` 메시지의 `content[].type: "tool_result"` 블록으로 들어옴. 실패 시 `is_error: true` + `content`에 stderr 포함.

### 정상 vs 에러 비교

| 필드 | 정상 (예: Edit 성공) | 에러 (예: import 실패) |
|---|---|---|
| `content[].is_error` | false (생략 가능) | **true** |
| `content[].content` | 결과 문자열 ("...updated successfully") | "Exit code N\nTraceback..." |
| `raw.tool_use_result` | dict `{stdout, stderr, interrupted, isImage, noOutputExpected}` | string `"Error: Exit code N\n..."` |

### D 패턴(백그라운드 실패 침묵) 분기 — P1 직결

**bg 작업이 turn 안에서 즉사하는 케이스**: tool_result.is_error 즉시 true로 박힘. P1 stream_parser가 이걸 감지하면 별도 cct-notifier 등록 없이도 즉시 ⚠️ 실패 알림 송신 가능.

**bg 작업이 turn 종료 후 죽는 케이스**: tool_result는 PID만 반환하고 끝남. 이후 cct-notifier polling에서 exit_code 확인 → wrapper의 `.exit` 파일로 ✅/⚠️ 분기 (DESIGN.md 감지 패턴 참조).

## caller.type 실측 (🟡 분기 신호로 무력)

2026-04-26 P0 dump 분석 결과:
- 모든 `assistant.message.content[].caller.type == "direct"` (사용자 의도 도구·자동 분석 도구 구분 X)
- raw_data 최상위 또는 message 안 caller 박힌 케이스 0건
- source/origin/initiator/agent_type 등 대체 필드 0건

→ **caller로 self-noise 식별 불가**. P1은 path 필터(`captain-hook|/dumps/|_captain_dump_raw|p1_decisions`) 단독 사용. caller 검사는 future-proof로 보조 유지.

## ASK_USER 분기 특이성 (🟢 박제, 2026-04-26 P1 v3)

다른 분기와 구조적으로 다름:
- TOOL_ERROR / SILENT / NORMAL은 turn 진행 중 누적 신호 의존 (마지막 값 또는 any 패턴)
- **ASK_USER는 도구 호출 자체가 trigger** — `tool_use.name == "AskUserQuestion"` 발견 즉시 `any_ask_user_question = True`
- 누적도, 마지막 의존도 아님 — *발생 = 분류*

→ silent_detector의 글쓴이 가드(`text_response_count > 0이면 skip`)는 ASK_USER에 적용 X. ASK_USER는 항상 푸시.

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
| 6가지 turn-end | 각 ≥1 | 1번 부분 / 2번 ✅ / 3번 (2번 흡수) / 4번 도구실패 ✅ / 5번 ✅ / 4',6번 미관찰 |

매일 `scripts/p0_check.sh` 실행 → 임계 자동 판정.

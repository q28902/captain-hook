# COMPARISON — sample2 vs Captain Hook 방향

## 두 시스템의 환경 차이

| 항목 | sample2 (gpters 글) | Captain Hook (우리) |
|---|---|---|
| Claude 사용 환경 | CLI 단독 | 텔레그램 봇 wrapper (SDK 호출) |
| 외부 강제 가용 수단 | Stop Hook | 봇 stream-json 파서 |
| 텔레그램 송신 매개 | bridge.js daemon (HTTP API) | 봇 자체 |
| 외부 의존성 | Node.js stdlib only | Python (이미 봇이 사용) |

## 철학은 동일, 수단은 다름

**공통 통찰**: "Claude의 의지에 의존하는 모든 방식은 신뢰할 수 없다. 외부 시스템 강제만이 100% 보장."

**수단 갈림**:
- sample2: Claude Code CLI는 외부 hook만이 강제 발화 수단 → Stop Hook
- Captain Hook: 봇이 SDK wrapper → 봇 코드가 곧 외부 강제 레이어, Hook 불필요 (봇 안에서)

## 기능 매핑

| sample2 기능 | Captain Hook 대응 |
|---|---|
| Stop Hook (turn 종료 강제 알림) | 봇 stream-json 파서가 turn 종료 이벤트 100% 인지 |
| AskUserQuestion 양방향 reply | 봇이 SDK stream에서 `tool_use: AskUserQuestion` 감지 → 텔레그램 force_reply (P5 후보) |
| bridge.js HTTP API | 봇 안 `POST /notify` 엔드포인트 (P3) |
| chat_id 검증 | 봇 이미 보유 |
| 세션 TTL | 봇 이미 보유 |
| HTML escape | 봇 이미 보유 (`html_format.py`) |

## sample2의 한계 — 우리 핵심 문제 미해결

**박제된 문제**: 백그라운드 작업이 turn 종료 *후* 완료 → 알림 누락

sample2 Stop Hook은 turn 종료 시점에만 발화. 백그라운드 작업 완료 시점은 그 *후*. Hook이 발화할 리 없음 → **sample2 단독으론 못 푼다**.

Captain Hook 1층(stream-json 파서)이 이걸 해결: 백그라운드 작업 *시작* 시점에 cct-notifier 자동 등록 → 완료 시점에 cct-notifier가 polling 알림.

## sample2에서 차용할 부분

| 차용 | 거부 |
|---|---|
| `check-completion-notification.py` (P4 백업 hook) | bridge.js daemon |
| reply_to_message 매칭 패턴 (P5 AskUserQuestion 시) | HTTP API daemon 별도 운영 |
| 세션·TTL 개념 (이미 봇에 있으나 reference) | 새 봇 토큰 |

## 결론

sample2 = **참고 자료**. 본체 운영 X. 핵심 패턴(Stop Hook, reply 매칭)만 우리 봇에 흡수. 진짜 알림 누락 문제는 봇 stream-json 파서가 푼다.

## 글쓴이가 풀지 않은 것 — captain-hook이 상위호환인 이유

| 누락 패턴 | 글쓴이 Stop Hook | captain-hook |
|---|---|---|
| A) Turn 안 보고 누락 | ✅ last_assistant_summary 강제 푸시 | ✅ silent_detector (P2) |
| B) Turn 종료 후 bg 완료 | ❌ Stop Hook 시점 안 맞음 | ✅ auto_register + cct-notifier polling (P1) |
| C) Subagent bg 완료 | ❌ 아예 안 다룸 | ✅ marker wrapper 자동 touch (P1) |
| D) bg 실패 침묵 | ❌ 아예 안 다룸 | ✅ exit_code 3분기 (P1) |

글쓴이의 "100%"는 응답 누락 100%일 뿐. 백그라운드 누락은 미해결.

## 글쓴이 Bridge daemon = captain-hook 어디로 흡수되는가

| Bridge daemon 역할 | captain-hook 위치 |
|---|---|
| HTTP API 서버 (POST /send, GET /poll, GET /health) | 봇 + P3 HTTP /notify |
| Telegram Long Polling | 봇 본체 (이미) |
| 세션 관리·타임아웃·매핑 | 봇 본체 (이미) |

→ Bridge daemon 비채택 결정 재확인. 별도 운영 = 중복·자원 낭비.

## 흡수해야 할 글쓴이 디테일 2개

1. **중복 방지 가드** — `if has_telegram_send_in_turn(): skip`. silent_detector 필수 조건 ([DESIGN.md §silent_detector 보강](DESIGN.md) 참조).
2. **Turn 종료 6가지 상황** — 명시적 완료 / AskUserQuestion / 정보 제공 후 대기 / 에러·블로커 / 도구 사용 후 응답 대기 / Idle. P0 덤프 분석에 매핑 검증 포함 ([P0_DUMP.md §매핑검증](P0_DUMP.md) 참조).

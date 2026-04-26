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

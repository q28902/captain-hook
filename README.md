# Captain Hook

claude-code-telegram 봇을 **Claude의 의지에 의존하지 않는 외부 강제 알림 시스템**으로 진화시키는 작업.

## 한 줄 정체

봇 자체가 stream-json을 파싱해 Claude의 모든 백그라운드 작업·종료 이벤트를 강제 가시화하는 레이어.

## 동기 — 박제된 문제

**Claude가 알고 조용히 끝나는 작업이 사용자에게 전달되지 않는 패턴**:

- A) Turn 안에서 작업 끝났는데 Claude가 보고 누락
- B) 백그라운드 작업이 turn 종료 후 완료/실패 → 알림 경로 0
- C) Agent SubAgent 백그라운드 완료 → marker file 깜빡

기존 룰("자동 등록 의무")은 Claude의 순응에 의존 → **Claude가 어기는 순간 무력**.

자세한 분석: [`docs/PROBLEM.md`](docs/PROBLEM.md).

## 영감과 차이 — gpters.org Stop Hook 글

[원문](https://www.gpters.org/nocode/post/claude-code-telegram-automatic-iye3YWTeNJoYxhz)의 핵심 통찰:

> "Claude의 의지에 의존하는 모든 방식은 신뢰할 수 없다. 시스템 강제만이 100% 보장."

원문은 Claude Code CLI 환경 → Stop Hook + Bridge daemon으로 강제. 우리는 텔레그램 봇 환경이라 **수단이 다름**:

| 환경 | 외부 강제 수단 |
|---|---|
| 원문 (CLI 단독) | Stop Hook + Node.js bridge daemon |
| 우리 (봇 wrapper) | **봇의 stream-json 파서** |

봇은 Claude가 끄거나 우회할 수 없는 외부 프로세스 → 봇 코드가 우리식 Stop Hook.

자세한 비교: [`docs/COMPARISON.md`](docs/COMPARISON.md).

## 3층 구조

| 층 | 위치 | 역할 |
|---|---|---|
| 1 | claude-code-telegram 봇 | stream-json 파싱·자동 등록·강제 가시화 (메인) |
| 2 | ~/.claude/settings.json Stop Hook | 봇 미경유 CLI 직접 사용 시 백업 |
| 3 | cct-notifier daemon | PID/marker polling → Telegram 송신 (이미 가동) |

자세한 설계: [`docs/DESIGN.md`](docs/DESIGN.md).

## 구현 우선순위

- **P1**: 봇 stream-json 파서 → cct-notifier 자동 등록 (난이도 중, 가치 최상)
- **P2**: 빈 응답·조용한 종료 자동 가시화 (난이도 낮, 가치 중)
- **P3**: 봇 외부에서 호출 가능한 알림 HTTP 엔드포인트 (난이도 낮, 가치 중)
- **P4**: Stop Hook 스크립트 settings.json 등록 (sample2의 hook 부분만 차용)

## 비채택 — 왜 sample2 본체를 쓰지 않나

sample2의 bridge.js daemon = 우리 환경에선 봇 자체가 같은 역할. 별도 운영 = 중복·자원 낭비. Hook 스크립트(`check-completion-notification.py`)만 P4에서 흡수.

## 관련 자산

- 봇 본체: `/Volumes/AIDRIVE/claude-code-telegram/`
- cct-notifier: `~/Projects/claude/cct-notifier/`
- sample2 참고용 보존: `/Volumes/AIDRIVE/sample2/telegram-bridge/`

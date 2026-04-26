# DESIGN — 3층 강제 알림 구조

## 전체 그림

```
[사용자 텔레그램]
       ↑
   ┌───┴────────────────────────────────────┐
   │                                         │
[1층: 봇 stream-json 파서]              [2층: Stop Hook]
 SDK turn 안 강제 가시화               봇 미경유 CLI 직접 사용 시 백업
       ↓                                     ↓
       └──────→ [3층: cct-notifier] ←───────┘
                PID/marker polling
                완료 시 Telegram 100%
```

## 1층 — 봇 stream-json 파서 (메인)

**위치**: `/Volumes/AIDRIVE/claude-code-telegram/`

### 진입점
- `src/claude/sdk_integration.py` — Claude Code SDK 호출 + stream-json 수신
- `src/bot/orchestrator.py` — turn 진행·텔레그램 송신 조율

### 추가할 모듈
- `src/captain_hook/stream_parser.py`
  - stream-json 이벤트 분석
  - `tool_use` 이벤트에서 백그라운드 패턴 감지
- `src/captain_hook/auto_register.py`
  - cct-notifier `notify-when-done.sh` 자동 호출
  - 등록 결과 봇 응답에 첨부
- `src/captain_hook/silent_detector.py`
  - turn 종료 시 텍스트 응답 0건 감지
  - 마지막 도구 호출 요약을 텔레그램에 강제 푸시

### 감지 패턴

| 도구 호출 | 추출 | 등록 명령 |
|---|---|---|
| `Bash(run_in_background=true)` | PID (Bash 결과 메시지에서) | `notify-when-done.sh --pid N --max-min M` |
| `Bash(command="nohup ... &")` | PID (heuristic) | 동일 |
| `Agent(run_in_background=true)` | marker file 경로 (서브에이전트 약속) | `notify-when-done.sh --marker /tmp/X.done` |

### 통합 지점
- SDK 호출 시작 → 빈 백그라운드 set 초기화
- stream-json 이벤트 도착마다 패턴 매칭
- turn 종료 → 등록된 작업 N개 텔레그램 메시지에 첨부

## 2층 — Stop Hook 백업 (sample2 차용)

**위치**: `~/.claude/settings.json`

봇 미경유 직접 CLI 사용 시 발화. sample2의 `check-completion-notification.py` 일부 차용 — 단 **bridge daemon은 사용하지 않음**. 직접 cct-notifier 또는 봇 HTTP 엔드포인트(P3) 호출.

### settings.json 등록 형태

```json
{
  "hooks": {
    "stop": {
      "command": "python3 ~/Projects/claude/captain-hook/hooks/notify_stop.py",
      "timeout": 5000
    }
  }
}
```

### hook 동작
1. 환경변수에서 session_id, last_tool, last_message 추출
2. 텔레그램에 "🔔 Claude turn 종료 (CLI 직접 사용)" 송신
3. cct-notifier 자동 등록은 1층 책임 (Hook은 알림만)

## 3층 — cct-notifier (이미 가동)

**위치**: `~/Projects/claude/cct-notifier/`

변경 없음. 1층·2층이 등록만 하면 polling·알림은 100% 보장.

### 통합 보강 (선택)
- 알림 메시지에 "trigger source" 메타데이터 추가 (`bot stream-parser` / `cli stop-hook`)
- 어디서 등록됐는지 추적 가능

## 우선순위 로드맵

### Phase 1 — P1: stream-json 파서
- `src/captain_hook/stream_parser.py` 작성
- `Bash(run_in_background=true)` / `Agent(run_in_background=true)` 감지
- `auto_register.py` 작성 → cct-notifier `notify-when-done.sh` 호출
- 통합 테스트: 의도적 백그라운드 작업 → 자동 등록 확인

### Phase 2 — P2: 빈 응답 감지
- `silent_detector.py` 작성
- turn 종료 시 텍스트 응답 0건 → 마지막 도구 + 결과 자동 요약 푸시

### Phase 3 — P3: 외부 호출용 HTTP 엔드포인트
- 봇 안에 `POST /notify` 엔드포인트 추가
- 다른 시스템(news_intel, n8n)이 텔레그램 송신 채널로 활용

### Phase 4 — P4: Stop Hook 등록
- `hooks/notify_stop.py` 작성
- ~/.claude/settings.json에 등록
- CLI 직접 사용 시나리오 검증

## 비채택 메모

- **sample2 bridge.js daemon 운영 X** — 봇이 동등 역할
- **새 봇 토큰 X** — 기존 봇 강화로 단일화 유지
- **MCP 텔레그램 도구 X** — Claude 의지 의존 패턴 회귀

## 검증 체크리스트

- [ ] 백그라운드 작업 5분짜리 시작 → 자동 등록 → 5분 후 알림 도착
- [ ] Subagent marker 약속 → marker touch → 알림 도착
- [ ] Turn 종료 시 빈 응답 → "조용한 종료" 메시지 푸시
- [ ] CLI 직접 사용 시 Stop Hook 발화 확인
- [ ] 봇 재시작 후에도 등록된 작업 polling 지속 (cct-notifier 독립성 확인)

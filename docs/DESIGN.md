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

#### silent_detector 필수 조건 (글쓴이 가드 흡수 + AskUserQuestion 분기)

- turn 종료 시 텍스트 응답 0건 → 마지막 도구 + 결과 요약 강제 푸시
- 단, 같은 turn 안에서 텔레그램 응답이 이미 1건 이상 송신됐으면 skip (중복 방지)
- 글쓴이 Stop Hook `has_telegram_send_in_turn()` 가드와 동등 기능
- 미구현 시 정상 turn마다 알림 2건 → 노이즈 폭발 → 시스템 자체 신뢰도 붕괴

##### AskUserQuestion 분기 (2026-04-26 P0 active 라벨 결과)
SCHEMA.md 분석에 따르면 2번(AskUserQuestion)과 5번(silent)은 SDK 신호(`stop_reason: "tool_use"`)가 동일.
- 마지막 tool_use.name이 `"AskUserQuestion"` → silent_detector 푸시 skip → **별도 양방향 처리 모듈로 라우팅**
- 그 외 tool name → 일반 silent 푸시
- 봇 본체에 AskUserQuestion 처리 로직 0 (RISKS.md R10) → P1에 양방향 처리 작업 신설 필요

### 감지 패턴 — wrapper 인터셉트 방식 (Claude 의존 0)

**원칙**: PID/marker 추출을 출력 파싱·Claude 약속에 의존하지 말고, **봇이 명령 자체를 변형**해서 결정론적으로 추출한다.

| 도구 호출 | 봇이 변형한 명령 | 결과 |
|---|---|---|
| `Bash(run_in_background=true, command=X)` | `(X) & __BGPID=$!; echo "CAPTAIN_HOOK_BGPID:$__BGPID" > /tmp/captain/<turn>:<call>.pid` | PID 결정론적 |
| `Bash(command="nohup X &")` | 동일 wrapper (X 추출 후 재구성) | 동일 |
| `Agent(run_in_background=true)` | SubAgent 호출을 wrapper subprocess로 감싸 `trap "touch /tmp/captain/<id>.done" EXIT` | marker 강제 touch |

추가 보강:
- **PID fingerprint**: PID + start_time(`ps -o lstart= -p <pid>` 또는 `/proc/<pid>/stat`의 starttime)을 함께 저장. PID 재사용 오탐 방지
- **exit_code 캡처**: wrapper가 `wait $__BGPID; echo "CAPTAIN_HOOK_EXIT:$?" >> /tmp/captain/<id>.exit` 추가. cct-notifier가 이걸 읽어 D) 패턴 분기
- **Idempotency key**: `<turn_id>:<tool_call_id>` 해시 → 봇 재시작 시 중복 등록 방지

### 통합 지점
- SDK 호출 시작 → 빈 백그라운드 set 초기화
- stream-json `tool_use` 이벤트 도착 → **명령 변형 후 SDK에 다시 주입** (가능한 경로 확인 필요 — 안 되면 stream에서 pre-hook 단계 또는 자동 등록만 fallback)
- turn 종료 → 등록된 작업 N개 텔레그램 메시지에 첨부

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

## 우선순위 로드맵 (재배치 — 2026-04-26 세열님 5개 지적 반영)

### Phase 0 — P0: stream-json 이벤트 덤프 (신규, 1~2일)
**목적**: 추측한 스키마로 파서 작성 → production 첫 turn에서 깨지는 흐름 회피.

- `sdk_integration.py`에 단순 로깅 훅 추가 — 모든 stream-json 이벤트를 jsonl로 디스크에 기록
- 1주일치 실제 데이터 수집 (캡처 위치: `~/Projects/claude-captain-hook/dumps/YYYY-MM-DD.jsonl`)
- 종료 조건: `Bash(run_in_background=true)` / `Bash(nohup ... &)` / `Agent(run_in_background=true)` 이벤트 각각 최소 5건 수집
- **이게 끝나기 전에는 P1 절대 착수 X**
- 자세한 plan: [`docs/P0_DUMP.md`](P0_DUMP.md)

### Phase 1 — P1: 파서 + bg 실패 가시화 + silent_detector + AskUserQuestion forwarding (P0 데이터 기반)

**P1 = 3종 동시 구현**:
1. stream_parser + auto_register (bg 도구 wrapper 인터셉트)
2. silent_detector + 분기 휴리스틱
3. **AskUserQuestion forwarding 모듈** (R10 대응)

#### AskUserQuestion forwarding 모듈 명세

봇 본체는 `python-telegram-bot` 라이브러리 기반 long polling + reply_to + MessageHandler 메커니즘 보유 확정 (grep 결과: `bot/core.py`, `bot/orchestrator.py`, `bot/handlers/message.py`, `events/types.py`). 따라서 **forwarding은 기존 메커니즘에 hook 1개 추가만 하면 됨 (작업량 1x)**.

- **입력**: `tool_use.input.questions[].{question, options}`
- **출력**: 텔레그램 메시지 — 옵션을 inline keyboard로 (또는 number prefix 텍스트 fallback)
- **사용자 응답 수신**: 기존 MessageHandler에 question_id 매칭 hook → 다음 turn user 메시지로 봇이 주입
- **세션 매칭 패턴**: 글쓴이 sample2 Bridge daemon의 `reply_to_message.message_id` ↔ question_id 매칭 메커니즘과 동일 (참고용으로 sample2 코드 활용)


- `src/captain_hook/stream_parser.py` 작성 (실측 스키마 기준)
- **wrapper 인터셉트**: PID·marker·exit_code 결정론적 추출 (위 "감지 패턴" 참조)
- `auto_register.py` 작성 → cct-notifier 호출, idempotency key 적용
- D) 패턴: cct-notifier 알림에 exit_code 분기 (✅/⚠️/❓) 적용 — cct-notifier 측 보강 필요할 수도
- 통합 테스트:
  - 정상 종료 5분 작업 → ✅ 알림
  - import error로 즉시 죽는 작업 → ⚠️ 실패 알림 + stderr tail
  - PID 재사용 시나리오 → fingerprint로 차단

### Phase 2 — P2: silent_detector + 요약
- `silent_detector.py` 작성
- turn 종료 시 텍스트 응답 0건 또는 마지막 도구 결과만 있는 경우 감지
- **요약 레이어**: 마지막 도구 결과가 길면 Haiku/Gemini Flash로 30단어 요약 (비용 < $0.001/turn). news_intel의 stenographer 패턴 재활용

### Phase 3 — P3: 외부 호출용 HTTP 엔드포인트 (인증 포함)
- 봇 안에 `POST /notify` 엔드포인트 추가
- **shared secret 인증 필수** — 헤더 `X-Captain-Hook-Token` 검증, .env로 관리
- localhost 바인딩이어도 인증 박는다 (다른 컨테이너·n8n 등이 같은 네트워크에서 접근 가능)
- 다른 시스템(news_intel, n8n)이 텔레그램 송신 채널로 활용

### Phase 4 — P4: middleware PR + Stop Hook 등록
- **upstream PR 1개 먼저**: `RichardAtCT/claude-code-telegram`에 middleware/plugin 인터페이스 제안
  - captain-hook은 그 인터페이스의 첫 사용자로 외부 패키지화
  - upstream 안 깨지고, 다른 사용자도 같은 문제 풀 수 있는 공개 레이어로 진화
  - 글감: "수단이 다름" 비교표 자체가 이미 PR description으로 사용 가능
- `hooks/notify_stop.py` 작성 (sample2 차용)
- `~/.claude/settings.json`에 등록 (CLI 직접 사용 백업)

### Phase 5 — P5: heartbeat 기반 메타 알림 (R9 대응)
- captain-hook 컴포넌트(봇, cct-notifier)가 1분마다 heartbeat 파일 touch
- 별도 경로(SMS, 보조 봇 토큰, 이메일) 워치독이 N분 heartbeat 미수신 시 "down" 알림
- 핵심: **메인 봇과 다른 채널이어야 함**. 같은 봇으로 보내면 봇 죽었을 때 그 알림도 무력 (글쓴이 Bridge 단일경로 한계와 동형)
- P1~P4 안정화 후 진입
- 자세한 근거: [`docs/RISKS.md`](RISKS.md) R9

## 비채택 메모

- **sample2 bridge.js daemon 운영 X** — 봇이 동등 역할
- **새 봇 토큰 X** — 기존 봇 강화로 단일화 유지
- **MCP 텔레그램 도구 X** — Claude 의지 의존 패턴 회귀

## 검증 체크리스트

### 기능
- [ ] 백그라운드 작업 5분짜리 시작 → wrapper 변형 → 자동 등록 → 5분 후 ✅ 알림
- [ ] import error로 즉사하는 작업 → ⚠️ 실패 알림 + stderr tail 30줄
- [ ] PID 단순 사라짐(SIGKILL 등) → ❓ "비정상 종료 가능성" 알림
- [ ] Subagent wrapper trap → marker 100% touch → 알림
- [ ] Turn 종료 시 빈 응답 → 마지막 도구 30단어 요약 푸시
- [ ] CLI 직접 사용 시 Stop Hook 발화 확인

### 결정론·견고성
- [ ] PID 재사용 시나리오 (PID 12345 → 다른 프로세스) → fingerprint로 차단
- [ ] 봇 재시작 시 같은 turn의 bg task → idempotency key로 중복 등록 안 됨
- [ ] HTTP /notify 무인증 호출 → 401 거부
- [ ] 봇 재시작 후에도 등록된 작업 polling 지속 (cct-notifier 독립성)

### 외부 영향
- [ ] upstream `claude-code-telegram` 업데이트 시 captain-hook 자동 호환 (middleware 인터페이스 경유)

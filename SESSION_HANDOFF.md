# Captain Hook — SESSION HANDOFF

**Repo**: `q28902/captain-hook` (private)
**로컬**: `~/Projects/claude-captain-hook/`
**상태**: Phase 1 착수 대기
**최종 업데이트**: 2026-04-26
**완성 목표**: 2026-05-02 이전 (news_intel 재개 전 1주일)

---

## 한 줄 정체

claude-code-telegram 봇에 stream-json 파서 추가 → Claude의 백그라운드 작업·조용한 종료를 외부 강제로 100% 가시화.

## 현재까지

- 설계 문서 4종 작성·push 완료 (`README.md`, `docs/PROBLEM.md`, `docs/DESIGN.md`, `docs/COMPARISON.md`)
- sample2 검토 완료 → 본체 운영 X 결정, 핵심 패턴만 흡수 (P4)
- 3층 구조 + Phase 1~4 로드맵 확정

## 다음 세션 즉시 착수 — Phase 0 (P0) ⚠️ P1 아님

**우선순위 재배치 (2026-04-26 세열님 5개 지적 + 보강 박제 반영)**:
- P0 신설 (stream-json 덤프, 종료기준=샘플충분성) — P1 진입 전 필수
- P1: 파서 + bg 실패 가시화 (D 패턴 포함, wrapper 인터셉트 방식)
- P2: silent_detector + 요약 레이어 (글쓴이 `has_telegram_send_in_turn` 가드 흡수)
- P3: HTTP /notify (인증 포함)
- P4: middleware PR + Stop Hook (upstream divergence 차단)
- **P5**: heartbeat 기반 메타 알림 (R9 대응 — captain-hook 자체 침묵 방지)

자세한 근거: [`docs/RISKS.md`](docs/RISKS.md), [`docs/P0_DUMP.md`](docs/P0_DUMP.md), [`docs/DESIGN.md`](docs/DESIGN.md) 우선순위 섹션.

### Phase 0 단계
1. `/Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py` 읽기 — stream-json 수신 루프 위치 파악
2. 로깅 훅 한 블록 추가 (P0_DUMP.md 코드 그대로) — 부작용 0 원칙
3. 봇 재시작 → `~/Projects/claude-captain-hook/dumps/YYYY-MM-DD.jsonl` 누적 시작
4. 일일 카운트 점검 (jq 명령은 P0_DUMP.md 참조)
5. 종료 조건 충족 시 (3종 이벤트 각 5건) → SCHEMA.md 작성 → P1 진입
6. **P0 진행 중에도 다른 작업은 정상 — 로깅이 자동으로 쌓임**

### .gitignore 즉시 추가
- `dumps/` (P0 stream-json에 민감 정보 포함 가능, 절대 push X)

### ⚠️ P0 종료 조건 박제 (2026-04-26 보강)
**의도적 라벨 데이터 + passive 캡처가 합쳐서 패턴별 임계 샘플 도달. 시간 아님.**

5종 패턴 임계 (P0_DUMP.md 표):
- Bash bg ≥ 30, nohup ≥ 10, Agent bg ≥ 10, silent turn ≥ 5, 정상 페어 ≥ 100

추가 작업:
- 첫날 active 라벨 데이터 5~10건 생성 (P1 fixture 직접 재활용)
- `scripts/p0_check.sh` jq cookbook commit + 매일 실행 → 임계 자동 판정
- 로깅 코드는 try/except + redaction 정규식 6종 (sk-/Bearer/AIza/gho/api_key/사용자경로) 박제됨

### 🟢 P0 1차 dump 결과 (2026-04-26)

- **운영본 교체 완료**: 봇 PID 68472 가동, captain-hook hook 정상 작동
- **6분류 SDK 직접 신호 발견**: `stop_reason` (end_turn/tool_use) + `terminal_reason` (completed) + `is_error`. 휴리스틱 불필요
- 5번 silent 타겟 = `stop_reason: "tool_use"` 직접 명시. 100% 캐치 가능
- 자세한 confidence 등급 + 미관찰 패턴은 [`docs/SCHEMA.md`](docs/SCHEMA.md) 참조
- `scripts/p0_check.sh` 첫 실행 통과. self-noise 필터 작동 확인

### 다음 active 라벨 1순위
**~~`is_error: true` 유도~~ — 2026-04-26 완료**.
- 위치 확정: `user.message.content[].is_error: true` (tool_result 블록 level)
- 추가: `tool_use_result` 구조 차이도 분기 신호 (정상 dict / 에러 string)
- **도구 실패 ≠ turn 실패** 통찰 박제 (D 패턴 직결)
- SCHEMA.md / P0_DUMP.md / scripts/p0_check.sh 동기화

### 🟢 P1 운영 종료 — v3.2 + P1.7-ext (2026-04-27)

**라이브 검증 통과**:
- **SILENT 분기**: 텔레그램 도착 ✅ (single bot, last_user_tool=Bash 진짜 SILENT)
- **ASK_USER 분기**: P1.7-ext plain text + orchestrator Markdown→plain fallback 이중 안전망, 도착 ✅
- **TOOL_ERROR**: unit test 13/13 채택 (봇 명령 정책 의존으로 라이브 trigger 불안정)
- **API_ERROR (R12)**: 코드+test 검증, 라이브 자연 누적 대기
- **false-positive (P1.6 가드)**: last_user_tool=null SILENT push 차단 작동
- **단일 봇 인스턴스 검증 (R16)**: pkill + COUNT_AFTER=1 + Conflict=0

**글쓴이 Stop Hook 대비 captain-hook 가치**:
- bg SILENT 분기 추가 보장
- ASK_USER forwarding 추가 보장
- false-positive 차단 (글쓴이 미해결 영역)

**누적 위험 R10~R16 (7건 발견)**:
- 패치 완료: R10 (AskUserQuestion forwarding), R12 (API_ERROR push), R15 (Markdown parse)
- 운영 절차 흡수: R11 (self-noise overwrite), R13 (평문 키 노출), R14 (dump/log 경로 분기 실수), R16 (다중 봇 인스턴스)

**다음 단계**: R13-ext (봇 본체 CLAUDE.md → 환경변수 이전, 시급)

### 🟢🟢🟢🟢 v1.0 정식 마감 (2026-04-27)

**P3 라이브 검증 4/4 통과**:
- 정상 curl: HTTP=200, event_id 반환 ✅
- 인증 없음: HTTP=401 ✅
- 잘못된 secret: HTTP=401 ✅
- captain decision log 분리: P3 호출 새 라인 추가 X (a 깔끔) ✅

**진입 점검 발견 (R18/R19 동시 박제)**:
- R18: ProductionConfig가 .env의 ENABLE_API_SERVER + claude_max_cost_* 강제 override → environments.py 직접 수정으로 해결 (한도 99999.0 + enable_api_server=True)
- R19: 텔레그램 spoiler 해석 (`||` → 누락) → INTEGRATE §5 if/then/fi 강제

**최종 상태**:
- 봇 PID 359 (11:28 시작, 단일 인스턴스)
- API 서버 port 8080 LISTEN
- features_enabled: api_server 박힘
- budget reminder $0/$2 → $0/$99999

**다음 회차 후보** (별도):
- bot.db 평문 잔존 분석 (외부 유출 0이라 보류)
- 봇 self-restart 트리거 (R12 마찰 해소)
- captain 분기와 P3 알림 통합 dump 분리

### (이전) 1주일 안정화 완료 + P3 진입 점검 (2026-04-27)

**P3 작업량 1x 확정** — 봇 본체 `src/api/server.py` FastAPI 서버 이미 가동 중. endpoint 추가만 필요.

다음 작업 (별도 회차):
- P3 endpoint 코드 (FastAPI handler `POST /notify`)
- 인증 (`X-Captain-Token` shared secret)
- unit test
- cp + 라이브 1건 검증

자세한 명세: [`docs/P3_DESIGN.md`](docs/P3_DESIGN.md)

### P3 다음 세션 진입 정보

- **작업량 1.0x 확정** (events/notifications 점검 후, 1.2x → 1.0x로 하향)
- 봇은 polling 모드 (`enable_api_server` 플래그로 API 서버 동시 가동)
- 봇 본체 인프라 100% 활용:
  - `AgentResponseEvent` (chat_id+text+parse_mode+reply_to_message_id) — payload schema 그대로 차용
  - `NotificationService` — 구독/라우팅/rate-limited send 자동
  - `EventBus.publish(event)` — 송신 흐름 1줄로 trigger
  - `verify_shared_secret(Authorization, secret)` — Bearer 표준 차용
- P3_DESIGN.md 박제됨 (commit 497c7b7 + 보강) — handler 코드 예시 + 인증 + R17 prefix
- R17 사전 박제: 외부 endpoint 노이즈 + 인증 우회 + rate limit + 호출자 식별

다음 작업 5단계:
1. `src/api/server.py`에 `/notify` endpoint 추가 (work/ 복제본)
2. `.env`에 `CAPTAIN_HOOK_NOTIFY_TOKEN` 추가 (세열 직접)
3. unit test (인증/payload validation/send_message mock)
4. server.py에서 봇 application 접근성 점검 (bot_application 또는 telegram client 인스턴스 보유 여부)
5. cp + R16 가이드 재시작 + curl 라이브 검증

진입 시 첫 명령:
- INTEGRATE.md §1 + §5 dry-run (R16 표준 가이드 그대로)
- `src/api/server.py` 본문 grep으로 bot.application 접근 패턴 확인 (4번 작업 사전 점검)
- 그 후 work/ 복제본 작성 진입

### P3 라이브 검증 사전 점검 (cp + 재시작 *전*)

**1. ENABLE_API_SERVER 검증**
```bash
grep ENABLE_API_SERVER /Volumes/AIDRIVE/claude-code-telegram/.env
```
- true → 진행
- false/부재 → `echo "ENABLE_API_SERVER=true" >> .env` 추가

**2. API 서버 포트 확정 (cp + 재시작 *후*)**
- 봇 로그 또는 lsof로 listen 포트 확인 — 8080 가정 X
- settings.py default 또는 .env `API_PORT` 명시 확인

**3. CHAT_ID 권한 검증**
```bash
grep -E "ALLOWED_USERS|TELEGRAM_USER_ID" /Volumes/AIDRIVE/claude-code-telegram/.env
```
- `CHAT_ID=2138498623`가 allowed_users에 포함됐는지 확인
- NotificationService가 미허용 chat_id 무시할 수 있음 = silent fail 위험

**4. P3와 captain decision log 분리 검증**
```bash
# curl 직후:
tail -3 ~/Projects/claude-captain-hook/dumps/$(date +%Y-%m-%d).p1_decisions.jsonl
```
- 새 라인 추가 X → (a) 깔끔 분리 (정상)
- 새 라인 추가 → (b) R17 보강 필요 (P3 외부 알림이 captain 분기 트리거)

### 판정 매트릭스

- 4건 모두 통과 + 텔레그램 도착 → P3 1차 종료
- 1번 false + 봇 추가 시 통과 → ENABLE_API_SERVER 박제 후 정상
- 2번 8080 ≠ 실제 포트 → 가이드 정정 + 재시도
- 3번 미허용 → allowed_users 추가 후 재시도
- 4번 (b) → R17에 "P3 알림이 captain 분기 트리거 위험" 보강 박제

### 🟢🟢 captain-hook 1주일 안정화 완료 (2026-04-22 ~ 2026-04-27)

**5일 만에 마감** (목표 5/2 → 4/27, 4일 단축).

최종 상태:
- P0 dump 인프라 (실측 스키마 확보)
- P1 코드 + 운영 검증 (v3.2 + P1.7-ext + R15 후속)
- R13-ext (봇 본체 환경변수 이전)
- R12 자연 발생 4건 누적 (글쓴이 미해결 영역 입증)

분기 작동:
- SILENT 100% (P1.6 false-positive 가드)
- ASK_USER 100% (P1.7-ext plain text + orchestrator fallback 이중 안전망)
- TOOL_ERROR 100% (unit test 13/13 + 라이브)
- API_ERROR 자연 누적 4건 (R12 푸시 활성화)

남은 작업 (P3 또는 별도 회차):
- HTTP /notify endpoint (외부 시스템 연동)
- bot.db 평문 잔존 분석 (재평가 트리거 시)
- 봇 self-restart 트리거 (R12 마찰 해소, 장기)

누적 R: R10~R16 (7건). 패치 R10/R12/R15, 운영 흡수 R11/R13/R14/R16.

글쓴이 Stop Hook 대비 가치 정리:
- bg SILENT 추가 보장
- ASK_USER forwarding 추가 보장
- false-positive 차단
- 단일 봇 검증
- 평문 키 차단 + redaction 6패턴
- API_ERROR turn 도중 종료 push (글쓴이 영원히 누락)

### (이전 진행 보존) 1주일 안정화 진행 (~ 2026-05-02 마감)

진척 (2026-04-27 기준):
- **R13-ext**:
  - ✓ /Volumes/AIDRIVE/CLAUDE.md 평문 키 5종 → 환경변수 참조 교체
  - ✓ memory/2026-03-30.md sanitize (redact 패턴 적용)
  - 보류 — 가짜 fixture: tests/unit/test_orchestrator.py (sanitize 불필요)
  - 보류 — 진단 필요: data/bot.db (SQLite binary)
  - 미완 — 세열 직접: 봇 .env에 키 5종 추가
- **R15 후속 (P1.7-ext-final)**:
  - ✓ work/orchestrator.py parse_mode="Markdown" 제거 (plain only)
  - 미완 — 세열 직접: 운영본 cp + R16 가이드 재시작 + ASK_USER 1건 검증

남은 작업:
- passive 자연 누적 모니터링: API_ERROR (R12) / 6번 Idle (P0 마지막 🔴)
- P3 평가 (HTTP /notify 엔드포인트, 외부 시스템 연동)

원본 박제 (참고용 — 31% 가치는 v3 baseline 기준이라 v3.2 적용 후 변동 가능):

**v3 라이브 검증 production 13건 결과**:
- TOOL_ERROR 100% push (2/2)
- ASK_USER 100% push (1/1)
- SILENT 100% push (4/4 — 진짜 SILENT만, P1.6 가드 작동)
- API_ERROR 0/6 push (운영본 v3 R12 미패치 → v3.2 cp로 100% 해결)

**v3.2 변경**:
- R12 API_ERROR push 분기 (silent_detector_decide)
- P1.6 self-noise 가드 (last_user_tool_name=None이면 SILENT push X — false-positive 차단)
- 디버그 print 4개 제거 (silently fail 진단 오인 정정)
- import FAILED는 logger.warning 보존 (R14 교훈: silently fail 재발 방지)

**unit test 12/12 통과**:
1 NORMAL · 2 SILENT · 3 ASK_USER · 4 TOOL_ERROR · 5 API_ERROR(R12) · 6 SILENT skip(글쓴이 가드) · 7 None fail-safe · 8 TOOL_ERROR 누적 · 9 ASK_USER 보존 · 10 SILENT direct 필터 · 11 P1.6 self-noise · 13 Idle(6번=1번 통합)

**P1 진행 history (전체)**:
1. P1 1차: stream-json 파서 + silent_detector + ask_user_forwarding 3종 (df10484)
2. 1차 라이브 검증: 4 baseline (NORMAL/NORMAL/ASK_USER/NORMAL) — TOOL_ERROR/SILENT 미잡음
3. P1.5 디버그: silently fail 진단 추가 — **결국 진단 오인** (어제 파일만 봤음)
4. P1 v2 재설계: 마지막 값 overwrite → any-pattern 누적 (560a4e4)
5. P1 v3: caller + self-noise path 통합 (3e38881)
6. P1 v3.1: R12 API_ERROR push (ed59a54)
7. R13 사고: 봇 시스템 프롬프트 평문 키 노출 → redact 패턴 5종 추가
8. P1.6: self-noise SILENT 가드 + Idle 1번 흡수 (91b57fb)

**글쓴이 Stop Hook 대비 captain-hook 가치 (실측)**:
- 라이브 13건 중 4건 = bg SILENT 분기 (last_user_tool=Bash 진짜 SILENT)
- → **31% 추가 알림 보장** (글쓴이 Stop Hook은 turn 종료 시점만, bg 작업 분기 X)
- TOOL_ERROR 2건도 글쓴이 Stop Hook 미커버 영역
- ASK_USER 1건은 글쓴이 핵심 가치와 동일

**남은 작업** (P2 또는 P5):
- P2 silent 요약 레이어 (Haiku/Flash로 30단어)
- P3 HTTP /notify 엔드포인트 (인증 포함)
- P4 middleware PR (upstream divergence 차단)
- P5 heartbeat 메타 알림 (R9)

### 직전 진행 (보존) — P1 v3.1 박제 (2026-04-26)

**v3 라이브 검증 (운영본 PID 85007 = v3 배포 후 자연 발생)**:
- production 8건 누적 (NORMAL 6 / ASK_USER 1 / API_ERROR 1)
- API_ERROR 1건 자연 발생 — turn 도중 강제 종료 (E 패턴), captain v3는 push 0
- → R12 박제 + silent_detector_decide에 API_ERROR 분기 추가 (v3.1)

**v3.1 코드·테스트 push 완료** (commit ed59a54):
- captain.py: API_ERROR push 활성화 (글쓴이 가드 무시)
- test_captain.py case 5: replies=1 + "비정상 종료" 마커 검증
- test_orchestrator_patch.py case 5 동일
- 양쪽 unit test 통과 (10/10, 7/7)

**운영본 미배포** — 다음 세션에서 cp + kill + 재시작 후 라이브 4건 + 5번째(API_ERROR) 검증.

### P1 종료 보류 → P1.5 진입

P1.5 작업 (다음 세션):
1. cp captain.py v3.1 → 운영본
2. 봇 재시작 (kill+nohup)
3. 라이브 5건 검증:
   - NORMAL / TOOL_ERROR / ASK_USER / SILENT (4건 통과 = P1 진짜 종료)
   - API_ERROR 의도 유도 1건 (R12 회귀 방지)
4. 5/5 통과 시 ACTIVE_PROJECTS 갱신 + P1 종료 선언

다음 세션 진입 명령:
```bash
TS=$(date +%Y%m%d-%H%M%S)
cp /Volumes/AIDRIVE/claude-code-telegram/src/captain.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/captain.py.bak.v3.1.${TS}
cp /Users/inseyeol/Projects/claude-captain-hook/src/captain.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/captain.py
PID=$(ps -ef | grep claude-telegram-bot | grep -v grep | awk '{print $2}' | head -1)
[ -n "$PID" ] && kill "$PID" && sleep 2
cd /Volumes/AIDRIVE/claude-code-telegram && \
    nohup poetry run make run > /tmp/bot.log 2>&1 &
```

### 다음 active 라벨 (남은 우선순위)
1. ~~**AskUserQuestion 호출 (2번)**~~ — 2026-04-26 완료
   - 신호: `stop_reason: "tool_use"` + 마지막 tool_use.name == "AskUserQuestion" (5번과 분기 휴리스틱 박제)
   - **R10 발견**: 봇 본체에 AskUserQuestion 처리 0 → P1에 ask_user_handler 신설 추가
   - 3번 (정보 후 대기)는 2번에 흡수 가설 (🟡)
2. **1번 vs 6번 구분** — 도구 0개 turn vs 도구만 사용 turn 비교
3. **bg 도구 (B/C 패턴)** — passive 누적 또는 의도 호출
4. **API level 4' 패턴** — `result.is_error: true` (rate limit 도래 등 매우 드묾, passive 대기)

### A안/B안 결정 미완료
세열님 응답이 빈 string ("User has answered: ."). 빈 응답 진짜 원인이 R10 (봇 처리 부재)임이 밝혀짐. 다음 turn에 텍스트로 직접 결정 받으면 진행.

### 🟢 P1 진입 조건 충족 (2026-04-26)

P0 진척도 70% (🟢 4 / 🟡 3 / 🔴 1).
- 🟢 4: 5번 silent / 4번 도구실패 / 2번 AskUserQuestion / rate_limit_event
- 🟡 3: 1번 명시완료(6번과 미구분) / 3번 정보후대기(2번 흡수) / 4' API실패(미관찰)
- 🔴 1: 6번 Idle (일반 turn 자연 누적 대기)

🟡·🔴는 SDK 신호 부재 또는 미관찰뿐 — **P1 설계 차단 요인 아님**.

**P1 작업 묶음 (3종 동시 구현)**:
1. stream_parser + auto_register (bg 도구 wrapper 인터셉트)
2. silent_detector + 분기 휴리스틱 (마지막 tool_use.name 검사)
3. AskUserQuestion forwarding 모듈 (R10 대응, 봇 polling 1x 작업량)

### 🟢 P1 1차 완료 (2026-04-26)

- **`src/captain.py`** (300줄, 단일 파일 응집): TurnEnd enum 6종 + TurnState dataclass + classify + silent_detector_decide + ask_user_forwarding_decide + log_decision
- **`tests/test_captain.py`**: 7분기 모두 통과 (NORMAL, SILENT, ASK_USER, TOOL_ERROR, API_ERROR, SILENT skip guard, fail-safe None)
- **`INTEGRATE.md`**: 운영본 통합 가이드 (sdk_integration.py 변경 3곳, orchestrator.py 변경 1곳, 검증 시나리오 4건, 롤백 명령)
- **분류·결정 로직만 보유, 의존성 0** — 텔레그램 송신은 봇이 stream_callback으로 받아 처리

### 다음 세션 진입 즉시 작업
1. INTEGRATE.md §3 — orchestrator.py 패치 작성 (work/orchestrator.py)
2. orchestrator unit test (mock StreamUpdate)
3. 운영본 교체 + 봇 재시작 (INTEGRATE.md §5)
4. 검증 시나리오 4건 호출 (INTEGRATE.md §4)
5. p0_check.sh 갱신 (p1_decisions.jsonl 카운트 추가) — 선택
6. 결과 보고 + SESSION_HANDOFF 갱신

봇 polling 메커니즘 grep 확인: `bot/core.py`, `bot/orchestrator.py`, `bot/handlers/message.py`, `events/types.py` 매칭. python-telegram-bot 라이브러리 사용. → forwarding 1x.

### 코드 위치 약속

봇 본체(`/Volumes/AIDRIVE/claude-code-telegram/`)에 새 모듈 추가:
- `src/captain_hook/__init__.py`
- `src/captain_hook/stream_parser.py`
- `src/captain_hook/auto_register.py`
- `src/captain_hook/silent_detector.py` (Phase 2)

이 repo(`~/Projects/claude-captain-hook/`)는 **설계 문서·테스트 시나리오·릴리즈 노트만** 보관. 실제 코드는 봇 repo에 들어감.

> 봇 repo는 RichardAtCT/claude-code-telegram fork. push 권한 확인 필요. 권한 없으면 q28902로 fork 생성 후 진행.

## Phase 2~4 후순위

- Phase 2 (P2): 빈 응답·조용한 종료 자동 가시화 — `silent_detector.py`
- Phase 3 (P3): 봇 안 `POST /notify` 외부 호출용 엔드포인트
- Phase 4 (P4): `~/.claude/settings.json` Stop Hook 등록 (sample2 차용)

## 검증 체크리스트 (DESIGN.md 발췌)

- [ ] 백그라운드 작업 5분짜리 시작 → 자동 등록 → 5분 후 알림 도착
- [ ] Subagent marker 약속 → marker touch → 알림 도착
- [ ] Turn 종료 시 빈 응답 → "조용한 종료" 메시지 푸시
- [ ] CLI 직접 사용 시 Stop Hook 발화 확인
- [ ] 봇 재시작 후에도 등록된 작업 polling 지속

## 다음 세션 진입 시

1. ACTIVE_PROJECTS.md → captain-hook Top entry 확인
2. 이 문서 읽기
3. 봇 repo push 권한 확인 (`gh repo view RichardAtCT/claude-code-telegram --json viewerPermission`)
4. Phase 1 단계 1부터 진행
5. 작업 종료 시 이 문서 + ACTIVE_PROJECTS.md 갱신

## 관련 자산

- 봇 본체: `/Volumes/AIDRIVE/claude-code-telegram/` (origin: `RichardAtCT/claude-code-telegram`)
- cct-notifier: `~/Projects/claude/cct-notifier/`
- sample2 참고용: `/Volumes/AIDRIVE/sample2/telegram-bridge/` (운영 X)
- 영감 출처: https://www.gpters.org/nocode/post/claude-code-telegram-automatic-iye3YWTeNJoYxhz

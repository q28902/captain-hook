# RISKS — 박제된 위험·자잘한 누수 (2026-04-26 5개 지적)

## 1. Claude 의존 잔존 (구조적)

| 패턴 | 순진한 설계 | 잔존 위험 | 우리 대안 |
|---|---|---|---|
| `Bash(run_in_background=true)` | 출력에서 PID 정규식 | 출력 포맷 변경 시 무력 | wrapper로 `__BGPID=$!` 캡처 |
| `nohup ... &` | 동일 | 동일 | 동일 |
| `Agent(run_in_background=true)` | marker 약속 prompt 의존 | Claude가 trap 깜빡 | wrapper subprocess `trap EXIT touch` 강제 |

**핵심**: PID/marker 추출은 *출력 파싱*이 아니라 *명령 변형*으로 결정론화한다.

## 2. PID 재사용 오탐

PID는 unsigned 16-bit 또는 32-bit 정수. OS가 종료된 PID를 재사용하면 다른 프로세스를 우리 task로 오인.

**대안**: PID + start_time fingerprint
- Linux: `/proc/<pid>/stat`의 22번 필드(starttime, jiffies)
- macOS: `ps -o lstart= -p <pid>`
- 두 값을 조합한 해시를 추적 키로 사용

## 3. 백그라운드 실패 침묵 (D 패턴)

PROBLEM.md D) 참조. cct-notifier가 PID 사라짐만 감지하고 exit_code 모르면 "성공" 알림 잘못 송신.

**대안**: wrapper에서 `wait $__BGPID; echo $? > /tmp/captain/<id>.exit` 로 exit_code 캡처. cct-notifier가 이 파일 읽어 분기.

## 4. Idempotency 누락

봇 재시작 시 같은 turn의 bg task가 stream replay되면 cct-notifier에 중복 등록 → 알림 2번.

**대안**: `<turn_id>:<tool_call_id>` 해시를 등록 키로. 이미 등록됐으면 skip.

## 5. HTTP /notify 인증 (P3)

localhost 바인딩이라도 같은 머신의 다른 컨테이너·n8n·다른 사용자가 접근 가능. 무인증이면 텔레그램 스팸 가능.

**대안**:
- `.env`에 `CAPTAIN_HOOK_NOTIFY_TOKEN=<random>` 보관
- `POST /notify` 헤더 `X-Captain-Hook-Token` 검증
- 토큰 불일치 → 401

## 6. silent_detector 푸시 메시지 길이

마지막 도구 결과가 1만 줄짜리 grep 결과면 텔레그램 메시지 폭발.

**대안**: Haiku 또는 Gemini Flash로 30단어 요약. 비용 < $0.001/turn. news_intel의 stenographer 패턴 재활용.

## 7. Upstream Divergence (claude-code-telegram fork)

봇 본체에 모듈을 직접 추가하면:
- upstream(`RichardAtCT/claude-code-telegram`) 업데이트 시 수동 merge
- `sdk_integration.py` 시그니처 변경 → captain-hook 깨짐
- 다른 사용자에게 전파 불가 (본인 환경 lock-in)

**대안**: middleware/plugin 인터페이스 PR을 upstream에 먼저. captain-hook은 그 인터페이스의 첫 사용자로 외부 패키지화.

P4에서 이 PR 진행. 그 전까지 P0~P3는 fork 안 직접 수정 허용 (단, 모듈을 `src/captain_hook/`로 격리해 추후 추출 쉽게).

## 8. 덤프 파일 민감 정보

P0 stream-json 덤프에 API key·파일 내용·사용자 메시지 포함 가능.

**대안**: 
- `dumps/`를 .gitignore에 추가 (절대 push X)
- 분석 후 SCHEMA.md만 commit
- 분석 끝나면 dumps/ 삭제 또는 외장 보관

## R9 — captain-hook 자체의 침묵 (메타 누락)

봇 프로세스 죽음 / cct-notifier 죽음 / 디스크 풀 / OOM / 네트워크 단절 시 알림 0.

"100% 보장"은 시스템 boundary 안에서만 성립. 글쓴이도 동일 한계 — 재부팅 시 Bridge daemon 자동구동 누락 사고를 글에서 명시.

**처리 시점: P5 — heartbeat 기반 메타 알림**

- captain-hook 컴포넌트(봇, cct-notifier)가 1분마다 heartbeat 파일 touch
- 별도 경로(SMS, 보조 봇 토큰, 이메일) 워치독이 N분 heartbeat 미수신 시 "down" 알림
- 핵심: **메인 봇과 다른 채널이어야 함**. 같은 봇으로 보내면 봇 죽었을 때 그 알림도 무력 (글쓴이 Bridge 단일경로 한계와 동형)

P5는 P1~P4 안정화 후 진입.

## R10 — AskUserQuestion 빈 응답 자동 생성 (SDK 한계, 2026-04-26 active 라벨 결과)

stdin 막힘 → SDK 자동 빈 응답 → 사용자에 질문 노출 0.
글쓴이의 last_assistant_summary 강제 푸시도 이 패턴에선 무력 — 푸시할 텍스트 자체가 빈 문자열.

A 패턴의 하위 패턴(**A-AUQ**)으로 분류. PROBLEM.md A에 cross-link.

처리 시점: P1 silent_detector와 동시에 AskUserQuestion forwarding 모듈 신설.

검출 신호 (SCHEMA.md 2번):
- 마지막 assistant 메시지 content[]에 `type=="tool_use"` + `name=="AskUserQuestion"`
- 그 직후 result.stop_reason=="end_turn"
- assistant text 응답 길이 0 또는 자동생성 빈 문자열 마커

푸시 페이로드: tool_use.input.question + options 배열 → 텔레그램 inline keyboard 또는 텍스트 fallback.

## 10개 위험 — 우선순위

| # | 위험 | 처리 시점 |
|---|---|---|
| 1, 3 | Claude 의존·실패 침묵 | P1 wrapper 설계 |
| 2 | PID 재사용 | P1 fingerprint |
| 4 | Idempotency | P1 등록 로직 |
| 6 | silent 길이 | P2 요약 |
| 5 | HTTP 인증 | P3 |
| 7 | upstream divergence | P4 PR |
| 8 | 덤프 민감 정보 | P0 .gitignore (즉시) |
| 9 | 메타 누락 (자체 침묵) | P5 heartbeat |
| 10 | 봇 AskUserQuestion 처리 0 | P1 ask_user_handler 신설 |
| 11 | self-noise: 분석 도구 overwrite | P1 v2 any-pattern + path 필터 |
| 12 | API_ERROR push 누락 | P1 v3.1 silent_detector_decide 분기 추가 |
| 13 | 봇 시스템 프롬프트 평문 키 노출 | redact 패턴 5종 추가 + 봇 본체 환경변수 이전 |
| 14 | dumps 파일 날짜 분기 진단 실수 | 항상 ls -lt로 최근 파일 확인 |
| 15 | ASK_USER push 텔레그램 미도착 (코드 대칭인데 비대칭 동작) | P1.7 stderr print + plain fallback + P1.7-ext plain text |
| 16 | 봇 다중 인스턴스 동시 가동 (Conflict 사고) | INTEGRATE.md §5 pkill + 인스턴스 검증 |

## R16 — 봇 다중 인스턴스 동시 가동 (2026-04-27 P1.7 cp 사고)

증상:
- P1.7 cp 후 재시작 시 기존 봇 미kill 상태에서 신규 시작
- `telegram.error.Conflict: terminated by other getUpdates request` 발생
- 두 봇이 같은 token으로 polling → 메시지 라우팅 무작위
- ASK_USER 진단을 흐릴 정도의 노이즈 발생

근본 원인:
- INTEGRATE.md §5 PID kill 로직: `PID=$(pgrep -f claude-telegram-bot | head -1)`
- `head -1`만 잡음 → 2개 이상 가동 시 1개만 kill
- nohup 재시작 시 잔존 봇 살아있음 인지 못 함

처리: INTEGRATE.md §5 `pkill` + 인스턴스 갯수 강제 검증으로 보강.

## R14-후속 — 봇 진짜 stdout/stderr 경로 (2026-04-27 발견)

R14 원본은 "dumps 파일 날짜 분기 진단 실수"였으나, P1.7-ext 진단 중 더 큰 R14 패턴 발견:

봇 stdout/stderr 진짜 경로:
- `/private/tmp/claude-telegram-bot.log` (stdout, structlog JSON, 39MB+ 누적)
- `/private/tmp/claude-telegram-bot.err` (stderr, captain print + 외부 라이브러리 오류)
- `/tmp/bot.log`은 **nohup wrapper만** 담음 (봇 자체 logging 별개)

진단 명령 표준:
- captain ASK_USER/SILENT print → `cat /private/tmp/claude-telegram-bot.err`
- 봇 본체 logger.warning/error → `grep ... /private/tmp/claude-telegram-bot.log`
- /tmp/bot.log은 시작 단계 startup/shutdown 로그만

→ 모든 미래 진단에서 두 경로 동시 grep 표준화 (INTEGRATE.md §5 헬스체크).

## R15 — ASK_USER push 텔레그램 미도착 (2026-04-27 라이브 검증)

증상:
- captain.py ask_user_forwarding_decide payload 결정 정상 (decision log ask_user_pushed=true 박힘)
- sdk_integration P1 hook의 stream_callback 호출 완료 (silent와 동일 emit 코드)
- orchestrator captain_ask_user 분기 코드 정상 (silent와 본문 100% 대칭)
- 그러나 텔레그램 미도착 (세열 시각 검증 N)

진단 한계:
- 봇 stderr (/tmp/bot.log)에 "captain ask_user push failed" 0건 → except 진입 자체 없음
- "BadRequest", "Markdown" 키워드 0건
- silent_push는 정상 도착 → 인프라/권한 문제 아님
- 코드 대칭이라 정적 grep으로 원인 식별 불가

P1.7 패치 (work/orchestrator.py):
- stderr 강제 print: entry, Markdown OK/FAILED, plain fallback 시도
- 다음 cp + 재시작 후 ASK_USER 1건 trigger → /tmp/bot.log grep으로 silent fail 위치 즉시 식별

기대:
- "[captain ASK_USER] entry" 0건 → orchestrator 분기 진입 자체 안 됨 (update_obj.type 매칭 실패)
- "Markdown FAILED" 보임 → Markdown parse 에러 확정 → plain fallback이 도착해야 정상
- 둘 다 OK인데 텔레그램 미도착 → 텔레그램 API 자체 문제 (rate limit, 세션 timeout 등)

### 2026-04-27 후속 — Markdown FAILED 노이즈 잔존

P1.7-ext 적용 후 captain은 plain text만 생성하지만 orchestrator는 여전히 `parse_mode="Markdown"` 시도 → 매 ASK_USER마다 "Markdown FAILED → plain reply OK" 로그 누적.

원인: description에 markdown link 형식 (`[label](url)`) 등 포함 시 entity parse 실패. captain이 plain 보내도 orchestrator의 1차 시도가 Markdown이라 일부 텍스트(`(`,`)`, `:` 조합)가 entity로 오인 가능.

처리 시점: P1.7-ext-final (R13-ext와 묶음 권장).
코드 변경: orchestrator.py captain_ask_user 분기 첫 reply_text의 `parse_mode="Markdown"` 제거 (또는 captain push payload에 metadata로 plain 명시 → orchestrator가 분기).

부수 효과:
- /private/tmp/claude-telegram-bot.log 39MB 누적 속도 감소
- 진짜 에러 가시성 향상

### R15 후속 처리 완료 (2026-04-27, P1.7-ext-final)

- work/orchestrator.py captain_ask_user 분기 patched: parse_mode="Markdown" 제거, plain only
- captain은 plain text 보장(P1.7-ext) → Markdown 시도 자체 안 함 → "Markdown FAILED" 로그 누적 차단
- 운영본 cp + 봇 재시작 후 stderr "[captain ASK_USER] plain OK"만 보여야 정상

### 2026-04-27 R15 후속 처리 완료 (P1.7-ext-final)
work/orchestrator.py captain_ask_user 분기 — Markdown 시도 제거, plain text only.
captain은 P1.7-ext로 plain 보장이라 Markdown fallback 불필요. 노이즈 차단.

### 2026-04-27 R13-ext 처리 완료
- /Volumes/AIDRIVE/CLAUDE.md "## API 키" 섹션 평문 키 5종 → 환경변수 참조 표현
- claude-code-telegram/memory/2026-03-30.md 평문 키 1건 redact 처리
- 봇 .env (gitignored, chmod 600)에서 키 로드 (load_dotenv 가동 중)
- test_orchestrator.py:602의 `eyJhbGciOiJIUzI1NiJ9.payload.sig`는 fake fixture (.payload.sig) → 미수정

## R13 — 봇 시스템 프롬프트 평문 키 노출 (2026-04-27 사고)

발견:
- 본 secretarybot 자기점검 turn에서 봇 instruction 또는 CLAUDE.md가 텔레그램 응답에 그대로 노출
- 노출 키: DeepSeek / OpenRouter / Gemini / n8n / Tavily 5종 평문
- captain-hook redaction 패턴(sk-, Bearer, api_key=, AIza, gho_, /Users/) 중 sk-/AIza만 부분 매칭
- 즉 redaction 통과해도 일부 키는 그대로 dump

근본 원인:
- 봇 본체가 시스템 프롬프트에 키 평문 박음 (환경변수 미사용 또는 fallback)
- captain redaction이 키 종류 전수 커버 못함

위험도 재평가 (2026-04-27 세열 결정):
- 노출 채널 = **본인 개인 텔레그램만**. 외부 공개 0, git public 0
- 외부 유출 가능성 매우 낮음 → **키 rotate 불필요**
- 향후 노출 차단 (redact 패턴 + 본체 환경변수 이전)에 집중

### R13-ext 처리 완료 (2026-04-27)

- `/Volumes/AIDRIVE/CLAUDE.md`: 평문 키 5종 제거 → 환경변수 참조 형태로 교체 ✓
- `claude-code-telegram/memory/2026-03-30.md`: redaction 패턴 적용, 평문 0건 ✓
- `tests/unit/test_orchestrator.py`: 가짜 JWT fixture (`eyJhbGciOiJIUzI1NiJ9.payload.sig`) — sanitize 불필요
- `data/bot.db`: SQLite binary, 별도 진단 보류 (audit_log 등 메시지 기록일 가능성)
- 봇 `.env` 키 5종 추가: 세열님 직접 작업 (DEEPSEEK/OPENROUTER/GEMINI/N8N/TAVILY_API_KEY)
- captain-hook redact 패턴 5종 추가 박힘 (work/sdk_integration.py)

처리:
1. ~~키 5종 즉시 회수·rotate~~ — 위험도 재평가 후 취소
2. **봇 본체에서 시스템 프롬프트 → 환경변수 이전** (captain-hook 범위 외, 별도 작업)
3. **captain-hook redaction 패턴 추가** (work/sdk_integration.py `_CAPTAIN_REDACT_PATTERNS`):
   - `sk-or-v1-[a-f0-9]{64}` (OpenRouter)
   - `AIzaSy[A-Za-z0-9_-]{33}` (Gemini, AIza{30,}보다 정확)
   - `tvly-(dev|prod)-[A-Za-z0-9]{20,}` (Tavily)
   - `eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}` (JWT, n8n 등)
   - `sk-d[0-9a-f]{30,}` (DeepSeek)
4. **dumps/ 전체 grep + 발견 시 해당 파일 sanitize 또는 삭제** (2026-04-27 격리 완료: `/tmp/leaked-dumps-quarantine/`)
5. **git history grep + 발견 시 history rewrite** (force push) — 검사 완료, 0 hit ✓

영향 범위:
- captain-hook 자체 결함은 redaction 미커버만 (3번)
- 1·2번은 봇 본체 사고. captain-hook은 기록자(messenger). 봇 본체에 R13-ext 별도 박제 권장

처리 시점: 즉시 (P1.5 디버그보다 우선)

## R12 — API_ERROR push 누락 (P1 v3 결함, 2026-04-26 자연 발생 1건 발견)

**증상**: result.is_error=true + result=null + terminal_reason=null인 turn 발생 (1777203673).
- 직전 시퀀스: docs Edit 2건 + Bash git commit 도중 강제 종료
- 사용자가 본 마지막 = Bash git commit tool_use, 봇 응답 0건
- captain.classify는 TURN_END_API_ERROR 정상 분류
- 그러나 silent_detector_decide는 SILENT/TOOL_ERROR만 push, **API_ERROR 분기 X** → 사용자 알림 0

**원인**: P1 v1~v3 silent_detector_decide 명세에 API_ERROR 빠짐.

**처리 (P1 v3.1)**:
- `silent_detector_decide`에 API_ERROR 분기 추가
- 글쓴이 가드(text_response_count) **무시** — turn 자체가 강제 종료라 알림 필수
- 푸시 메시지: "🛑 Claude turn 비정상 종료 — API/SDK 에러. 응답 누락 가능. 마지막 도구 호출이 잘렸을 수 있음."
- unit test 5번 갱신 (replies=1 + 비정상 종료 마커)

### 자연 발생 누적 (2026-04-26 ~ 2026-04-27)

| 시각 | 사고 | captain "🛑" push |
|---|---|---|
| 04-26 git commit 강제 종료 | turn 도중 외부 종료 | ✅ |
| 04-27 R13-ext 작업 중 | Claude turn 비정상 종료 | ✅ |
| 04-27 API 500 | Anthropic 측 장애 | ✅ |
| 04-27 진입 점검 중 | API/SDK 에러 | ✅ |

4건 누적. R12 push 분기가 captain-hook 작업에서 가장 자주 trigger되는 신호.
글쓴이 Stop Hook 방식으론 last_assistant_summary 빈 문자열이라 푸시 거리 자체 0.
SCHEMA.md 4' 항목 🟢 등급 자연 검증 완료.

## R11 — Self-noise overwrite (P1 v1 결함, 2026-04-26 라이브 검증 결과)

**증상**: P1 v1 (마지막 값 단순 보존) 라이브 검증 4건 중 2건 실패
- TOOL_ERROR: import error tool_result.is_error=true가 후속 jq 분석 false로 덮임 → NORMAL 오분류
- SILENT: nohup sleep tool_use stop_reason이 후속 분석 end_turn으로 덮임 → NORMAL 오분류

**원인**: TurnState 마지막 값 의존 + captain 자체 분석 호출이 turn 안 추가 도구로 박힘 (self-noise).

**caller.type 실측 결과**: 모든 도구 호출 `caller.type=="direct"` → 분기 신호 무력 (SCHEMA.md 참조).

**처리 (P1 v2 + v3)**:
- TurnState 재설계: any-pattern 누적 (any_tool_error / any_ask_user_question / last_meaningful_stop_reason)
- 첫 실패 도구 보존 (덮어쓰기 X)
- self-noise path 필터: `captain-hook|/dumps/|_captain_dump_raw|p1_decisions` 박힌 도구는 last_user_* 갱신 X
- caller.type 1차 보조 검사 (future-proof)

회귀 방지 unit test 3건 추가 (8/9/10), 10/10 통과.

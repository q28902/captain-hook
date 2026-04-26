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

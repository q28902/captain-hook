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

## R10 — 봇 본체에 AskUserQuestion 처리 로직 0 (2026-04-26 active 라벨 결과)

`grep -rn "AskUserQuestion\|ask_user\|permission_prompt" /Volumes/AIDRIVE/claude-code-telegram/src/` → **0건**.

증상:
- Claude가 AskUserQuestion 호출 → SDK가 stdin 막힘 자동 감지 → 빈 응답 자동 생성 → 사용자에게 옵션 화면 노출 X
- 본 active 라벨 turn에서 빈 응답 도착한 진짜 원인. 사용자 의도 X, 시스템 한계.

영향:
- glunsiz 글쓴이 Stop Hook은 AskUserQuestion → 텔레그램 force_reply → 답변 받기 흐름이 핵심 가치 중 하나. 우리 봇엔 이 통로 부재
- 5번 silent와 SDK 신호 동일 (`stop_reason: "tool_use"`) → silent_detector가 잘못 처리하면 노이즈 발생

처리 시점: **P1에 신규 작업 1건 추가**
- `src/captain_hook/ask_user_handler.py` 신설
- stream_parser가 `tool_use(name=AskUserQuestion)` 감지 시 라우팅
- input.questions[].options 파싱 → 텔레그램 inline keyboard 또는 force_reply 송신
- 사용자 응답 → SDK stdin 주입 (또는 Hook bridge 패턴 차용)
- 글쓴이 sample2 reply_to_message 매칭 패턴 재활용 가능

P1 로드맵 업데이트 필요.

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

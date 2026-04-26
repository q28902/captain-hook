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

## 8개 위험 — 우선순위

| # | 위험 | 처리 시점 |
|---|---|---|
| 1, 3 | Claude 의존·실패 침묵 | P1 wrapper 설계 |
| 2 | PID 재사용 | P1 fingerprint |
| 4 | Idempotency | P1 등록 로직 |
| 6 | silent 길이 | P2 요약 |
| 5 | HTTP 인증 | P3 |
| 7 | upstream divergence | P4 PR |
| 8 | 덤프 민감 정보 | P0 .gitignore (즉시) |

# P0 — stream-json 이벤트 덤프 (1~2일 작업)

## 목적

추측한 스키마로 P1 파서를 짜면 production 첫 turn에서 깨지는 흐름이 거의 확정. **실측 데이터 기반 설계가 유일한 방어**.

## 방법

### 1. 로깅 훅 박기 — fail-safe + redaction

위치: `/Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py`

stream-json 이벤트 수신 루프에 한 블록 추가:

```python
# captain-hook P0 dump — fail-safe, never break bot
import json, os, re, sys, time
from datetime import date

DUMP_DIR = os.path.expanduser("~/Projects/claude-captain-hook/dumps")

# Redaction 패턴 — 평문 로컬 파일도 안전하게
_REDACT_PATTERNS = [
    (re.compile(r'sk-[A-Za-z0-9_-]{20,}'), 'sk-REDACTED'),
    (re.compile(r'Bearer\s+[A-Za-z0-9._-]+', re.IGNORECASE), 'Bearer REDACTED'),
    (re.compile(r'(["\']?(?:api_?key|token|secret|password)["\']?\s*[:=]\s*["\']?)[^"\'\s,}]+', re.IGNORECASE), r'\1REDACTED'),
    (re.compile(r'/Users/[^/\s"\']+'), '/Users/REDACTED'),
    (re.compile(r'AIza[0-9A-Za-z_-]{30,}'), 'AIza-REDACTED'),  # Gemini
    (re.compile(r'gho_[A-Za-z0-9]{30,}'), 'gho-REDACTED'),     # GitHub
]

def _redact(s: str) -> str:
    for pat, repl in _REDACT_PATTERNS:
        s = pat.sub(repl, s)
    return s

try:
    os.makedirs(DUMP_DIR, exist_ok=True)
    raw = json.dumps({"ts": time.time(), "session_id": session_id, "event": event}, ensure_ascii=False)
    redacted = _redact(raw)
    with open(f"{DUMP_DIR}/{date.today()}.jsonl", "a") as f:
        f.write(redacted + "\n")
except Exception as e:
    # dump 실패가 봇 본체 죽이는 일 0
    print(f"[captain-hook P0] dump skipped: {e}", file=sys.stderr)
```

**원칙**:
- 로깅 외 다른 로직 변경 X. 부작용 0
- 모든 코드는 `try/except`로 감싸 봇 본체 영향 차단
- redaction은 dump 시점 적용 — 평문 로컬 파일도 안전 (외부 공유·이슈 첨부 시 매번 손으로 지울 필요 X)
- 감지 실패 패턴 발견 시 `_REDACT_PATTERNS`만 추가

### 2. 종료 조건 — 시간 아님, 샘플 충분성

**P0의 본래 목적은 시간이 아니라 스키마 확신**. "1주일 기다렸는데 자연 발생 0인 패턴"이 있으면 그대로 P1 가서 깨짐. 종료 기준은 패턴별 임계 샘플 도달:

| 패턴 | 임계 샘플 |
|---|---|
| `Bash(run_in_background=true)` tool_use | ≥ 30건 |
| `Bash(command="nohup ... &")` tool_use | ≥ 10건 |
| `Agent(run_in_background=true)` tool_use | ≥ 10건 |
| Silent turn (텍스트 응답 0 또는 도구 결과만) | ≥ 5건 |
| 정상 tool_use·tool_result 페어 | ≥ 100건 (스키마 일반화용) |
| Turn 종료 6가지 상황 (글쓴이 분류) | 각 ≥ 1건 (§매핑검증 참조) |

passive 캡처 + active 라벨 데이터 합산. **위 6개 모두 충족** = P1 진입 조건.

### 3. Active 데이터 생성 (첫날 필수)

passive 캡처만으론 패턴 불균형. 첫날 의도적 라벨 데이터 5~10개 생성 → P1 파서 unit test fixture로 직접 재활용.

생성 스크립트 (예시):

```bash
# Bash bg 다양한 변형 5건
sleep 300 &           # 단순 bg
nohup sleep 60 &      # nohup
(sleep 30 && exit 1) &  # 의도적 실패 (D 패턴 fixture)
(sleep 5 && exit 0) &   # 즉시 정상 종료
nohup python -c "import nonexistent" 2>err.log &  # import error fixture

# Agent bg 시나리오
# Aki 세션에서 Agent run_in_background=true로 더미 작업 5건 (sleep, ls, etc)
```

각 라벨링: 어떤 패턴인지, 기대 분기(✅/⚠️/❓)가 무엇인지 별도 노트에 기록 → P1 검증 케이스로 직결.

### 4. 일일 점검 — jq cookbook (충분성 자동 판정)

dump만 쌓고 분석을 P0 끝나고 시작하면 1주일 낭비. 매일 돌려 종료 조건 자동 판정.

```bash
DUMPS=~/Projects/claude-captain-hook/dumps
JQ() { cat $DUMPS/*.jsonl | jq -r "$1" 2>/dev/null; }

echo "=== 전체 라인 ==="
wc -l $DUMPS/*.jsonl

echo "=== Bash run_in_background=true ==="
JQ 'select(.event.type=="tool_use" and .event.name=="Bash" and .event.input.run_in_background==true)' | wc -l

echo "=== Bash nohup heuristic ==="
JQ 'select(.event.type=="tool_use" and .event.name=="Bash" and (.event.input.command|tostring|test("nohup.+&\\s*$")))' | wc -l

echo "=== Agent run_in_background=true ==="
JQ 'select(.event.type=="tool_use" and .event.name=="Agent" and .event.input.run_in_background==true)' | wc -l

echo "=== Silent turn (turn 종료 + 텍스트 응답 0건) ==="
# session_id 그룹화 후 마지막 이벤트가 stop이고 그 turn에 text 응답 없는 경우
# (실제 스키마 확인 후 보강)

echo "=== 임계 도달 여부 ==="
# 위 4개가 모두 임계 넘으면 "P1 GO" 출력
```

이 스크립트를 `scripts/p0_check.sh`로 commit. 매일 실행해 임계 도달 즉시 P0 종료.

### 5. 분석 (임계 도달 시)

`docs/SCHEMA.md`(신규) 작성:
- 각 이벤트의 실제 필드 구조
- PID 추출 가능 위치 (tool_result에 PID가 어떻게 노출되는지)
- exit_code·stderr 캡처 가능 시점
- Agent SubAgent 호출 시 marker file 약속이 prompt 어디에 박히는지

## §매핑검증 — turn-end 6가지 상황 (글쓴이 분류 기준)

P0 덤프 분석 시 stream-json에서 다음 6가지가 각각 어떤 이벤트 시퀀스로 구분되는지 식별:

| # | 상황 | stream-json 식별 가설 | active 검증 방법 |
|---|---|---|---|
| 1 | 명시적 완료 | message_stop + 텍스트 ≥ 1 | 일반 turn 1건 |
| 2 | AskUserQuestion | tool_use(name=AskUserQuestion) 직후 종료 | 의도 호출 1건 |
| 3 | 정보 제공 후 대기 | 1과 동일 추정 | 1과의 차이 검증 |
| 4 | 에러/블로커 | error 이벤트 + 비정상 종료 | 의도적 빌드 실패 1건 |
| 5 | 도구 사용 후 응답 대기 | 도구 결과 + 텍스트 0 | silent_detector 핵심 타겟 |
| 6 | Idle | 1과 동일? 모호 | 별도 종료 신호 있는지 확인 |

- 4번 = D 패턴(실패 침묵)과 겹침 → 분기 매핑 확인 필수
- 5번 = silent_detector 핵심 타겟 (텍스트 0건 + 도구 결과 ≥ 1)
- 6번 = Anthropic SDK가 별도 신호로 구분하는지 미상 → P0에서 확정

§종료 조건 표에 6가지 각각 ≥ 1건 도달 조건 포함됨.

## 다음 단계 (P1 진입 조건)

- [ ] 5종 패턴 임계 샘플 모두 충족 (위 표)
- [ ] Active 라벨 데이터 5~10건 + 기대 분기 노트
- [ ] SCHEMA.md 작성 완료
- [ ] wrapper 인터셉트 가능성 검증 (SDK가 tool_use 전에 명령 변형을 허용하는지 — 안 되면 fallback 설계 필요)

위 4개 충족 시에만 P1 착수. **시간(1주일)은 참고일 뿐 종료 기준 아님.**

## 주의

- redaction은 1차 방어. 새 패턴 발견 시 `_REDACT_PATTERNS` 즉시 보강
- 디스크 사용량 모니터: jsonl 1만 라인당 ~5MB 예상. 1주일 100MB 이내
- 로깅 훅 자체가 SDK 호출 latency 늘리지 않도록 — append만, flush·sync 강제 X
- 분석 끝나면 dumps/ 외장 보관 또는 삭제 (장기 평문 노출 회피)

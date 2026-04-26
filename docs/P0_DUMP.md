# P0 — stream-json 이벤트 덤프 (1~2일 작업)

## 목적

추측한 스키마로 P1 파서를 짜면 production 첫 turn에서 깨지는 흐름이 거의 확정. **실측 데이터 기반 설계가 유일한 방어**.

## 방법

### 1. 로깅 훅 박기

위치: `/Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py`

stream-json 이벤트 수신 루프에 한 줄 추가:

```python
# captain-hook P0 dump
import json, os
from datetime import date
DUMP_DIR = os.path.expanduser("~/Projects/claude-captain-hook/dumps")
os.makedirs(DUMP_DIR, exist_ok=True)
with open(f"{DUMP_DIR}/{date.today()}.jsonl", "a") as f:
    f.write(json.dumps({"ts": time.time(), "session_id": session_id, "event": event}) + "\n")
```

**원칙**: 로깅 외 다른 로직 변경 X. 부작용 0.

### 2. 수집 기간

- 시작: P0 박은 시점
- 종료 조건: 아래 3종 이벤트가 각각 최소 5건 이상 수집
  - `Bash(run_in_background=true)` tool_use
  - `Bash(command="nohup ... &")` tool_use
  - `Agent(run_in_background=true)` tool_use

세열님 평소 사용 패턴이면 1주일 내 충분히 수집 예상.

### 3. 일일 점검

```bash
ls -la ~/Projects/claude-captain-hook/dumps/
wc -l ~/Projects/claude-captain-hook/dumps/*.jsonl
# 패턴별 카운트:
jq 'select(.event.type=="tool_use" and .event.name=="Bash" and .event.input.run_in_background==true)' \
   ~/Projects/claude-captain-hook/dumps/*.jsonl | wc -l
```

### 4. 분석 (수집 종료 후)

`docs/SCHEMA.md`(신규) 작성:
- 각 이벤트의 실제 필드 구조
- PID 추출 가능 위치 (tool_result에 PID가 어떻게 노출되는지)
- exit_code·stderr 캡처 가능 시점
- Agent SubAgent 호출 시 marker file 약속이 prompt 어디에 박히는지

## 다음 단계 (P1 진입 조건)

- [ ] dumps/ 누적 1주일치 또는 3종 이벤트 각 5건 이상
- [ ] SCHEMA.md 작성 완료
- [ ] wrapper 인터셉트 가능성 검증 (SDK가 tool_use 전에 명령 변형을 허용하는지 — 안 되면 fallback 설계 필요)

위 3개 충족 시에만 P1 착수.

## 주의

- 덤프 파일에 민감 정보(API key, 파일 내용) 포함될 수 있음 → repo .gitignore에 `dumps/` 추가
- 디스크 사용량 모니터: jsonl 1만 라인당 ~5MB 예상. 1주일 100MB 이내
- 로깅 훅 자체가 SDK 호출 latency 늘리지 않도록 — append만, flush·sync 강제 X

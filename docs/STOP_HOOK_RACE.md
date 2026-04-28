# Stop Hook Race Condition — 분석 + 처방 (v1.1, 2026-04-28)

Claude Code Stop hook 작성 시 transcript flush 타이밍과 충돌해 **stale 메시지를 마지막으로 인식하는 race condition**이 존재한다. 이 문서는 발견 경위·원인·재현·표준 처방을 박제한다. captain-hook 산하의 모든 Stop hook은 이 패턴을 따를 것.

---

## 1. 발견 경위

`/Volumes/AIDRIVE/claude-code-telegram/hooks/table-guard.py`는 CLAUDE.md "표 출력 안전" 규칙(한글 cell width > 12자 차단)을 자동 게이트화하기 위한 Stop hook. 라이브 가동 직후 다음 패턴 발생:

1. Aki 응답 A — 위반 표 포함 → 훅이 정상 차단
2. Aki 응답 B — 표 없는 깨끗한 bullet 응답
3. **그런데 훅이 다시 차단** — block reason은 응답 A의 셀 (`'cct-notifier 폐지'` 17자) 명시

응답 B에는 그 표가 없는데 훅이 잡았다. 즉 훅이 **응답 A를 마지막 메시지로 본다**.

## 2. 원인 — Stop hook 발동 시점과 transcript flush 사이 race

```
Claude SDK
   │ stream-json 토큰 생성
   ▼
transcript JSONL append (buffered)
   │
   ▼
stop_reason="end_turn" 송출
   │   (harness가 transcript flush 보장 못함)
   ▼
🚨 Stop hook spawn — stdin에 transcript_path 전달
   │
   ▼
훅이 파일 읽음 → 마지막 entry가 아직 안 박힘 → 직전 turn entry를 "마지막"으로 인식
```

핵심: Claude harness가 **flush와 hook spawn 사이에 동기화를 보장 안 함**. 대부분의 경우 fast filesystem이라 그냥 작동하지만, 디스크 부하·외장 SSD·VM 환경 등에서 늦으면 race 발현.

## 3. 무한 루프 위험

훅이 race로 옛 entry 보고 block 송출 → Claude가 재작성 → 다시 Stop hook fire → 다시 race로 같은 옛 entry 또 잡음 → **block 무한 반복**. 사용자는 답을 영영 못 받음.

## 4. 1차 처방 — `stop_hook_active` 플래그

Claude Code Stop hook 입력 JSON에 `stop_hook_active: true` 필드가 있다. 이는 "harness가 이전 block 결과로 Claude를 다시 세션에 넣은 재진입"을 의미. 훅은 이 값을 보면 **위반 검사 자체를 건너뛰어 무한 루프 방지**.

```python
if inp.get("stop_hook_active") is True:
    return 0
```

이걸로 **무한 루프는 끊기지만**, race로 직전 turn 위반이 잘못 잡히는 1차 사고 자체는 그대로. 1번에서 잡힌 block은 사용자에게 노이즈로 전달.

## 5. 2차 처방 — UUID + end_turn + 폴링 (v1.1 표준 패턴)

### 핵심 아이디어

훅 입장에서 "지금 막 끝난 그 turn"을 정확히 식별해야 한다. Claude transcript JSONL의 각 entry는:

```json
{
  "type": "assistant",
  "uuid": "237fc06d-cf8c-4ee4-a75e-e54cf5044873",
  "timestamp": "2026-04-28T01:44:29.512Z",
  "message": {
    "role": "assistant",
    "stop_reason": "end_turn",
    "content": [{"type": "text", "text": "..."}],
    ...
  }
}
```

3가지 필드 활용:
- **`uuid`** — 글로벌 유일. "이 entry 이미 봤나" 식별
- **`stop_reason: "end_turn"`** — turn 중간의 tool_use entry 무시. 진짜 종료 entry만 검사
- **state file** — 직전 fire에서 검사한 uuid 저장 (예: `/tmp/table-guard-state.json`)

### 알고리즘

```
1. state.last_uuid 읽기
2. budget(예: 3초) 동안 100ms 간격 polling:
   - transcript에서 stop_reason=end_turn 이고 uuid != state.last_uuid 인 entry 검색
   - 찾으면 break
3. 못 찾고 timeout → silent pass (사용자 가두지 않음)
4. 찾으면:
   - state.last_uuid = new uuid (block 송출 전에도 무조건 저장)
   - 위반 검사
   - 위반 시 decision:block 송출
```

### 왜 이게 race를 처리하나

- transcript가 늦게 flush되면 폴링이 기다려준다 → 새 entry 등장 즉시 검사
- 영영 안 들어와도 (`hook bug`) 3초 후 silent pass — 사용자 갇히지 않음
- 검사 직전에 state 갱신하므로 재진입 시 같은 uuid 보고 즉시 통과 → 재차단 X
- multi-part turn (text → tool_use → text) 도 끝의 end_turn entry만 검사

### `stop_hook_active` 보험은 유지

state file이 망가지거나 state·transcript 동기 깨지는 사고 대비. 이중화.

## 6. 평소 지연 vs 최악 케이스

| 시나리오 | 지연 |
|---|---|
| 정상 (transcript flush 빠름) | ~수십 ms |
| race 발동 (transcript 200~500ms 지연) | 200~500 ms |
| race 영영 미해소 (degenerate) | 3000 ms (POLL_BUDGET_S) → silent pass |

## 7. 코드

표준 구현은 `~/Projects/claude-captain-hook/hooks/table-guard.py` 참조. 다른 Stop hook(예: 파괴적 명령 차단·6포인트 보고 누락 검사·n8n 워크플로우 비인가 수정 차단) 작성 시 동일한 race 핸들링 골격을 복제해 쓸 것.

## 8. 다음 보강 후보

- transcript 파일 mtime 비교로 "변동 있을 때만 폴링" 최적화 (현재는 무조건 폴링)
- `state.last_uuid` 외 `state.last_block_uuid`도 분리 저장해 "block 후 같은 위반 재발" 케이스 정확 추적
- harness 측 fix: harness가 hook spawn 전 transcript fsync 보장 (Anthropic 측 변경 필요)

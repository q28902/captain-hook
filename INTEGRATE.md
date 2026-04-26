# INTEGRATE — captain.py 운영본 통합 가이드

P1 unit test 통과(7/7) 후 봇 운영본에 통합하는 절차.

## 1. 코드 배치 (백업 + cp, 절대경로)

**1a. 백업 (sdk_integration.py + orchestrator.py)**
```bash
TS=$(date +%Y%m%d-%H%M%S)
cp /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py.bak.p1.${TS}
cp /Volumes/AIDRIVE/claude-code-telegram/src/bot/orchestrator.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/bot/orchestrator.py.bak.p1.${TS}
echo "BACKUP_TS=${TS}"   # 롤백 시 사용
```

**1b. captain.py 복제 (신규 파일이라 백업 불필요)**
```bash
cp /Users/inseyeol/Projects/claude-captain-hook/src/captain.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/captain.py
```

**1c. 패치된 sdk_integration.py / orchestrator.py 복제 (work/ 검증본)**
```bash
cp /Users/inseyeol/Projects/claude-captain-hook/work/sdk_integration.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py
cp /Users/inseyeol/Projects/claude-captain-hook/work/orchestrator.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/bot/orchestrator.py
# (orchestrator.py 패치는 다음 세션에서 작성)
```

봇 repo 안에선 `from src.captain import ...` 또는 패키지 구조에 따라 `from ..captain import ...`.

## 2. sdk_integration.py 변경 (3곳)

### (a) 모듈 상단 import 추가

기존 P0 dump 블록 아래에 1줄:

```python
from src.captain import TurnState, TurnEnd, classify, silent_detector_decide, ask_user_forwarding_decide, log_decision
```

### (b) execute_command 안 — turn 시작 시 state 생성

`messages: List[Message] = []` 직후:

```python
captain_state = TurnState()
```

### (c) raw_data loop 안 — update + classify

기존 P0 tee 직후, parse_message 직전에 추가:

```python
async for raw_data in client._query.receive_messages():
    _captain_dump_raw(raw_data, session_id)
    # captain-hook P1
    captain_state.update(raw_data)
    classification = classify(raw_data, captain_state)
    if classification != TurnEnd.TURN_PROGRESS:
        silent_payload = silent_detector_decide(captain_state, classification)
        ask_user_payload = ask_user_forwarding_decide(captain_state, classification)
        log_decision(captain_state, classification, silent_payload, ask_user_payload)
        # 푸시 페이로드는 stream_callback으로 orchestrator에 전달 (다음 단계)
        if silent_payload and stream_callback:
            await stream_callback(StreamUpdate(
                type="captain_silent_push",
                content=silent_payload["text"],
                metadata={"level": silent_payload.get("level", "info")},
            ))
        if ask_user_payload and stream_callback:
            await stream_callback(StreamUpdate(
                type="captain_ask_user",
                content=ask_user_payload["text"],
                metadata={"options": ask_user_payload.get("options", [])},
            ))
    try:
        message = parse_message(raw_data)
    # ... 기존 로직 ...
```

## 3. orchestrator.py 변경 (stream_callback 처리)

**위치 확정 (grep 검증)**:
- 정의: `src/bot/orchestrator.py:716` — `def _make_stream_callback(self, ...)`
- 내부 클로저: `line 749` — `async def _on_stream(update_obj: StreamUpdate) -> None`
- 호출 위치 3곳: `line 1005, 1271, 1480` (agentic + classic 진입점)

**패치 위치**: line 749 `_on_stream` 본문 시작 직후, 기존 interrupt 검사(line 751) 직전 또는 직후에 captain 분기 추가.

```python
async def _on_stream(update_obj: StreamUpdate) -> None:
    # captain-hook P1 분기 (신규)
    if update_obj.type == "captain_silent_push":
        # progress_msg 또는 새 메시지로 푸시 — chat_id는 클로저에서 가져옴
        # progress_msg.chat_id 활용 (없으면 update.message.chat.id)
        try:
            await progress_msg.reply_text(
                update_obj.content or "",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning("captain silent push failed", error=str(e))
        return  # 기존 로직 우회
    if update_obj.type == "captain_ask_user":
        # P1 1차: 텍스트 fallback (number prefix). inline keyboard는 P1.5
        try:
            await progress_msg.reply_text(
                update_obj.content or "",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning("captain ask_user push failed", error=str(e))
        return

    # 기존 로직 (interrupt 검사부터 그대로)
    if interrupt_event is not None and interrupt_event.is_set():
        return
    # ...
```

**주의**:
- `progress_msg`는 클로저 변수로 이미 잡혀있음 (line 716 시그니처 인자)
- `text_response_count` 갱신은 sdk_integration.py 측이 stream_callback 송신 직전에 captain_state에 직접 +1 (orchestrator는 모름)
- 즉 sdk_integration.py에서 `await stream_callback(...)` 호출 후 `captain_state.text_response_count += 1` 1줄 추가

## 4. 검증 시나리오

운영본 교체 후 봇 재시작, 다음 4가지 케이스 텔레그램에서 호출:

1. **NORMAL**: 일반 텍스트 응답 turn → 푸시 0건 (기존과 동일)
2. **SILENT**: "ls /tmp 한 번 실행하고 결과 보고하지 마" → 봇이 자동 silent 푸시 1건
3. **ASK_USER**: AskUserQuestion 호출 → 봇이 옵션 텍스트 푸시 1건
4. **TOOL_ERROR**: "python -c 'import nx' 실행해" → 봇이 ⚠️ 도구 실패 + stderr 푸시

각 케이스마다 `~/Projects/claude-captain-hook/dumps/<date>.p1_decisions.jsonl` 라인 추가 확인.

## 5. 봇 재시작 (PID 자동 추출)

§1에서 백업·cp는 이미 끝낸 상태 가정. 여기는 봇 종료 + 재시작만.

```bash
# 5a. 현재 PID 자동 추출 + 종료 (하드코딩 X)
PID=$(ps -ef | grep claude-telegram-bot | grep -v grep | awk '{print $2}' | head -1)
if [ -z "$PID" ]; then
    echo "ERROR: bot PID not found — is bot running?"
else
    echo "killing PID=$PID"
    kill "$PID"
    sleep 2
    # 안 죽었으면 SIGKILL
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
fi

# 5b. 재시작 (nohup + 로그 명시)
cd /Volumes/AIDRIVE/claude-code-telegram && \
    nohup poetry run make run > /tmp/bot.log 2>&1 &
NEW_PID=$!
echo "new PID: $NEW_PID"

# 5c. 헬스체크 (30초 대기 → ERROR 검색 + 프로세스 살아있는지)
sleep 30
echo "--- bot.log ERROR/exception/traceback ---"
tail -100 /tmp/bot.log | grep -iE "error|exception|traceback" | head -10
echo "--- process check ---"
ps -ef | grep claude-telegram-bot | grep -v grep | head -1
```

## 6. 롤백

§1에서 출력한 `BACKUP_TS` 사용:

```bash
# 백업 복원
cp /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py.bak.p1.${BACKUP_TS} \
   /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py
cp /Volumes/AIDRIVE/claude-code-telegram/src/bot/orchestrator.py.bak.p1.${BACKUP_TS} \
   /Volumes/AIDRIVE/claude-code-telegram/src/bot/orchestrator.py
rm -f /Volumes/AIDRIVE/claude-code-telegram/src/captain.py

# 봇 재시작 (§5 동일 흐름)
PID=$(ps -ef | grep claude-telegram-bot | grep -v grep | awk '{print $2}' | head -1)
[ -n "$PID" ] && kill "$PID" && sleep 2
cd /Volumes/AIDRIVE/claude-code-telegram && \
    nohup poetry run make run > /tmp/bot.log 2>&1 &
```

## 7. 다음 세션 즉시 작업

본 세션은 **3종 모듈 본체 + unit test + INTEGRATE.md 작성**까지. orchestrator.py 패치 + 운영본 교체 + 검증 시나리오 4건은 다음 세션.

다음 세션 진입 순서:
1. ACTIVE_PROJECTS → captain-hook SESSION_HANDOFF
2. INTEGRATE.md (이 파일) §3 orchestrator 패치 작성 → work/orchestrator.py
3. orchestrator unit test (mock StreamUpdate)
4. 운영본 교체 + 봇 재시작 (§5)
5. 검증 시나리오 4건 (§4)
6. 결과 보고 + SESSION_HANDOFF 갱신

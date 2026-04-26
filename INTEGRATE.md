# INTEGRATE — captain.py 운영본 통합 가이드

P1 unit test 통과(7/7) 후 봇 운영본에 통합하는 절차.

## 1. 코드 배치

```bash
# captain-hook repo의 src/captain.py를 봇 repo로 복제
cp ~/Projects/claude-captain-hook/src/captain.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/captain.py
```

봇 repo 안에선 `from src.captain import ...` 또는 패키지 구조에 따라 import.

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

기존 stream_callback이 StreamUpdate를 받아 텔레그램 송신하는 위치에 분기 추가:

```python
async def stream_callback(update: StreamUpdate):
    if update.type == "captain_silent_push":
        await self.bot.send_message(
            chat_id=chat_id,
            text=update.content,
            parse_mode="Markdown",
        )
        captain_state.text_response_count += 1  # 가드 갱신
    elif update.type == "captain_ask_user":
        # 옵션을 inline keyboard로 (또는 텍스트 fallback)
        # P1 1차는 텍스트 fallback만, inline keyboard는 P1.5에서 보강
        await self.bot.send_message(
            chat_id=chat_id,
            text=update.content,
            parse_mode="Markdown",
        )
        captain_state.text_response_count += 1
    else:
        # 기존 로직
        ...
```

## 4. 검증 시나리오

운영본 교체 후 봇 재시작, 다음 4가지 케이스 텔레그램에서 호출:

1. **NORMAL**: 일반 텍스트 응답 turn → 푸시 0건 (기존과 동일)
2. **SILENT**: "ls /tmp 한 번 실행하고 결과 보고하지 마" → 봇이 자동 silent 푸시 1건
3. **ASK_USER**: AskUserQuestion 호출 → 봇이 옵션 텍스트 푸시 1건
4. **TOOL_ERROR**: "python -c 'import nx' 실행해" → 봇이 ⚠️ 도구 실패 + stderr 푸시

각 케이스마다 `~/Projects/claude-captain-hook/dumps/<date>.p1_decisions.jsonl` 라인 추가 확인.

## 5. 운영본 교체 + 봇 재시작 명령

```bash
# 백업
cp /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py.bak.p1.$(date +%Y%m%d)

# captain.py 복제 + sdk_integration.py 패치 (위 §2 변경 박은 work/sdk_integration.py)
cp ~/Projects/claude-captain-hook/src/captain.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/captain.py
cp ~/Projects/claude-captain-hook/work/sdk_integration.py \
   /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py

# orchestrator.py 패치 (위 §3) — 별도 work/orchestrator.py로 박은 후 cp
# (이 작업은 다음 세션에서 진행 — orchestrator는 본 세션 미수정)

# 봇 PID 확인
ps -ef | grep claude-telegram-bot | grep -v grep

# kill (현재 PID 68472)
kill <PID>

# 재시작
cd /Volumes/AIDRIVE/claude-code-telegram && nohup poetry run make run > /tmp/bot.log 2>&1 &

# 헬스체크
sleep 30 && tail -50 /tmp/bot.log | grep -iE "error|exception" | head -5
```

## 6. 롤백

```bash
cp /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py.bak.p1.<date> \
   /Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py
rm /Volumes/AIDRIVE/claude-code-telegram/src/captain.py
kill <new_PID>
cd /Volumes/AIDRIVE/claude-code-telegram && nohup poetry run make run > /tmp/bot.log 2>&1 &
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

"""Mock test — orchestrator _on_stream captain 분기 통합 검증.

End-to-end flow 시뮬레이션:
  raw_data → captain.update + classify → silent/ask decide → StreamUpdate →
  on_stream 시뮬레이터 → mock progress_msg.reply_text

7건 fixture (captain P1 unit test와 동일 입력) → reply_text 호출·내용 검증.

Run: python3 tests/test_orchestrator_patch.py
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from captain import (  # noqa: E402
    TurnEnd,
    TurnState,
    ask_user_forwarding_decide,
    classify,
    silent_detector_decide,
)


# ============================================================
# Mocks (orchestrator + StreamUpdate dataclass 흉내)
# ============================================================
@dataclass
class StreamUpdate:
    """sdk_integration.py StreamUpdate 흉내 (의존성 회피)."""

    type: str
    content: Optional[str] = None
    metadata: Optional[dict] = field(default_factory=dict)


class MockProgressMsg:
    def __init__(self) -> None:
        self.replies: list = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append((text, kwargs))


# work/orchestrator.py:749 _on_stream의 captain 분기 부분만 추출
async def on_stream_simulator(update_obj: StreamUpdate, progress_msg: MockProgressMsg) -> bool:
    """Returns True if captain branch fired (return), False if fell through."""
    if update_obj.type == "captain_silent_push":
        await progress_msg.reply_text(update_obj.content or "", parse_mode="Markdown")
        return True
    if update_obj.type == "captain_ask_user":
        await progress_msg.reply_text(update_obj.content or "", parse_mode="Markdown")
        return True
    return False


# sdk_integration.py raw_data loop의 captain 호출 부분 흉내
async def sdk_loop_simulator(events: list, progress_msg: MockProgressMsg, text_response_count: int = 0):
    state = TurnState()
    state.text_response_count = text_response_count
    classification = TurnEnd.TURN_PROGRESS
    for raw in events:
        state.update(raw)
        cls = classify(raw, state)
        if cls != TurnEnd.TURN_PROGRESS:
            classification = cls
            silent = silent_detector_decide(state, cls)
            ask = ask_user_forwarding_decide(state, cls)
            if silent:
                upd = StreamUpdate(type="captain_silent_push", content=silent.get("text"))
                await on_stream_simulator(upd, progress_msg)
                state.text_response_count += 1
            if ask:
                upd = StreamUpdate(type="captain_ask_user", content=ask.get("text"))
                await on_stream_simulator(upd, progress_msg)
                state.text_response_count += 1
    return state, classification


# ============================================================
# Fixtures (captain P1 unit test와 동일)
# ============================================================
def fx_assistant_tool_use(name, input_):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "x", "name": name, "input": input_}]}, "session_id": "s"}


def fx_assistant_text(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}, "session_id": "s"}


def fx_user_tool_result(content, is_error=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "x", "content": content, "is_error": is_error}]}, "session_id": "s"}


def fx_message_delta(stop_reason):
    return {"type": "stream_event", "event": {"type": "message_delta", "delta": {"stop_reason": stop_reason}}, "session_id": "s"}


def fx_result(stop_reason="end_turn", is_error=False):
    return {"type": "result", "stop_reason": stop_reason, "terminal_reason": "completed", "is_error": is_error, "session_id": "s"}


# ============================================================
# Tests
# ============================================================
async def main():
    print("=== orchestrator _on_stream captain 분기 통합 mock test ===\n")
    fails = 0

    async def run(label, events, expect_replies, expect_marker=None, text_response_count=0):
        nonlocal fails
        msg = MockProgressMsg()
        try:
            state, cls = await sdk_loop_simulator(events, msg, text_response_count)
        except Exception as e:
            print(f"  [RAISED] {label}: {e}")
            fails += 1
            return
        ok_count = len(msg.replies) == expect_replies
        ok_marker = expect_marker is None or (msg.replies and expect_marker in msg.replies[0][0])
        flag = "[OK]" if (ok_count and ok_marker) else "[FAIL]"
        print(f"  {flag} {label}: replies={len(msg.replies)} (expect {expect_replies}), cls={cls.value}")
        if msg.replies:
            print(f"       reply[0][:80]: {msg.replies[0][0][:80]}")
        if not (ok_count and ok_marker):
            fails += 1

    # 1. NORMAL — push 0
    await run("1) NORMAL", [
        fx_assistant_text("hi"), fx_message_delta("end_turn"), fx_result("end_turn"),
    ], expect_replies=0)

    # 2. SILENT — push 1, 도구 마커
    await run("2) SILENT", [
        fx_assistant_tool_use("Bash", {"command": "ls /tmp"}),
        fx_message_delta("tool_use"), fx_result("end_turn"),
    ], expect_replies=1, expect_marker="조용한 종료")

    # 3. ASK_USER — push 1, options 마커
    await run("3) ASK_USER", [
        fx_assistant_tool_use("AskUserQuestion", {
            "questions": [{"question": "A or B?", "header": "Pick",
                "options": [{"label": "A", "description": "first"}, {"label": "B", "description": "second"}]}]}),
        fx_message_delta("tool_use"), fx_result("end_turn"),
    ], expect_replies=1, expect_marker="A or B?")

    # 4. TOOL_ERROR — push 1, ⚠️ 마커 + stderr tail
    await run("4) TOOL_ERROR", [
        fx_assistant_tool_use("Bash", {"command": "python -c 'import nx'"}),
        fx_message_delta("tool_use"),
        fx_user_tool_result("Exit code 1\nModuleNotFoundError: No module named 'nx'", is_error=True),
        fx_result("end_turn"),
    ], expect_replies=1, expect_marker="도구 실패")

    # 5. API_ERROR — R12: push 1 (사용자에 turn 강제 종료 알림)
    await run("5) API_ERROR (R12)", [
        fx_assistant_text("trying..."), fx_message_delta("end_turn"),
        fx_result("end_turn", is_error=True),
    ], expect_replies=1, expect_marker="비정상 종료")

    # 6. SILENT skip — 기본 가드
    await run("6) SILENT skip (guard)", [
        fx_assistant_tool_use("Bash", {"command": "ls"}),
        fx_message_delta("tool_use"), fx_result("end_turn"),
    ], expect_replies=0, text_response_count=1)

    # 7. None 입력 — 예외 0, push 0
    msg7 = MockProgressMsg()
    state7 = TurnState()
    try:
        state7.update(None)
        cls7 = classify(None, state7)
        if cls7 != TurnEnd.TURN_PROGRESS:
            fails += 1
            print("  [FAIL] 7) None: classify should return PROGRESS")
        else:
            print(f"  [OK] 7) None input: cls={cls7.value}, replies=0")
    except Exception as e:
        fails += 1
        print(f"  [RAISED] 7) None: {e}")

    print(f"\n{'='*40}")
    if fails == 0:
        print("[PASS] All 7 cases OK")
        return 0
    else:
        print(f"[FAIL] {fails} assertion(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""Captain Hook P1 unit tests — standalone, no SDK deps.

각 분기 1건씩 mock raw_data fixture로 검증:
1. TURN_END_NORMAL
2. TURN_END_SILENT (5번 silent_detector 푸시)
3. TURN_END_ASK_USER (2번 ask_user_forwarding 푸시)
4. TURN_END_TOOL_ERROR (4번 silent_detector 푸시 + stderr tail)
5. TURN_END_API_ERROR (4' 푸시 X — silent_detector 대상 아님)
6. silent skip (글쓴이 가드: text_response_count > 0)

Run: python3 tests/test_captain.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from captain import (  # noqa: E402
    TurnEnd,
    TurnState,
    ask_user_forwarding_decide,
    classify,
    log_decision,
    silent_detector_decide,
)


# ============================================================
# Fixtures — minimal raw_data dicts for each branch
# ============================================================
def fx_assistant_tool_use(tool_name: str, tool_input: dict) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_x", "name": tool_name, "input": tool_input}
            ],
        },
        "session_id": "sess-test",
    }


def fx_assistant_text(text: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
        "session_id": "sess-test",
    }


def fx_user_tool_result(content: str, is_error: bool = False) -> dict:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_x",
                    "content": content,
                    "is_error": is_error,
                }
            ],
        },
        "session_id": "sess-test",
    }


def fx_message_delta(stop_reason: str) -> dict:
    return {
        "type": "stream_event",
        "event": {"type": "message_delta", "delta": {"stop_reason": stop_reason}},
        "session_id": "sess-test",
    }


def fx_result(stop_reason: str = "end_turn", is_error: bool = False) -> dict:
    return {
        "type": "result",
        "stop_reason": stop_reason,
        "terminal_reason": "completed",
        "is_error": is_error,
        "api_error_status": None,
        "result": "ok",
        "session_id": "sess-test",
    }


# ============================================================
# Tests
# ============================================================
def run_branch(label: str, events: list, expect: TurnEnd, text_response_count: int = 0):
    state = TurnState()
    state.text_response_count = text_response_count
    classification = TurnEnd.TURN_PROGRESS
    for ev in events:
        state.update(ev)
        classification = classify(ev, state)
    silent = silent_detector_decide(state, classification)
    auq = ask_user_forwarding_decide(state, classification)
    log_decision(state, classification, silent, auq)
    ok = classification == expect
    flag = "[OK]" if ok else f"[FAIL expected {expect}]"
    print(f"  {flag} {label}: got {classification.value}")
    if silent:
        print(f"       silent push: {silent['text'][:80]}...")
    if auq:
        print(f"       ask_user push: {auq['text'][:80]}...")
    return ok, state, classification, silent, auq


def main() -> int:
    print("=== Captain Hook P1 unit tests ===\n")
    fails = 0

    # 1) NORMAL — 일반 텍스트 응답 + end_turn
    ok, *_ = run_branch(
        "1) NORMAL",
        [
            fx_assistant_text("hi"),
            fx_message_delta("end_turn"),
            fx_result("end_turn"),
        ],
        TurnEnd.TURN_END_NORMAL,
    )
    if not ok:
        fails += 1

    # 2) SILENT — Bash 도구 후 응답 0 + tool_use stop
    ok, _, _, silent, _ = run_branch(
        "2) SILENT",
        [
            fx_assistant_tool_use("Bash", {"command": "ls /tmp"}),
            fx_message_delta("tool_use"),
            fx_result("end_turn"),  # tool_use 후 turn 종료 (silent)
        ],
        TurnEnd.TURN_END_SILENT,
    )
    if not ok:
        fails += 1
    if not silent:
        print("       [FAIL] silent payload missing")
        fails += 1

    # 3) ASK_USER — AskUserQuestion 호출
    ok, _, _, _, auq = run_branch(
        "3) ASK_USER",
        [
            fx_assistant_tool_use(
                "AskUserQuestion",
                {
                    "questions": [
                        {
                            "question": "A or B?",
                            "header": "Pick",
                            "options": [
                                {"label": "A", "description": "first"},
                                {"label": "B", "description": "second"},
                            ],
                        }
                    ]
                },
            ),
            fx_message_delta("tool_use"),
            fx_result("end_turn"),
        ],
        TurnEnd.TURN_END_ASK_USER,
    )
    if not ok:
        fails += 1
    if not auq:
        print("       [FAIL] ask_user payload missing")
        fails += 1

    # 4) TOOL_ERROR — Bash 호출 + tool_result is_error true
    ok, _, _, silent, _ = run_branch(
        "4) TOOL_ERROR",
        [
            fx_assistant_tool_use("Bash", {"command": "python -c 'import nx'"}),
            fx_message_delta("tool_use"),
            fx_user_tool_result("Exit code 1\nModuleNotFoundError: No module named 'nx'", is_error=True),
            fx_result("end_turn"),
        ],
        TurnEnd.TURN_END_TOOL_ERROR,
    )
    if not ok:
        fails += 1
    if not silent or "도구 실패" not in silent.get("text", ""):
        print("       [FAIL] tool_error silent payload missing or wrong format")
        fails += 1

    # 5) API_ERROR — result.is_error true
    ok, _, _, silent, _ = run_branch(
        "5) API_ERROR",
        [
            fx_assistant_text("trying..."),
            fx_message_delta("end_turn"),
            fx_result("end_turn", is_error=True),
        ],
        TurnEnd.TURN_END_API_ERROR,
    )
    if not ok:
        fails += 1
    # silent_detector는 API_ERROR 대상 X
    if silent is not None:
        print("       [FAIL] silent should be None for API_ERROR")
        fails += 1

    # 6) SILENT skip — 글쓴이 가드 (text_response_count > 0)
    ok, _, _, silent, _ = run_branch(
        "6) SILENT skip (guard)",
        [
            fx_assistant_tool_use("Bash", {"command": "ls"}),
            fx_message_delta("tool_use"),
            fx_result("end_turn"),
        ],
        TurnEnd.TURN_END_SILENT,
        text_response_count=1,
    )
    if not ok:
        fails += 1
    if silent is not None:
        print("       [FAIL] silent guard didn't skip")
        fails += 1

    # 7) Fail-safe — None 입력
    state = TurnState()
    state.update(None)  # should not raise
    cls = classify(None, state)
    if cls != TurnEnd.TURN_PROGRESS:
        print("       [FAIL] None input didn't return PROGRESS")
        fails += 1
    else:
        print("  [OK] 7) Fail-safe: None input handled gracefully")

    print(f"\n{'='*40}")
    if fails == 0:
        print(f"[PASS] All branches OK")
        return 0
    else:
        print(f"[FAIL] {fails} assertion(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

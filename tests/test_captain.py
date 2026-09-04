"""Captain Hook P1 unit tests — standalone, no SDK deps.

각 분기 1건씩 mock raw_data fixture로 검증:
1. TURN_END_NORMAL
2. TURN_END_SILENT (5번 silent_detector 푸시)
3. TURN_END_ASK_USER (2번 ask_user_forwarding 푸시)
4. TURN_END_TOOL_ERROR (4번 silent_detector 푸시 + stderr tail)
5. TURN_END_API_ERROR (4' 푸시 X — silent_detector 대상 아님)
6. silent skip (기본 가드: text_response_count > 0)

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

    # 5) API_ERROR — result.is_error true. R12: silent_detector도 푸시해야 함
    ok, _, _, silent, _ = run_branch(
        "5) API_ERROR (R12)",
        [
            fx_assistant_text("trying..."),
            fx_message_delta("end_turn"),
            fx_result("end_turn", is_error=True),
        ],
        TurnEnd.TURN_END_API_ERROR,
    )
    if not ok:
        fails += 1
    # R12: API_ERROR도 푸시 (silent != None)
    if silent is None or "비정상 종료" not in silent.get("text", ""):
        print("       [FAIL] API_ERROR push missing (R12 regression)")
        fails += 1

    # 6) SILENT skip — 기본 가드 (text_response_count > 0)
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

    # 8) TOOL_ERROR 누적 — 의도 도구 실패 + 후속 분석 도구 정상 → TOOL_ERROR
    ok, _, _, silent, _ = run_branch(
        "8) TOOL_ERROR 누적 (실측 회귀)",
        [
            fx_assistant_tool_use("Bash", {"command": "python -c 'import nx'"}),
            fx_user_tool_result("Exit code 1\nModuleNotFoundError", is_error=True),
            # 후속 분석 도구 (captain-hook 경로 박힘 → self-noise)
            fx_assistant_tool_use("Bash", {"command": "tail -3 ~/Projects/claude-captain-hook/dumps/x.jsonl"}),
            fx_user_tool_result("ok", is_error=False),
            fx_message_delta("end_turn"),
            fx_result("end_turn"),
        ],
        TurnEnd.TURN_END_TOOL_ERROR,
    )
    if not ok:
        fails += 1
    if not silent or "도구 실패" not in silent.get("text", ""):
        print("       [FAIL] cumulative tool_error didn't survive overwrite")
        fails += 1

    # 9) ASK_USER 보존 — AskUserQuestion + 후속 분석 → ASK_USER
    ok, _, _, _, auq = run_branch(
        "9) ASK_USER 보존 (실측 회귀)",
        [
            fx_assistant_tool_use("AskUserQuestion", {
                "questions": [{"question": "X?", "header": "Pick",
                    "options": [{"label": "A", "description": "a"}, {"label": "B", "description": "b"}]}]}),
            # 후속 self-noise 분석
            fx_assistant_tool_use("Bash", {"command": "jq -c '.raw' ~/Projects/claude-captain-hook/dumps/x.jsonl"}),
            fx_user_tool_result("ok"),
            fx_message_delta("end_turn"),
            fx_result("end_turn"),
        ],
        TurnEnd.TURN_END_ASK_USER,
    )
    if not ok:
        fails += 1
    if not auq:
        print("       [FAIL] ask_user didn't survive overwrite")
        fails += 1

    # 10) SILENT direct 필터 — nohup sleep + 후속 분석 (self-noise) → SILENT
    ok, _, _, silent, _ = run_branch(
        "10) SILENT direct 필터 (실측 회귀)",
        [
            fx_assistant_tool_use("Bash", {"command": "nohup sleep 60 &", "run_in_background": True}),
            fx_message_delta("tool_use"),
            # 후속 self-noise 분석 — last_meaningful_stop_reason은 tool_use 유지되어야
            fx_assistant_tool_use("Bash", {"command": "tail -1 ~/Projects/claude-captain-hook/dumps/p1_decisions.jsonl"}),
            fx_user_tool_result("ok"),
            fx_message_delta("end_turn"),
            fx_result("end_turn"),
        ],
        TurnEnd.TURN_END_SILENT,
    )
    if not ok:
        fails += 1
    if not silent or "조용한 종료" not in silent.get("text", ""):
        print("       [FAIL] silent payload missing")
        fails += 1
    # last_user_tool은 self-noise 필터로 nohup sleep이어야 (jq 분석 X)
    # silent 텍스트에서 확인
    if silent and "nohup sleep" not in silent.get("text", ""):
        print(f"       [FAIL] last_user_tool was overwritten: {silent.get('text','')[:100]}")
        fails += 1

    # 11) P1.6 self-noise 가드: stop_reason=tool_use 누적 + 모든 도구가 noise path
    ok, _, _, silent, _ = run_branch(
        "11) P1.6 self-noise 가드",
        [
            # 모든 도구가 self-noise path (captain-hook|/dumps/) → last_user_tool_name 갱신 X
            fx_assistant_tool_use("Bash", {"command": "tail ~/Projects/claude-captain-hook/dumps/x.jsonl"}),
            fx_message_delta("tool_use"),
            fx_user_tool_result("ok"),
            fx_assistant_tool_use("Bash", {"command": "jq '.cls' ~/Projects/claude-captain-hook/dumps/y.jsonl"}),
            fx_user_tool_result("ok"),
            fx_message_delta("end_turn"),
            fx_result("end_turn"),
        ],
        TurnEnd.TURN_END_SILENT,
    )
    if not ok:
        fails += 1
    if silent is not None:
        print("       [FAIL] P1.6 가드 미작동: silent push 발생 (last_user_tool=null인데 push)")
        fails += 1

    # 13) Idle (6번) — 도구 0개 + 텍스트 1건 + end_turn → NORMAL (1번과 동일)
    ok, _, _, silent, _ = run_branch(
        "13) Idle (6번 = 1번 통합)",
        [
            fx_assistant_text("정보 제공만 하고 도구 호출 없이 종료"),
            fx_message_delta("end_turn"),
            fx_result("end_turn"),
        ],
        TurnEnd.TURN_END_NORMAL,
    )
    if not ok:
        fails += 1
    if silent is not None:
        print("       [FAIL] Idle case unexpectedly produced push")
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

    # ── 2026-09-04: 감시자 자신의 고장 (P1.7) ──────────────────────
    # 옛 판은 분류기가 터지면 TURN_PROGRESS(=알림 없음), 감시자가 터지면
    # None(=푸시 없음)을 돌려줬다. **조용한 종료를 잡는 도구가 자기 고장에는
    # 조용한** 구조였다. 미성립은 정상이 아니다 — 시끄러워야 한다.
    class _Boom(dict):
        def get(self, *a, **k):
            raise RuntimeError("판정 불가")

    st = TurnState()
    got = classify(_Boom(), st)
    ok = got == TurnEnd.TURN_CLASSIFY_FAILED
    fails += 0 if ok else 1
    print(f"  {'✅' if ok else '❌'} 분류기 고장 → CLASSIFY_FAILED: got {got.value}")

    push = silent_detector_decide(st, got)
    ok = bool(push) and push.get("level") == "error"
    fails += 0 if ok else 1
    print(f"  {'✅' if ok else '❌'} 분류 실패는 error 로 푸시된다: {bool(push)}")

    st2 = TurnState(last_user_tool_name="Bash", last_meaningful_stop_reason="tool_use")
    st2.last_user_tool_input = {"x": object()}      # json.dumps 가 터진다
    push2 = silent_detector_decide(st2, TurnEnd.TURN_END_SILENT)
    ok = bool(push2) and push2.get("level") == "error"
    fails += 0 if ok else 1
    print(f"  {'✅' if ok else '❌'} 감시자 고장도 침묵하지 않는다: {bool(push2)}")

    print(f"\n{'='*40}")
    if fails == 0:
        print(f"[PASS] All branches OK")
        return 0
    else:
        print(f"[FAIL] {fails} assertion(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

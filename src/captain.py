"""Captain Hook — P1 모듈 (v2: any-pattern 누적 기반)

분류·결정 로직만 보유 (텔레그램 송신은 sdk_integration.py에서 처리).
의존성 0. 모든 함수 fail-safe (raise 금지, stderr 로그만).

v2 변경 — 라이브 검증 4건 결과 반영 (2026-04-26):
- 마지막 값 overwrite → any 누적 패턴
  · any_tool_error: 한 번이라도 tool_result.is_error=true 발견 시 True 유지
  · any_ask_user_question: tool_use.name="AskUserQuestion" 발견 시 True
  · last_meaningful_stop_reason: stop_reason="tool_use" 발견하면 보존,
    이후 "end_turn"으로 덮이지 않음
- self-noise 회피: caller.type="direct"인 도구만 last_user_* 갱신 (선택)

3종 모듈:
1. classify(raw_data, state) → TurnEnd enum
2. silent_detector_decide(state) → push_payload or None
3. ask_user_forwarding_decide(state) → push_payload or None
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional


# ============================================================
# Enum
# ============================================================
class TurnEnd(Enum):
    TURN_END_API_ERROR = "api_error"        # result.is_error == true
    TURN_END_TOOL_ERROR = "tool_error"      # any_tool_error == true
    TURN_END_ASK_USER = "ask_user"          # any_ask_user_question == true
    TURN_END_SILENT = "silent"              # last_meaningful_stop_reason == "tool_use"
    TURN_END_NORMAL = "normal"
    TURN_PROGRESS = "progress"
    # 2026-09-04 신설 — **분류기 자신이 터진 상태**. 옛 판은 이때 TURN_PROGRESS
    # (아직 진행 중)를 돌려줬는데, 그건 「알림 없음」과 같은 뜻이라 감시자가
    # 고장나면 조용해졌다. 조용한 종료를 잡는 도구가 자기 고장에는 조용한 것이
    # 이 프로젝트가 막으려는 바로 그 형태다. 미성립은 정상이 아니다.
    TURN_CLASSIFY_FAILED = "classify_failed"


# ============================================================
# State (any-pattern)
# ============================================================
# Self-noise: captain-hook 자체 분석 호출 식별
# 2026-04-26 caller.type 실측: 모든 tool_use가 "direct" → caller로 구분 불가
# → path 필터 단독 채택. caller 검사는 future-proof로 보조 유지.
_SELF_NOISE_PATTERN = re.compile(r"captain-hook|/dumps/|_captain_dump_raw|p1_decisions")


def _is_user_intent_tool(block: dict) -> bool:
    """도구 호출이 사용자 의도인지 (self-noise가 아닌지) 판정.

    1차: caller.type 검사 (현재 모두 "direct"라 무력, future-proof)
    2차: input 안 self-noise 경로 필터 (메인 신호)
    """
    # 1차 — caller 신호 (SDK가 분리 분류 시작하면 활용)
    caller = block.get("caller") or {}
    ct = caller.get("type")
    if ct and ct != "direct":
        return False
    # 2차 — input path 필터
    input_str = json.dumps(block.get("input") or {}, ensure_ascii=False, default=str)
    if _SELF_NOISE_PATTERN.search(input_str):
        return False
    return True


@dataclass
class TurnState:
    """Turn 단위 누적 state. 마지막 값 overwrite 대신 any 패턴."""

    session_id: Optional[str] = None
    text_response_count: int = 0

    # 누적 신호 (한 번 True면 유지)
    any_tool_error: bool = False
    any_ask_user_question: bool = False

    # stop_reason: tool_use가 한 번이라도 보이면 보존, end_turn으로 덮이지 않음
    last_meaningful_stop_reason: Optional[str] = None

    # turn level result 신호
    api_error: bool = False

    # push payload 구성용 — 가장 최근 의미 있는 도구
    last_user_tool_name: Optional[str] = None       # self-noise 제외 도구
    last_user_tool_input: Optional[dict] = None
    failed_tool_name: Optional[str] = None          # 첫 실패 도구
    failed_tool_content: Optional[str] = None       # 첫 실패 결과 (stderr tail)
    ask_user_input: Optional[dict] = None           # AskUserQuestion input
    classify_error: Optional[str] = None            # 분류기 자신이 터진 사유 (2026-09-04)

    # 텍스트 응답 흔적
    has_text_block: bool = False

    def update(self, raw_data: Any) -> None:
        """raw_data 1건 보고 state 갱신. fail-safe + any-pattern 누적."""
        try:
            if not isinstance(raw_data, dict):
                return
            t = raw_data.get("type")
            sid = raw_data.get("session_id")
            if sid:
                self.session_id = sid

            # 1) assistant — tool_use·text 추출
            if t == "assistant":
                msg = raw_data.get("message") or {}
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "tool_use":
                        name = block.get("name") or ""
                        binput = block.get("input") or {}
                        # AskUserQuestion 누적
                        if name == "AskUserQuestion":
                            self.any_ask_user_question = True
                            self.ask_user_input = binput
                        # self-noise 필터: caller + path 통합 (위 _is_user_intent_tool)
                        if _is_user_intent_tool(block):
                            self.last_user_tool_name = name
                            self.last_user_tool_input = binput
                    elif btype == "text":
                        self.has_text_block = True

            # 2) user — tool_result is_error 누적
            elif t == "user":
                msg = raw_data.get("message") or {}
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result":
                        if bool(block.get("is_error", False)):
                            self.any_tool_error = True
                            # 첫 실패만 보존 (덮어쓰기 X)
                            if self.failed_tool_name is None:
                                self.failed_tool_name = (
                                    self.last_user_tool_name or "unknown"
                                )
                                c = block.get("content")
                                if isinstance(c, str):
                                    self.failed_tool_content = c
                                elif isinstance(c, list):
                                    self.failed_tool_content = json.dumps(
                                        c, ensure_ascii=False
                                    )[:2000]

            # 3) stream_event — message_delta.stop_reason 누적
            elif t == "stream_event":
                evt = raw_data.get("event") or {}
                if evt.get("type") == "message_delta":
                    delta = evt.get("delta") or {}
                    sr = delta.get("stop_reason")
                    # tool_use는 한 번이라도 보이면 보존, end_turn은 첫 값만
                    if sr == "tool_use":
                        self.last_meaningful_stop_reason = "tool_use"
                    elif sr and self.last_meaningful_stop_reason != "tool_use":
                        self.last_meaningful_stop_reason = sr

            # 4) result — turn level error
            elif t == "result":
                if raw_data.get("is_error") is True:
                    self.api_error = True
                if raw_data.get("api_error_status"):
                    self.api_error = True
        except Exception as e:
            print(f"[captain-hook P1] state update skipped: {e}", file=sys.stderr)


# ============================================================
# Classifier
# ============================================================
def classify(raw_data: Any, state: TurnState) -> TurnEnd:
    """raw_data 1건 + 누적 state 보고 turn 분류 반환.

    우선순위 (any 패턴):
      API_ERROR > TOOL_ERROR > ASK_USER > SILENT > NORMAL > PROGRESS
    """
    try:
        if not isinstance(raw_data, dict):
            return TurnEnd.TURN_PROGRESS
        t = raw_data.get("type")

        # turn 종료 신호 = result 이벤트
        if t == "result":
            if raw_data.get("is_error") is True or raw_data.get("api_error_status"):
                return TurnEnd.TURN_END_API_ERROR
            if state.any_tool_error:
                return TurnEnd.TURN_END_TOOL_ERROR
            if state.any_ask_user_question:
                return TurnEnd.TURN_END_ASK_USER
            if state.last_meaningful_stop_reason == "tool_use":
                return TurnEnd.TURN_END_SILENT
            return TurnEnd.TURN_END_NORMAL

        return TurnEnd.TURN_PROGRESS
    except Exception as e:
        # stderr 는 훅 실행 환경에서 아무도 안 본다. 분류 실패는 **푸시로** 나간다.
        print(f"[captain-hook P1] classify failed: {e}", file=sys.stderr, flush=True)
        state.classify_error = f"{type(e).__name__}: {e}"[:300]
        return TurnEnd.TURN_CLASSIFY_FAILED


# ============================================================
# Silent Detector
# ============================================================
def silent_detector_decide(state: TurnState, classification: TurnEnd) -> Optional[dict]:
    """SILENT/TOOL_ERROR/API_ERROR 시 강제 푸시 payload.

    R12 (2026-04-26): API_ERROR도 푸시 — 사용자에게 turn 강제 종료 알림 필수.
    봇 본체가 자체 통보 안 하면 사용자가 모름 (실측 1건 발생).
    """
    try:
        if classification == TurnEnd.TURN_CLASSIFY_FAILED:
            # 분류를 못 했다 = 이 turn 이 정상이었는지 **모른다**. 모르는 것을
            # 조용히 넘기지 않는다(2026-09-04).
            why = getattr(state, "classify_error", "") or "사유 미상"
            return {
                "text": f"🛑 captain-hook 분류 실패 — 이 turn 의 정상 여부를 판정하지 못했다.\n```\n{why}\n```",
                "level": "error",
            }
        if classification == TurnEnd.TURN_END_API_ERROR:
            # API_ERROR는 기본 가드 무시 — turn 자체가 강제 종료라 알림 필수
            return {
                "text": "🛑 Claude turn 비정상 종료 — API/SDK 에러. 응답 누락 가능. 마지막 도구 호출이 잘렸을 수 있음.",
                "level": "error",
            }
        if classification not in (TurnEnd.TURN_END_SILENT, TurnEnd.TURN_END_TOOL_ERROR):
            return None
        if state.text_response_count > 0:
            return None  # 기본 가드
        # P1.6 self-noise 가드: SILENT인데 사용자 의도 도구 0건이면 = captain 자체 분석 turn → push X
        if classification == TurnEnd.TURN_END_SILENT and not state.last_user_tool_name:
            return None

        if classification == TurnEnd.TURN_END_TOOL_ERROR:
            tool = state.failed_tool_name or "unknown"
            stderr_tail = (state.failed_tool_content or "")[-1500:]
            return {
                "text": f"⚠️ 도구 실패 — `{tool}`\n```\n{stderr_tail}\n```",
                "level": "warn",
            }
        else:  # SILENT
            tool = state.last_user_tool_name or "unknown"
            input_summary = ""
            if isinstance(state.last_user_tool_input, dict):
                if "command" in state.last_user_tool_input:
                    input_summary = str(state.last_user_tool_input["command"])[:300]
                else:
                    input_summary = json.dumps(
                        state.last_user_tool_input, ensure_ascii=False
                    )[:300]
            return {
                "text": f"🔔 조용한 종료 — 마지막 도구: `{tool}`\n```\n{input_summary}\n```",
                "level": "info",
            }
    except Exception as e:
        # 옛 판은 여기서 None(=푸시 안 함)을 돌려줬다. **감시자의 고장이 가장
        # 조용한 실패가 되는** 구조였다. 감시자가 죽으면 시끄러워야 한다.
        print(f"[captain-hook P1] silent_detector failed: {e}", file=sys.stderr)
        return {
            "text": f"🛑 captain-hook 감시자 오류 — 이 turn 을 감시하지 못했다.\n```\n{type(e).__name__}: {e}\n```"[:900],
            "level": "error",
        }


# ============================================================
# AskUserQuestion Forwarding
# ============================================================
def ask_user_forwarding_decide(state: TurnState, classification: TurnEnd) -> Optional[dict]:
    try:
        if classification != TurnEnd.TURN_END_ASK_USER:
            return None
        inp = state.ask_user_input or {}
        questions = inp.get("questions") or []
        if not questions:
            return None
        q = questions[0]
        question_text = q.get("question") or "(질문 없음)"
        options = q.get("options") or []
        # P1.7-ext (R15): Markdown 강조 포기 — plain text로 ✓ 100% push 보장
        # 옵션 description에 unescaped *, _ 들어가면 entity 미종료 BadRequest 유발
        opts_text = "\n".join(
            f"{i+1}. {o.get('label','?')}: {o.get('description','')}"
            for i, o in enumerate(options)
        )
        text = f"❓ {question_text}\n\n{opts_text}\n\n번호 또는 자유 텍스트로 답해주세요."
        return {
            "text": text,
            "options": options,
            "question": question_text,
            "header": q.get("header"),
            "multi_select": bool(q.get("multiSelect", False)),
        }
    except Exception as e:
        print(f"[captain-hook P1] ask_user_forwarding failed: {e}", file=sys.stderr)
        return None


# ============================================================
# Decision Log
# ============================================================
_DECISION_LOG_DIR = os.path.expanduser("~/Projects/claude-captain-hook/dumps")


def log_decision(
    state: TurnState,
    classification: TurnEnd,
    silent_payload: Optional[dict],
    ask_user_payload: Optional[dict],
) -> None:
    try:
        os.makedirs(_DECISION_LOG_DIR, exist_ok=True)
        path = f"{_DECISION_LOG_DIR}/{date.today()}.p1_decisions.jsonl"
        line = json.dumps(
            {
                "ts": time.time(),
                "session_id": state.session_id,
                "classification": classification.value,
                "any_tool_error": state.any_tool_error,
                "any_ask_user_question": state.any_ask_user_question,
                "last_meaningful_stop_reason": state.last_meaningful_stop_reason,
                "last_user_tool_name": state.last_user_tool_name,
                "failed_tool_name": state.failed_tool_name,
                "text_response_count": state.text_response_count,
                "silent_pushed": silent_payload is not None,
                "ask_user_pushed": ask_user_payload is not None,
            },
            ensure_ascii=False,
        )
        with open(path, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[captain-hook P1] decision log failed: {e}", file=sys.stderr)

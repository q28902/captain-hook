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


# ============================================================
# State (any-pattern)
# ============================================================
# Self-noise: captain-hook 자체 분석 호출 식별. caller.type 또는 경로 패턴
_SELF_NOISE_PATTERN = re.compile(r"captain-hook|/dumps/|_captain_dump_raw|p1_decisions")


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
                        # self-noise 필터: 도구 input에 captain-hook 경로 박혔으면
                        # last_user_* 갱신 X (분석 호출은 사용자 의도 X)
                        input_str = json.dumps(binput, ensure_ascii=False, default=str)
                        if not _SELF_NOISE_PATTERN.search(input_str):
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
        print(f"[captain-hook P1] classify failed: {e}", file=sys.stderr)
        return TurnEnd.TURN_PROGRESS


# ============================================================
# Silent Detector
# ============================================================
def silent_detector_decide(state: TurnState, classification: TurnEnd) -> Optional[dict]:
    """SILENT 또는 TOOL_ERROR 시 강제 푸시 payload."""
    try:
        if classification not in (TurnEnd.TURN_END_SILENT, TurnEnd.TURN_END_TOOL_ERROR):
            return None
        if state.text_response_count > 0:
            return None  # 글쓴이 가드

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
        print(f"[captain-hook P1] silent_detector failed: {e}", file=sys.stderr)
        return None


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
        opts_text = "\n".join(
            f"{i+1}. *{o.get('label','?')}* — {o.get('description','')}"
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

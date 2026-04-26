"""Captain Hook — P1 모듈

분류·결정 로직만 보유 (텔레그램 송신은 sdk_integration.py에서 처리).
의존성 0. 모든 함수 fail-safe (raise 금지, stderr 로그만).

3종 모듈:
1. classify(raw_data, state) → TurnEnd enum
2. silent_detector_decide(state) → push_payload or None
3. ask_user_forwarding_decide(state) → push_payload or None

통합 지점: src/claude/sdk_integration.py 안 `async for raw_data` 루프
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional


# ============================================================
# Enum + State
# ============================================================
class TurnEnd(Enum):
    """Turn 종료 분류. 우선순위: API_ERROR > TOOL_ERROR > ASK_USER > SILENT > NORMAL > PROGRESS."""

    TURN_END_API_ERROR = "api_error"        # result.is_error == true
    TURN_END_TOOL_ERROR = "tool_error"      # 직전 user.message.content[].is_error == true
    TURN_END_ASK_USER = "ask_user"          # 마지막 tool_use.name == "AskUserQuestion"
    TURN_END_SILENT = "silent"              # message_delta.stop_reason == "tool_use" + 일반 도구
    TURN_END_NORMAL = "normal"              # end_turn + 텍스트 응답 있음
    TURN_PROGRESS = "progress"              # turn 진행 중 (stream_event/system 등)


@dataclass
class TurnState:
    """Turn 단위로 누적되는 상태. 봇이 turn 시작 시 새로 생성, raw_data마다 update."""

    session_id: Optional[str] = None
    last_tool_use_name: Optional[str] = None       # 마지막 tool_use.name
    last_tool_use_input: Optional[dict] = None     # 마지막 tool_use.input
    last_stop_reason: Optional[str] = None         # 마지막 message_delta.stop_reason
    last_tool_result_is_error: bool = False        # 직전 tool_result.is_error
    last_tool_result_content: Optional[str] = None # 직전 tool_result.content (stderr 등)
    text_response_count: int = 0                   # turn 내 봇이 텔레그램 송신한 횟수
    api_error: bool = False                        # result.is_error == true 캐치
    has_text_block: bool = False                   # assistant content[] 안 type=="text" 발견 여부

    def update(self, raw_data: Any) -> None:
        """raw_data 1건 보고 state 갱신. fail-safe."""
        try:
            if not isinstance(raw_data, dict):
                return
            t = raw_data.get("type")

            # session_id 갱신 (모든 이벤트에 박혀있음)
            sid = raw_data.get("session_id")
            if sid:
                self.session_id = sid

            # 1) assistant 메시지 — tool_use·text 추출
            if t == "assistant":
                msg = raw_data.get("message") or {}
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "tool_use":
                        self.last_tool_use_name = block.get("name")
                        self.last_tool_use_input = block.get("input")
                    elif btype == "text":
                        self.has_text_block = True

            # 2) user 메시지 안 tool_result — is_error 체크
            elif t == "user":
                msg = raw_data.get("message") or {}
                for block in msg.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result":
                        self.last_tool_result_is_error = bool(block.get("is_error", False))
                        c = block.get("content")
                        if isinstance(c, str):
                            self.last_tool_result_content = c
                        elif isinstance(c, list):
                            self.last_tool_result_content = json.dumps(c, ensure_ascii=False)[:2000]

            # 3) stream_event — message_delta.stop_reason 추출
            elif t == "stream_event":
                evt = raw_data.get("event") or {}
                if evt.get("type") == "message_delta":
                    delta = evt.get("delta") or {}
                    sr = delta.get("stop_reason")
                    if sr:
                        self.last_stop_reason = sr

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

    우선순위: API_ERROR > TOOL_ERROR > ASK_USER > SILENT > NORMAL > PROGRESS.
    오직 turn 종료 신호(result 또는 message_delta with stop_reason)일 때만
    TURN_END_* 반환. 그 외엔 TURN_PROGRESS.
    """
    try:
        if not isinstance(raw_data, dict):
            return TurnEnd.TURN_PROGRESS
        t = raw_data.get("type")

        # turn 종료 후보 — result 이벤트
        if t == "result":
            # 우선순위 1: API 에러
            if raw_data.get("is_error") is True or raw_data.get("api_error_status"):
                return TurnEnd.TURN_END_API_ERROR
            # 우선순위 2: 도구 에러 (state에 누적된 직전 tool_result.is_error)
            if state.last_tool_result_is_error:
                return TurnEnd.TURN_END_TOOL_ERROR
            # 우선순위 3: AskUserQuestion (마지막 tool_use.name)
            if state.last_tool_use_name == "AskUserQuestion":
                return TurnEnd.TURN_END_ASK_USER
            # 우선순위 4: silent (stop_reason==tool_use + 일반 도구)
            #   AskUserQuestion 이미 위에서 걸렀으니 여기는 일반 도구만
            if state.last_stop_reason == "tool_use" and state.last_tool_use_name:
                return TurnEnd.TURN_END_SILENT
            # 그 외 → 정상 종료 (텍스트 응답 있어도 없어도)
            return TurnEnd.TURN_END_NORMAL

        return TurnEnd.TURN_PROGRESS
    except Exception as e:
        print(f"[captain-hook P1] classify failed: {e}", file=sys.stderr)
        return TurnEnd.TURN_PROGRESS


# ============================================================
# Silent Detector
# ============================================================
def silent_detector_decide(state: TurnState, classification: TurnEnd) -> Optional[dict]:
    """SILENT 또는 TOOL_ERROR 시 강제 푸시 페이로드 결정.

    글쓴이 가드: 같은 turn 안에서 텔레그램 송신 1건 이상 있으면 skip.
    Returns: dict {text, level} or None
    """
    try:
        if classification not in (TurnEnd.TURN_END_SILENT, TurnEnd.TURN_END_TOOL_ERROR):
            return None
        if state.text_response_count > 0:
            return None  # 글쓴이 has_telegram_send_in_turn 가드

        tool = state.last_tool_use_name or "unknown"
        if classification == TurnEnd.TURN_END_TOOL_ERROR:
            stderr_tail = (state.last_tool_result_content or "")[-1500:]
            return {
                "text": f"⚠️ 도구 실패 — `{tool}`\n```\n{stderr_tail}\n```",
                "level": "warn",
            }
        else:  # SILENT
            input_summary = ""
            if isinstance(state.last_tool_use_input, dict):
                if "command" in state.last_tool_use_input:
                    input_summary = str(state.last_tool_use_input["command"])[:300]
                else:
                    input_summary = json.dumps(state.last_tool_use_input, ensure_ascii=False)[:300]
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
    """ASK_USER 시 텔레그램 푸시 페이로드 결정.

    inline keyboard 옵션 또는 number prefix 텍스트 fallback.
    Returns: dict {text, options: [{label, description}, ...], question_id} or None
    """
    try:
        if classification != TurnEnd.TURN_END_ASK_USER:
            return None
        inp = state.last_tool_use_input or {}
        questions = inp.get("questions") or []
        if not questions:
            return None
        q = questions[0]  # 첫 질문만 처리 (다중 질문은 향후 확장)
        question_text = q.get("question") or "(질문 없음)"
        options = q.get("options") or []

        # number prefix fallback 텍스트
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
# Decision Log (P1 자산)
# ============================================================
_DECISION_LOG_DIR = os.path.expanduser("~/Projects/claude-captain-hook/dumps")


def log_decision(
    state: TurnState,
    classification: TurnEnd,
    silent_payload: Optional[dict],
    ask_user_payload: Optional[dict],
) -> None:
    """P1 결정 로그 jsonl. P0 dump와 같은 디렉토리, 별도 파일."""
    try:
        os.makedirs(_DECISION_LOG_DIR, exist_ok=True)
        path = f"{_DECISION_LOG_DIR}/{date.today()}.p1_decisions.jsonl"
        line = json.dumps(
            {
                "ts": time.time(),
                "session_id": state.session_id,
                "classification": classification.value,
                "last_tool_use_name": state.last_tool_use_name,
                "last_stop_reason": state.last_stop_reason,
                "tool_result_is_error": state.last_tool_result_is_error,
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

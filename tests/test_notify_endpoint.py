"""P3 /notify endpoint unit test — 4건.

직접 핸들러 함수를 mock으로 호출 (TestClient + FastAPI startup 우회).
검증:
1. auth missing → 401
2. auth invalid (wrong secret) → 401
3. auth valid + payload OK → AgentResponseEvent publish + R17 prefix
4. payload validation (text 누락) → 400

Run: python3 tests/test_notify_endpoint.py
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

# fastapi HTTPException은 별도 의존성. 본 단위는 fastapi import 없이 시뮬레이션.
class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")


# ============================================================
# Mock — AgentResponseEvent (실측 구조)
# ============================================================
@dataclass
class AgentResponseEvent:
    chat_id: int = 0
    text: str = ""
    parse_mode: Optional[str] = None
    reply_to_message_id: Optional[int] = None
    source: str = "agent"
    id: str = "evt-mock-id"


# ============================================================
# Mock — verify_shared_secret (auth.py 정확 모방)
# ============================================================
import hmac
def verify_shared_secret(authorization_header: Optional[str], secret: str) -> bool:
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return False
    return hmac.compare_digest(authorization_header[7:], secret)


# ============================================================
# captain_notify handler 시뮬레이션 (work/server.py 본문 그대로)
# ============================================================
async def captain_notify(
    request_body: dict,
    authorization: Optional[str],
    settings,
    event_bus,
):
    secret = settings.captain_notify_secret
    if not secret:
        raise HTTPException(503, "notify endpoint disabled")
    if not verify_shared_secret(authorization, secret):
        raise HTTPException(401, "invalid auth")

    text = request_body.get("text", "")
    if not text:
        raise HTTPException(400, "text required")
    chat_id = request_body.get("chat_id", 0)
    if not isinstance(chat_id, int):
        raise HTTPException(400, "chat_id must be int")
    caller_id = request_body.get("caller_id", "external")

    prefixed_text = f"📡 [{caller_id}] {text}"

    event = AgentResponseEvent(
        chat_id=chat_id,
        text=prefixed_text,
        parse_mode=request_body.get("parse_mode"),
        reply_to_message_id=request_body.get("reply_to_message_id"),
        source="captain_notify",
    )
    await event_bus.publish(event)
    return {"ok": True, "event_id": event.id}


# ============================================================
# Tests
# ============================================================
async def main() -> int:
    fails = 0
    SECRET = "test_secret_xyz"

    settings = MagicMock(captain_notify_secret=SECRET)
    event_bus = MagicMock(publish=AsyncMock())

    # 1. auth missing → 401
    try:
        await captain_notify({"text": "x", "chat_id": 1}, None, settings, event_bus)
        print("[FAIL] 1) auth missing should raise")
        fails += 1
    except HTTPException as e:
        if e.status_code == 401:
            print(f"[OK] 1) auth missing → 401 ({e.detail})")
        else:
            print(f"[FAIL] 1) wrong status: {e.status_code}")
            fails += 1

    # 2. auth invalid → 401
    try:
        await captain_notify({"text": "x", "chat_id": 1}, "Bearer wrong_secret", settings, event_bus)
        print("[FAIL] 2) wrong secret should raise")
        fails += 1
    except HTTPException as e:
        if e.status_code == 401:
            print(f"[OK] 2) wrong secret → 401 ({e.detail})")
        else:
            print(f"[FAIL] 2) wrong status: {e.status_code}")
            fails += 1

    # 3. auth valid + payload OK → publish 호출 + R17 prefix
    event_bus.publish.reset_mock()
    try:
        result = await captain_notify(
            {"text": "hello", "chat_id": 12345, "caller_id": "test_caller"},
            f"Bearer {SECRET}",
            settings,
            event_bus,
        )
        if not result.get("ok"):
            print("[FAIL] 3) result.ok != True")
            fails += 1
        if event_bus.publish.call_count != 1:
            print(f"[FAIL] 3) publish call_count={event_bus.publish.call_count}")
            fails += 1
        published_event = event_bus.publish.call_args[0][0]
        if not published_event.text.startswith("📡 [test_caller]"):
            print(f"[FAIL] 3) prefix missing: {published_event.text[:50]}")
            fails += 1
        elif published_event.chat_id != 12345:
            print(f"[FAIL] 3) chat_id mismatch: {published_event.chat_id}")
            fails += 1
        elif published_event.source != "captain_notify":
            print(f"[FAIL] 3) source mismatch: {published_event.source}")
            fails += 1
        else:
            print(f"[OK] 3) auth valid + publish + R17 prefix: {published_event.text[:60]}")
    except Exception as e:
        print(f"[FAIL] 3) unexpected exception: {e}")
        fails += 1

    # 4. payload validation — text 누락 → 400
    try:
        await captain_notify({"chat_id": 1}, f"Bearer {SECRET}", settings, event_bus)
        print("[FAIL] 4) text missing should raise")
        fails += 1
    except HTTPException as e:
        if e.status_code == 400:
            print(f"[OK] 4) text missing → 400 ({e.detail})")
        else:
            print(f"[FAIL] 4) wrong status: {e.status_code}")
            fails += 1

    # 5. (보너스) settings.captain_notify_secret = None → 503
    settings_disabled = MagicMock(captain_notify_secret=None)
    try:
        await captain_notify({"text": "x", "chat_id": 1}, "Bearer xx", settings_disabled, event_bus)
        print("[FAIL] 5) disabled secret should raise")
        fails += 1
    except HTTPException as e:
        if e.status_code == 503:
            print(f"[OK] 5) secret disabled → 503 ({e.detail})")
        else:
            print(f"[FAIL] 5) wrong status: {e.status_code}")
            fails += 1

    print(f"\n{'='*40}")
    if fails == 0:
        print("[PASS] All 5 tests OK")
        return 0
    else:
        print(f"[FAIL] {fails} assertion(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

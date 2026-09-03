#!/usr/bin/env python3
"""
ScheduleWakeup watchdog daemon (P-001 옵션 A, 2026-05-07)

launchd `com.captain.wakeup-fire` plist가 60초마다 호출.
ledger jsonl 읽고 expected_fire_at <= now + grace 인 미처리 promise를
텔레그램 sendMessage로 fire + ledger에 fired event append.

ledger 위치: /Volumes/AIDRIVE/captain-hook-state/wakeup_promises.jsonl
형식: append-only jsonl. event=promise/fired/failed.

Telegram 봇: secretarybot 우선 (LAYER_PROJECT_BOT_TOKEN > SECRETARY_BOT_TOKEN > TELEGRAM_BOT_TOKEN).
Chat: LAYER_PROJECT_CHAT_ID > SECRETARY_CHAT_ID > TELEGRAM_CHAT_ID.

호출:
    python3 wakeup_watchdog.py [--grace-seconds 120]

idempotency: fired event 박힌 promise_id는 다시 발송 X.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path("/Volumes/AIDRIVE/captain-hook-state/wakeup_promises.jsonl")
ENV_FILES = [
    Path("/Volumes/AIDRIVE/claude-code-telegram/.env"),
    Path("/Users/inseyeol/Projects/claude/LAYER5/.env"),
    Path("/Users/inseyeol/Projects/claude/LAYER3/.env"),
]


def _load_env() -> None:
    """관련 .env 파일을 setdefault로 로드. shell env 우선."""
    for p in ENV_FILES:
        if not p.exists():
            continue
        try:
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass


def _send_telegram(message: str) -> tuple[bool, str]:
    _load_env()
    token = (
        os.getenv("SECRETARY_BOT_TOKEN")
        or os.getenv("LAYER_PROJECT_BOT_TOKEN")
        or os.getenv("TELEGRAM_BOT_TOKEN")
    )
    chat_id = (
        os.getenv("SECRETARY_CHAT_ID")
        or os.getenv("LAYER_PROJECT_CHAT_ID")
        or os.getenv("TELEGRAM_CHAT_ID")
    )
    if not token or not chat_id:
        return False, "no token/chat_id env"
    try:
        import urllib.request
        data = json.dumps(
            {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode("utf-8", errors="replace")
            if r.status != 200:
                return False, f"http {r.status}: {body[:200]}"
        return True, "ok"
    except Exception as e:
        return False, str(e)[:200]


def _read_ledger() -> tuple[list[dict], set[str]]:
    """promises 리스트 + 이미 fired/failed 처리된 promise_id set."""
    promises: list[dict] = []
    closed: set[str] = set()
    if not LEDGER.exists():
        return promises, closed
    try:
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = rec.get("event")
            if ev == "promise":
                promises.append(rec)
            elif ev in ("fired", "failed"):
                pid = rec.get("promise_id")
                if pid:
                    closed.add(pid)
    except Exception as e:
        sys.stderr.write(f"[watchdog] ledger read fail: {e}\n")
    return promises, closed


def _append_event(record: dict) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        sys.stderr.write(f"[watchdog] ledger append fail: {e}\n")


def _format_message(p: dict) -> str:
    fire_at = p.get("expected_fire_at", "")
    try:
        dt = datetime.fromisoformat(fire_at.replace("Z", "+00:00"))
        fire_local = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        fire_local = fire_at
    reason = p.get("reason", "") or "(no reason)"
    prompt = p.get("prompt", "") or "(no prompt)"
    if len(prompt) > 1500:
        prompt = prompt[:1500] + " …(truncated)"
    return (
        f"⏰ <b>Aki ScheduleWakeup fire</b>\n"
        f"promise_id: <code>{p.get('promise_id', '?')}</code>\n"
        f"fire_at: {fire_local}\n"
        f"reason: {reason}\n\n"
        f"<b>prompt</b>:\n<pre>{prompt}</pre>\n\n"
        f"<i>다음 응답 트리거하려면 텔레그램으로 위 prompt 또는 자유 메시지 보내주세요.</i>"
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--grace-seconds", type=int, default=0,
                   help="expected_fire_at 후 N초 grace 줘서 약간 늦은 것까지 fire")
    args = p.parse_args()

    promises, closed = _read_ledger()
    now = datetime.now(timezone.utc)
    fired = 0
    skipped = 0

    for pr in promises:
        pid = pr.get("promise_id")
        if not pid or pid in closed:
            continue
        try:
            fire_at = datetime.fromisoformat(pr["expected_fire_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if fire_at > now:
            skipped += 1
            continue  # 아직 시각 안됨

        msg = _format_message(pr)
        ok, info = _send_telegram(msg)
        if ok:
            _append_event({
                "event": "fired",
                "promise_id": pid,
                "fired_at": now.isoformat(),
            })
            fired += 1
        else:
            _append_event({
                "event": "failed",
                "promise_id": pid,
                "fired_at": now.isoformat(),
                "err": info,
            })
            sys.stderr.write(f"[watchdog] fire fail pid={pid}: {info}\n")

    sys.stdout.write(
        f"[watchdog] fired={fired} skipped={skipped} closed={len(closed)} "
        f"open_promises={len(promises) - len(closed)}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
P-002 — bot.db messages 평문 키 redact (2026-05-07 신설)

R13 사고 후 봇 시스템 프롬프트 평문 키는 환경변수로 이전했지만,
historical messages 테이블엔 prompt/response 본문에 평문 키 잔존.
6 패턴 매칭 후 placeholder로 in-place 교체.

흐름:
1. bot.db.bak.{ts} 백업
2. messages.prompt + messages.response 전수 스캔
3. 6 패턴 substring redact → placeholder
4. UPDATE atomic, 사후 검증

호출:
    python3 redact_bot_db.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB = Path("/Volumes/AIDRIVE/claude-code-telegram/data/bot.db")

# Capture group은 키 값. 6 R13 패턴 + TELEGRAM_BOT_TOKEN 보강.
PATTERNS = [
    (re.compile(r"sk-(?:ant-api|proj)-[A-Za-z0-9_\-]{20,}"), "[REDACTED:sk]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{40,}"),                  "[REDACTED:sk]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{30,}"),            "Bearer [REDACTED]"),
    (re.compile(r"AIza[A-Za-z0-9_\-]{30,}"),                  "[REDACTED:google]"),
    (re.compile(r"gho_[A-Za-z0-9]{30,}"),                     "[REDACTED:github]"),
    (re.compile(r"eyJhbG[A-Za-z0-9._\-]{30,}"),               "[REDACTED:jwt]"),
    (re.compile(r"(api[_-]?key\s*=\s*)[A-Za-z0-9_\-]{15,}", re.I), r"\1[REDACTED]"),
    (re.compile(r"(TELEGRAM_BOT_TOKEN\s*=\s*)[0-9]{8,12}:[A-Za-z0-9_\-]{30,}"), r"\1[REDACTED]"),
    (re.compile(r"\b[0-9]{9,12}:[A-Za-z0-9_\-]{34,}\b"),       "[REDACTED:bot_token]"),
]


def redact(text: str | None) -> tuple[str | None, int]:
    if not text:
        return text, 0
    total = 0
    for pat, repl in PATTERNS:
        text, n = pat.subn(repl, text)
        total += n
    return text, total


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                   help="UPDATE 안 하고 카운트만 보고")
    args = p.parse_args()

    if not DB.exists():
        print(f"❌ DB 없음: {DB}", file=sys.stderr)
        return 1

    if not args.dry_run:
        bak = DB.with_suffix(f".bak.{datetime.now().strftime('%Y%m%dT%H%M%S')}")
        shutil.copy2(DB, bak)
        print(f"✅ 백업: {bak} ({bak.stat().st_size} bytes)")

    rows_changed = 0
    total_redacts = 0
    with sqlite3.connect(DB) as c:
        cur = c.cursor()
        cur.execute("SELECT message_id, prompt, response FROM messages")
        rows = cur.fetchall()

        for mid, prompt, response in rows:
            new_p, np_ = redact(prompt)
            new_r, nr = redact(response)
            if np_ + nr == 0:
                continue
            rows_changed += 1
            total_redacts += np_ + nr
            if not args.dry_run:
                cur.execute(
                    "UPDATE messages SET prompt=?, response=? WHERE message_id=?",
                    (new_p, new_r, mid),
                )
        if not args.dry_run:
            c.commit()

    print(f"📊 changed rows: {rows_changed} / total redacts: {total_redacts}")

    # 사후 검증
    print("\n=== 사후 패턴 카운트 ===")
    with sqlite3.connect(DB) as c:
        for kw in ["sk-", "Bearer ", "AIza", "gho_", "eyJhbG", "api_key=", "TELEGRAM_BOT_TOKEN"]:
            cur = c.execute(
                "SELECT COUNT(*) FROM messages WHERE prompt LIKE ? OR response LIKE ?",
                (f"%{kw}%", f"%{kw}%"),
            )
            print(f"  {kw}: {cur.fetchone()[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

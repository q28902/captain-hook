#!/usr/bin/env python3
"""
Stop hook: enforce CLAUDE.md table-output rule.

Rule (from /Volumes/AIDRIVE/CLAUDE.md "표 출력 안전"):
  - 한글 비중이 크고 cell 폭 변동이 큰 표는 표 대신 bullet/정의 리스트로 변환할 것
  - 표 유지 조건: 모든 cell ≤ 12자 + 컬럼별 폭 균일

Detection:
  - Find markdown table blocks (line starts/ends with `|`, next line is `---` divider).
  - Compute East-Asian-width-aware visible width per cell.
  - Violation = any cell containing Korean and visible width > 12.

Race-condition handling (Stop hook fires before transcript fully flushed):
  - Poll transcript up to POLL_BUDGET_S.
  - Look for assistant entry with stop_reason="end_turn" AND uuid not in
    {prev_uuid stored in state file} → guarantees we read the JUST-FINISHED turn,
    not a stale earlier one.
  - If poll times out → silent pass (never lock user into block when we can't
    confirm a fresh entry).
  - state file = /tmp/table-guard-state.json (single key: last_uuid).

On violation:
  - Persist new uuid to state (so next fire on same uuid bails immediately).
  - Emit {"decision":"block","reason":"..."} so Claude is forced to redo.
On pass:
  - Persist new uuid; exit 0.

Defensive: any internal error → exit 0 (never block on hook bug).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import unicodedata


KOR_RE = re.compile(r"[가-힣]")
TABLE_DIVIDER_RE = re.compile(r"^\|[\s:|\-]+\|\s*$")
THRESHOLD = 12
SKIP_MARKER = "<!-- table-guard:skip -->"

STATE_FILE = "/tmp/table-guard-state.json"
POLL_BUDGET_S = 3.0
POLL_INTERVAL_S = 0.1


# --------------------------- detection ---------------------------------


def cell_width(s: str) -> int:
    """Visible width: full/wide chars = 2, ambiguous/narrow = 1."""
    w = 0
    for ch in s:
        ea = unicodedata.east_asian_width(ch)
        w += 2 if ea in ("W", "F") else 1
    return w


def has_korean(s: str) -> bool:
    return bool(KOR_RE.search(s))


def detect_violations(text: str) -> list[str]:
    violations: list[str] = []
    lines = text.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()
        if (
            stripped.startswith("|")
            and stripped.endswith("|")
            and stripped.count("|") >= 3
            and i + 1 < n
            and TABLE_DIVIDER_RE.match(lines[i + 1].strip())
        ):
            rows = [stripped]
            j = i + 2
            while j < n:
                row = lines[j].strip()
                if row.startswith("|") and row.endswith("|"):
                    rows.append(row)
                    j += 1
                else:
                    break
            max_offending = 0
            offending_cell = ""
            for row in rows:
                cells = [c.strip() for c in row.split("|")[1:-1]]
                for c in cells:
                    if has_korean(c):
                        w = cell_width(c)
                        if w > THRESHOLD and w > max_offending:
                            max_offending = w
                            offending_cell = c
            if max_offending > 0:
                violations.append(
                    f"line {i+1}: 한글 cell width {max_offending} > {THRESHOLD} "
                    f"(예: '{offending_cell[:30]}')"
                )
            i = j
            continue
        i += 1
    return violations


# --------------------------- transcript I/O ----------------------------


def _entry_text(e: dict) -> str:
    """Extract text content from an assistant entry."""
    msg = e.get("message") if isinstance(e.get("message"), dict) else e
    content = msg.get("content")
    if isinstance(content, list):
        return "\n".join(
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        )
    if isinstance(content, str):
        return content
    return ""


def find_fresh_end_turn(
    transcript_path: str, prev_uuid: str | None
) -> tuple[str, str] | None:
    """Return (uuid, text) of the LAST assistant entry where:
      - type=='assistant' and stop_reason=='end_turn'
      - has non-empty text content
      - uuid != prev_uuid

    Returns None if no such entry exists (still racing or no fresh entry yet).
    """
    last_match: tuple[str, str] | None = None
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("type") != "assistant":
                    role = (e.get("message") or {}).get("role")
                    if role != "assistant":
                        continue
                msg = e.get("message") if isinstance(e.get("message"), dict) else e
                if msg.get("stop_reason") != "end_turn":
                    continue
                text = _entry_text(e)
                if not text.strip():
                    continue
                uid = e.get("uuid") or msg.get("id")
                if not uid:
                    continue
                if uid == prev_uuid:
                    continue
                last_match = (uid, text)
    except FileNotFoundError:
        return None
    except Exception:
        return None
    return last_match


# --------------------------- state I/O ---------------------------------


def load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_state(uuid: str) -> None:
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"last_uuid": uuid, "ts": time.time()}, f)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


# --------------------------- main --------------------------------------


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        inp = json.loads(raw)
    except Exception:
        return 0

    # Belt-and-suspenders: if harness already in re-entry mode, never block.
    if inp.get("stop_hook_active") is True:
        return 0

    transcript_path = inp.get("transcript_path") or ""
    if not transcript_path:
        return 0

    state = load_state()
    prev_uuid = state.get("last_uuid")

    # Poll for a fresh end_turn entry (race against transcript flush).
    deadline = time.time() + POLL_BUDGET_S
    fresh: tuple[str, str] | None = None
    while True:
        fresh = find_fresh_end_turn(transcript_path, prev_uuid)
        if fresh:
            break
        if time.time() >= deadline:
            break
        time.sleep(POLL_INTERVAL_S)

    if not fresh:
        # Never saw a fresh entry within budget. Silent pass — refusing to
        # block when we can't confirm what we'd be blocking.
        return 0

    new_uuid, text = fresh

    # Always record the new uuid first so a re-fire on the same entry bails.
    save_state(new_uuid)

    # Explicit override.
    if SKIP_MARKER in text:
        return 0

    violations = detect_violations(text)
    if not violations:
        return 0

    reason = (
        "CLAUDE.md 표 출력 규칙 위반. "
        + "; ".join(violations[:3])
        + ". 한글 cell width 12자 초과 표는 bullet/정의 리스트로 변환 후 재출력하세요. "
        f"긴급 우회는 응답 어딘가에 '{SKIP_MARKER}' 포함."
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

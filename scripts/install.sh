#!/usr/bin/env bash
# captain-hook install — set -e 안전 + dry-run + 자동 rollback
#
# 환경변수 BOT (필수): 자기 봇 fork 로컬 경로
# 환경변수 CAPTAIN_HOOK (필수): 본 repo clone 경로
#
# 사용:
#   export BOT=/path/to/your/claude-code-telegram
#   export CAPTAIN_HOOK=~/Projects/captain-hook
#   bash $CAPTAIN_HOOK/scripts/install.sh

set -euo pipefail

# ── 환경변수 검증 ──────────────────────────────
if [ -z "${BOT:-}" ]; then
    echo "ERROR: \$BOT 환경변수 미설정. export BOT=/path/to/your/claude-code-telegram" >&2
    exit 1
fi
if [ -z "${CAPTAIN_HOOK:-}" ]; then
    echo "ERROR: \$CAPTAIN_HOOK 환경변수 미설정. export CAPTAIN_HOOK=~/Projects/captain-hook" >&2
    exit 1
fi
if [ ! -d "$BOT/src" ]; then
    echo "ERROR: \$BOT 경로에 src/ 디렉토리 없음 — 봇 fork 경로 확인" >&2
    exit 1
fi
if [ ! -f "$CAPTAIN_HOOK/src/captain.py" ]; then
    echo "ERROR: \$CAPTAIN_HOOK 경로에 src/captain.py 없음 — clone 경로 확인" >&2
    exit 1
fi

# ── 1) 백업 ───────────────────────────────────
TS=$(date +%Y%m%d-%H%M%S)
BACKUP="$BOT/.captain-bak.$TS"
mkdir -p "$BACKUP"
echo "[install] 백업 디렉토리: $BACKUP"

for f in src/claude/sdk_integration.py \
         src/bot/orchestrator.py \
         src/api/server.py \
         src/config/settings.py \
         src/config/environments.py; do
    if [ -f "$BOT/$f" ]; then
        cp "$BOT/$f" "$BACKUP/$(basename $f)"
    fi
done
echo "[install] 5개 파일 백업 완료"

# ── 2) captain.py 신규 cp ─────────────────────
cp "$CAPTAIN_HOOK/src/captain.py" "$BOT/src/captain.py"
echo "[install] captain.py 신규 cp"

# ── 3) Patch dry-run + apply (실패 시 자동 rollback) ─
APPLIED=()
ROLLBACK() {
    echo "[install] ROLLBACK 시작 — 백업 $BACKUP에서 복원"
    cp "$BACKUP"/* "$BOT/src/claude/sdk_integration.py" 2>/dev/null || true
    cp "$BACKUP/sdk_integration.py" "$BOT/src/claude/sdk_integration.py" 2>/dev/null || true
    cp "$BACKUP/orchestrator.py" "$BOT/src/bot/orchestrator.py" 2>/dev/null || true
    cp "$BACKUP/server.py" "$BOT/src/api/server.py" 2>/dev/null || true
    cp "$BACKUP/settings.py" "$BOT/src/config/settings.py" 2>/dev/null || true
    cp "$BACKUP/environments.py" "$BOT/src/config/environments.py" 2>/dev/null || true
    rm -f "$BOT/src/captain.py"
    echo "[install] ROLLBACK 완료. backup 그대로 유지: $BACKUP"
    exit 1
}

cd "$BOT"
for f in environments orchestrator sdk_integration server settings; do
    PATCH="$CAPTAIN_HOOK/patches/${f}.patch"
    if ! [ -f "$PATCH" ]; then
        echo "[install] FAIL: $PATCH 부재"
        ROLLBACK
    fi
    if ! patch --dry-run -p0 -i "$PATCH" >/dev/null 2>&1; then
        echo "[install] FAIL: ${f}.patch dry-run 실패 — 봇 SHA divergence 가능"
        echo "  → fallback: $CAPTAIN_HOOK/patches/${f}.py 풀 파일 manual merge"
        ROLLBACK
    fi
    patch -p0 -i "$PATCH"
    APPLIED+=("$f")
done
echo "[install] 5개 patch 적용 완료: ${APPLIED[*]}"

# ── 4) .env 보강 ──────────────────────────────
if ! grep -q "^ENABLE_API_SERVER=true" "$BOT/.env" 2>/dev/null; then
    echo "ENABLE_API_SERVER=true" >> "$BOT/.env"
    echo "[install] .env: ENABLE_API_SERVER=true 추가"
fi
if ! grep -q "^CAPTAIN_NOTIFY_SECRET=" "$BOT/.env" 2>/dev/null; then
    SECRET=$(openssl rand -hex 32 2>/dev/null \
             || head -c 32 /dev/urandom | xxd -p -c 32 \
             || python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "CAPTAIN_NOTIFY_SECRET=$SECRET" >> "$BOT/.env"
    echo "[install] .env: CAPTAIN_NOTIFY_SECRET 신규 (랜덤 32 hex)"
fi

# ── 5) 다음 단계 안내 ─────────────────────────
echo
echo "[install] ✅ 모든 패치 적용 완료. 다음 단계:"
echo "  1. 봇 재시작: \$CAPTAIN_HOOK/INTEGRATE.md §5 (R16 가이드 — pkill + 단일 인스턴스 검증)"
echo "  2. 라이브 검증: \$CAPTAIN_HOOK/INTEGRATE.md §4 (NORMAL/SILENT/ASK_USER/TOOL_ERROR)"
echo "  3. 백업 위치: $BACKUP"
echo "  4. 롤백: cp $BACKUP/* \$BOT/src/<해당 디렉토리>/"

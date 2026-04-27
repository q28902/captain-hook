# Captain Hook v1.0

> **claude-code-telegram 봇을 강제 100% 가시화 레이어로 진화시키는 add-on.**
> Claude의 응답 누락·백그라운드 작업 침묵·강제 종료를 외부에서 push.

**Status**: v1.0 정식 마감 (2026-04-27, 5일 안정화). 라이브 검증 통과.
**License**: [MIT](LICENSE)
**기반 봇**: [`RichardAtCT/claude-code-telegram`](https://github.com/RichardAtCT/claude-code-telegram) (fork 필요)

⚠️ **이름 충돌**: "Captain Hook" = Disney 캐릭터 + npm git-hook 패키지. 검색 노출 약함. 다른 fork에서 rename 권장.

---

## 왜 필요한가

기본 텔레그램 봇은 **사용자 → Claude 입력**만 처리. Claude가 turn 끝에 "조용히 끝나는" 4가지 패턴은 사용자에게 전달 X:

| 패턴 | 기존 봇 | Captain Hook |
|---|---|---|
| 텍스트 응답 0건 + 도구만 사용 | silent fail | 🔔 SILENT push |
| 도구 실행 실패 | 응답 없음 | ⚠️ TOOL_ERROR push + stderr tail |
| AskUserQuestion 호출 | SDK 자동 빈 응답 | ❓ 옵션 텍스트 push |
| Turn 도중 강제 종료 (rate limit/OOM/kill) | 영영 침묵 | 🛑 API_ERROR push |

추가로 외부 시스템 (n8n, CI, 다른 봇)이 같은 텔레그램 채널로 메시지 송신하는 P3 endpoint (`POST /notify` + Bearer 인증).

---

## 30초 install (unified diff apply)

**Base 봇 SHA**: `fa008b3` (`ci: add pre-commit hooks and split lint into separate CI job`).
이 SHA에 가까울수록 patch 자동 apply 성공률 높음.

**Divergence 진단** (자기 봇 fork와 base 거리 측정):
```bash
cd $BOT && git rev-list --count fa008b3..HEAD
```
0~5: 즉시 apply 가능 / 5~50: dry-run 권장 / 50+: manual merge 권장.

**Secret 생성 — 환경별 대안** (`openssl rand -hex 32` 외):
- macOS/Linux: `openssl rand -hex 32`
- alpine docker: `head -c 32 /dev/urandom | xxd -p -c 32`
- python: `python3 -c "import secrets; print(secrets.token_hex(32))"`

```bash
git clone https://github.com/q28902/captain-hook.git ~/Projects/captain-hook
BOT=/path/to/your/claude-code-telegram   # ← 자기 봇 경로로 변경

# 1) 봇 본체 백업 + captain.py 신규 cp
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BOT/.captain-bak.$TS"
cp "$BOT/src/claude/sdk_integration.py" "$BOT/.captain-bak.$TS/"
cp "$BOT/src/bot/orchestrator.py" "$BOT/.captain-bak.$TS/"
cp "$BOT/src/api/server.py" "$BOT/.captain-bak.$TS/"
cp "$BOT/src/config/settings.py" "$BOT/.captain-bak.$TS/"
cp "$BOT/src/config/environments.py" "$BOT/.captain-bak.$TS/"
cp ~/Projects/captain-hook/src/captain.py "$BOT/src/captain.py"

# 2) 5개 unified diff apply (자동)
cd "$BOT"
for f in environments orchestrator sdk_integration server settings; do
    patch --dry-run -p0 -i ~/Projects/captain-hook/patches/${f}.patch \
      && patch -p0 -i ~/Projects/captain-hook/patches/${f}.patch \
      || echo "FAIL: ${f}.patch — manual merge from patches/${f}.py"
done

# 3) .env 보강
echo "ENABLE_API_SERVER=true" >> "$BOT/.env"
echo "CAPTAIN_NOTIFY_SECRET=$(openssl rand -hex 32)" >> "$BOT/.env"

# 4) 봇 재시작은 INTEGRATE.md §5 참조 (pkill + 단일 인스턴스 검증)
```

**Patch dry-run 실패 시 fallback 3가지**:
1. `patches/{file}.py` 풀 파일 직접 cp (봇 SHA 동일 시 안전)
2. `git apply --reject` 후 `.rej` 파일 보고 manual merge
3. 핵심 captain 분기만 `INTEGRATE.md` §2~§4 참조해 코드로 추가

⚠️ **자기 봇 fork SHA**가 base `fa008b3`에서 멀수록 conflict 증가. v1.x P4에서 middleware/plugin 인터페이스 PR로 patches/ 의존 제거 계획.

---

## 봇 fork 적용 5단계

자세한 절차는 [`INTEGRATE.md`](INTEGRATE.md) 참조. 요약:

1. **백업** — 봇 5파일 (sdk_integration / orchestrator / server / settings / environments) `.bak.${TS}`
2. **patch cp** — `src/captain.py` 신규 + 5파일 교체
3. **`.env` 보강** — `ENABLE_API_SERVER=true`, `CAPTAIN_NOTIFY_SECRET=<random>`
4. **봇 재시작** — `pkill -f` + 단일 인스턴스 검증 + Conflict 0건 확인 (R16 가이드)
5. **라이브 검증 4건** — NORMAL/TOOL_ERROR/ASK_USER/SILENT 텔레그램 도착 + P3 curl 200/401×2

---

## 핵심 분기

`src/captain.py` 단일 파일, 의존성 0. 분류·결정 로직만 보유 (텔레그램 송신은 봇이 EventBus 경유).

```
TurnEnd enum:
  TURN_END_API_ERROR    →  🛑 푸시  (turn 도중 강제 종료)
  TURN_END_TOOL_ERROR   →  ⚠️ 푸시  (도구 실행 실패 + stderr tail)
  TURN_END_ASK_USER     →  ❓ 푸시  (AskUserQuestion 옵션 plain text)
  TURN_END_SILENT       →  🔔 푸시  (도구만 사용 + 응답 0)
  TURN_END_NORMAL       →  push 0  (정상 텍스트 응답)
  TURN_PROGRESS         →  push 0  (turn 진행 중)
```

분류 우선순위 = `API_ERROR > TOOL_ERROR > ASK_USER > SILENT > NORMAL > PROGRESS`.

---

## 디렉토리 구조

```
captain-hook/
├── src/captain.py           ← 본체 (의존성 0, 봇 src/captain.py로 cp)
├── patches/                 ← 봇 본체 5파일 풀 패치 (cp 또는 manual merge)
├── tests/                   ← unit test 13/13 + orchestrator mock 7/7 + notify 5/5
├── scripts/p0_check.sh      ← P0 dump 분석용 jq cookbook
├── docs/
│   ├── PROBLEM.md           ← 4종 누락 패턴 정의
│   ├── DESIGN.md            ← 3층 구조 + Phase 0~5 로드맵
│   ├── SCHEMA.md            ← stream-json 실측 페이로드
│   ├── COMPARISON.md        ← 외부 Stop Hook 패턴 대비
│   ├── P0_DUMP.md           ← 데이터 주도 P0 절차
│   ├── P3_DESIGN.md         ← /notify endpoint 명세
│   └── RISKS.md             ← 위험 R10~R20 누적 박제
├── INTEGRATE.md             ← 봇 본체 통합 가이드 (R16 재시작)
├── CHANGELOG.md             ← v1.0 마감 박제
└── SESSION_HANDOFF.md       ← 진행 history (가장 최근 활동 상태)
```

---

## 글로서리

| 약어 | 의미 |
|---|---|
| **P0** | stream-json 덤프 단계 (실측 스키마 확보) |
| **P1** | 분류 + push 분기 본체 (v3.2 = P1.6 + R12 통합) |
| **P1.6** | self-noise 가드 (분석 도구 false-positive 차단) |
| **P1.7-ext** | ASK_USER plain text + Markdown fallback |
| **P3** | `POST /notify` HTTP endpoint (외부 시스템 진입점) |
| **P5** | heartbeat 메타 알림 (계획 — captain-hook 자체 침묵 방지) |
| **R10~R20** | 누적 위험 박제 (`docs/RISKS.md` 참조) |
| **R12** | API_ERROR turn 도중 종료 push |
| **R13** | 봇 시스템 프롬프트 평문 키 노출 사고 |
| **R16** | 봇 다중 인스턴스 동시 가동 차단 |
| **NORMAL/SILENT/TOOL_ERROR/ASK_USER/API_ERROR** | TurnEnd 분기 5종 |

---

## 알려진 한계

- **SDK 내부 스키마 의존**: `stop_reason` / `terminal_reason` / `tool_use_result` 필드는 Claude Agent SDK 내부 구조. SDK 업데이트 시 silent break 가능. 회귀 시 unit test 먼저 깨짐.
- **봇 SHA 종속 patches/**: 봇 본체 진화에 따라 patches/ 풀 파일이 conflict. v1.x에서 middleware/plugin 인터페이스 PR로 해결 계획 (P4).
- **bot.db 평문 잔존**: 본 사고(R13)에서 봇 SQLite 안 평문 키 노출은 미처리. 외부 유출 0이라 보류, 운영 시 본인 책임.
- **dumps/ rotation 정책 부재**: P0 dump가 `dumps/<date>.jsonl`로 무한 누적. 운영 시 `find dumps/ -mtime +7 -delete` 같은 cron 필요. v1.x에서 자동화 계획.
- **단일 사용자 가정**: chat_id 1개 환경 전제. 멀티 테넌트는 향후 확장.
- **이름 충돌**: 검색 노출 약함. fork rename 권장.

---

## 기여

- 이슈 트래커: [Issues](https://github.com/q28902/captain-hook/issues)
- 라이선스: [MIT](LICENSE)
- 외부 PR 환영. 단 v1.x 유지보수 우선 (R20 TOOL_ERROR 가드 / bot.db sanitize / SDK 스키마 watchdog).

---

## 진행 history

20개 누적 위험 + 5일 안정화의 박제는 [`SESSION_HANDOFF.md`](SESSION_HANDOFF.md) 참조.
설계 결정 근거는 [`docs/DESIGN.md`](docs/DESIGN.md) + [`docs/PROBLEM.md`](docs/PROBLEM.md).

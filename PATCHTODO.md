# Captain Hook — PATCHTODO

> v1.x 운영 중 발견된 사각지대·후보 작업 대기열. 우선순위 + 진단 사례 기록.
> 정식 위험은 `docs/RISKS.md` (R10~R22 박제). 여기는 **검토 단계**.

---

## P-006 — summon-aki 폐기 후속 (2026-04-30)

**상태**: ✅ 폐기 완료 (4/30). 후속 박제만.

**경위**:
- 4/28 v1.1 작업 시 sdk_integration.py에 silent push error/warn → summon-aki spawn 블록 통합
- 4/30 폐기 결정: Aki 세션 spawn 매번 새 인스턴스로 context 단절 + 노이즈 누적 + launchd TCC 권한 다이얼로그 silent hang
- 제거 대상 5종 코드 + 인프라 파일 2종 (summon-aki.sh, AKI_SUMMON.conf) 모두 삭제

**captain-hook 영향**:
- silent push 검출 자체는 유지 (텔레그램 알림만)
- spawn 블록 제거로 향후 회귀 위험: 새 통합 commit 시 동일 패턴 재도입 우려 → SESSION_HANDOFF "통합 금지" 명시 필요

**교훈**:
- "운영 프로젝트 에러 → Aki 자동 진단" 아이디어 자체는 매력적이지만, 매 호출이 새 세션이라 누적 학습 X + 수동 컨텍스트 의존
- 진짜 가치는 알림(인지) 단계까지. 진단·fix는 사람이 시점 정해서 진입하는 게 효율적
- 향후 동일 카테고리 작업은 PATCHTODO 등재 + 명확한 "fix 가능 범위" 명세 필요

---

## P-001 — Inter-turn watchdog (ScheduleWakeup silent fail)

**상태**: ✅ **옵션 A 구현 완료 (2026-05-07)** — PreToolUse 가로채기 + launchd watchdog daemon.

**구현 내역**:
- `hooks/wakeup-promise.py` — ScheduleWakeup PreToolUse hook. 호출 가로채 ledger 등록 + permissionDecision=deny (어차피 harness silent-fail이라 무해)
- `scripts/wakeup_watchdog.py` — 60초 polling daemon. expected_fire_at 도래 시 secretarybot Telegram sendMessage
- `~/Library/LaunchAgents/com.captain.wakeup-fire.plist` — `StartInterval=60`, RunAtLoad
- `/Volumes/AIDRIVE/.claude/settings.json` PreToolUse matcher `ScheduleWakeup` 등록
- ledger: `/Volumes/AIDRIVE/captain-hook-state/wakeup_promises.jsonl` (append-only, event=promise/fired/failed)

**검증 통과**:
- ScheduleWakeup payload → deny + ledger 박힘
- 다른 도구 payload → 즉시 통과 (exit 0)
- closed promise skip (idempotent)
- 실 fire 1회 텔레그램 도착 확인

**작동 흐름** (앞으로):
1. Aki가 ScheduleWakeup 호출 → harness가 PreToolUse hook 실행 → ledger 박힘 + 호출 deny
2. 약속 시각 도래 → launchd가 60초 폴링 중 watchdog 실행 → 텔레그램 사용자에게 prompt + reason 전송
3. 사용자가 텔레그램에서 자연 응답 → 다음 turn 시작 → Aki가 약속 처리

**한계 (의도적)**:
- 자동 prompt 주입 X — 사용자 manual 메시지 1번 필요 (옵션 B는 미구현)
- ledger 무한 누적 — 향후 fired/failed > 30일 자동 archive 후속

**증상**:
- Aki가 `ScheduleWakeup` 도구로 30분/1h 후 재진입 약속
- harness가 약속 시각에 wakeup 메시지를 봇/세션에 주입해야 작동
- 실측: 주입이 silent fail하는 경우 잦음 — 약속만 하고 재진입 안 옴
- 사용자 입장에선 "Aki가 아무 말 없이 사라진" 패턴

**captain-hook v1.x가 못 잡는 이유**:
- captain-hook은 `sdk_integration.py` stream-json 인터셉트
- 작동 시점: **현 turn 안에서** stream 끝났는데 telegram 송신 0 → SILENT 푸시
- Inter-turn 이슈(end_turn 이후 다음 turn 발화 자체 부재)는 stream 인터셉트 대상 0
- → v1.x 설계 사각지대

**v2 후보 설계**:
1. **약속 등록**: Aki가 `ScheduleWakeup` 호출하면 captain-hook이 별도 ledger 기록
   - `/Volumes/AIDRIVE/captain-hook/wakeup_promises.jsonl`
   - 필드: `{promise_id, scheduled_at, prompt_hash, expected_fire_at, project, session_id}`
2. **외부 watchdog**: launchd 5분 polling daemon
   - 현재 시각 > expected_fire_at + grace(예: 5분) 이고 fire 흔적 없으면
   - → telegram 알림 + summon-aki 트리거
3. **fire 확인 신호**: 다음 turn 시작 시 captain-hook이 ledger에서 promise_id consume

**대안 (간단)**:
- Aki 룰만 강화 — "ScheduleWakeup은 항상 cct-notifier paired bash sleep과 이중화"
- 게이트 X, 의지 의존 ⚠️
- 2026-04-29 sessions에서 적용 (`/tmp/news_intel_verify/check.sh` 패턴)

**의존**:
- cct-notifier daemon (이미 가동 중) 활용 가능
- launchd plist 1건 추가

**박제 트리거**: 실제 inter-turn watchdog 미수신 사고 1건 더 발생하면 P-001 정식 진입

---

## P-002 — bot.db 평문 잔존 분석

**상태**: ✅ 1차 처리 완료 (2026-05-07). `scripts/redact_bot_db.py` 신설.

**경위 (2026-05-07)**:
- 6 패턴 정규식(sk-/Bearer/AIza/gho_/eyJhbG/api_key/TELEGRAM_BOT_TOKEN) + bot_token 9-12digits:35chars
- 백업 후 atomic UPDATE: 6 row 10 redact 적용
- 사후 단순 substring 카운트 그대로(65건) — spot check 결과:
  - row 534 등: R13 처방 자체 박힌 메타 텍스트 (`sk-*, Bearer *` 같은 패턴 자체 인용)
  - .env.example placeholder (`TELEGRAM_BOT_TOKEN=`) 값 없음
  - 키 prefix fragment 12자 (전체 키 entropy 600bit급 → reverse 불가)
- 추가 자동 redact = 위양성 폭증 → 운영 messages 가독성 깨짐 → **그만**

**파일**: `~/Projects/claude-captain-hook/scripts/redact_bot_db.py` (백업 자동 + dry-run 옵션)

---

## P-003 — 봇 self-restart 트리거

**상태**: ✅ 50% 완료 — 기본 self-restart 인프라 작동 중 (2026-05-07 점검).

**현황 (2026-05-07 발견)**:
- 봇은 launchd `com.inseyeol.claude-code-telegram` 가동 (nohup 아님 — PATCHTODO 정보 outdated)
- plist `KeepAlive=true` + `ThrottleInterval=10` → **봇 crash 시 자동 재시작 작동 중**
- 즉 R12 API_ERROR로 봇 process 죽으면 launchd가 10초 후 재시작
- 누적 health check + 자체 SIGTERM 임계는 별도 후속 (현재 우선순위 낮음)

**남은 후속 (필요 시)**:
- captain-hook decision log "API_ERROR 누적 N회" 임계 → 자체 SIGTERM (현재는 봇이 안 죽으면 재시작 안 됨)
- 봇 본체 health endpoint + watchdog daemon 별도 polling
- → 우선순위 🟢 낮음 (현재 자연 self-restart로 충분)

---

## P-004 — Transcript fsync 보강 (Stop hook race 후속)

**상태**: ⏸ **공식 보류 결정 (2026-05-07)** — captain-hook 영역 외, harness upstream PR 후보.

**결정 사유**:
- v1.1 STOP_HOOK_RACE 처방(stop_hook_active + UUID + 폴링)으로 운영상 1차 해결
- 근본 fix는 harness transcript writer fsync 강제 — Anthropic 측 코드 변경 필요
- captain-hook 자체 영역에서 추가 처방 가치 없음 (이미 폴링으로 race 차단)

**향후 진입 조건**: Anthropic harness가 transcript fsync 옵션 노출 시 활용. 그 전까진 dormant.

---

## P-005 — Outbound 도구 호출(WebFetch/Curl) silent fail 검출

**우선순위**: 🟡 중간

**증상 추정**:
- WebFetch / Bash curl 등이 timeout · 빈 응답 · 200 OK인데 본문 0 케이스
- 현재 captain-hook은 도구 호출 결과의 `is_error`만 봄
- 200 OK + 빈 응답은 통과 → 사용자 경험상 silent fail

**작업 후보**:
- 도구별 결과 길이 임계 + 시간 임계 휴리스틱
- WebFetch tool_result.body 길이 < 100 등

**의존**: ~~라이브 자연 누적 5건 후 패턴 분석~~ → 아래 결론으로 종결

**결론 ✅ 2026-09-04 — 구현하지 않는다**

**2026-09-04 전수 실측 — 가정한 증상이 실재하지 않는다.** 덤프 262개에서 `tool_use`↔`tool_result` 를 짝지어 본문 길이와 소요시간을 둘 다 쟀다(내용은 읽지 않고 길이만 — 덤프엔 민감정보가 있을 수 있다).
  - **길이 축 기각**: `WebFetch` 성공분(`is_error=false`) 81건의 **최소가 206자**다. 제안됐던 「body < 100」 은 **0건을 잡는 죽은 규칙**이었다. 짧은 응답(min 12 · p10 35)은 전부 이미 `is_error=true` 로 잡히고 있었다. `WebSearch` 성공분 최소 1336자로 동일. 전역 길이 임계는 더 위험하다 — `ToolSearch` 는 정상인데 본문 0 이 59/62, `Bash` 는 `< 100` 에 17%(1,036건)가 걸린다(정상적으로 짧은 출력).
  - **시간 축 기각**: `WebFetch` 중앙 4.8s · p90 8.2s · **최대 31.8s**(60s 초과 0건), `WebSearch` 최대 25.5s. `Bash` 만 60s 초과가 236건인데 이건 빌드·테스트의 정상 장기 실행이지 silent fail 이 아니다.
  - **표본은 충분했다** — 원래 진입 조건이 「자연 누적 5건」이었는데 실제로는 WebFetch 81건 · WebSearch 64건을 봤다. 대상 0건이 아니라 **대상이 많은데 증상이 0건**이므로 이것은 미성립이 아니라 정당한 반증이다.
  - ⚠️ **실측 없이 임계를 박았다면** 「0건 잡는 규칙」이 매번 초록을 내며 감시하는 척했을 것이다 — 이 프로젝트가 잡으려는 바로 그 실패 유형이다.
  - **재진입 조건**: 「200 OK인데 본문이 비었다」를 사람이 실제로 겪은 사례 1건. 그때는 길이가 아니라 **그 사례의 실제 형태**에서 판정식을 만든다.

---

## 메모 — 박제 정책

- 새 사각지대 발견 시 P-NNN 형식으로 추가 (NNN = 발견 순)
- 우선순위 🔴 / 🟡 / 🟢 (RISKS.md 표기와 동일)
- "박제 트리거 = N회 재발 시 정식 진입" 명시
- 정식 진입 후엔 RISKS.md 또는 SESSION_HANDOFF로 이동 + 본 파일에 ✅ 마킹

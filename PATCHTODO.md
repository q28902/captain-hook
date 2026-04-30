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

**우선순위**: 🔴 높음 (사용자 직접 지적, 2026-04-29)

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

**우선순위**: 🟡 중간 (외부 유출 0이라 보류 중, ACTIVE_PROJECTS 비고)

**증상**:
- R13 사고(2026-04-26) 후 봇 시스템 프롬프트 평문 키 환경변수 이전
- 봇 SQLite `data/bot.db`에 과거 세션 텍스트 잔존 가능성
- 실외부 노출 0 = 즉시 시급성 낮으나 cleanup 가치

**작업**:
- bot.db 안 messages 테이블 sample → R13 redact 패턴 6종으로 grep
- 매칭 row UPDATE로 redact 처리
- migration 스크립트화

**의존**: 없음

---

## P-003 — 봇 self-restart 트리거

**우선순위**: 🟡 중간 (R12 마찰 해소, 장기)

**증상**:
- API_ERROR (R12) 발생 시 captain-hook이 푸시는 하지만 봇 자체는 살아있음
- 사용자가 수동 `pkill + nohup` 재시작해야 함
- 마찰 해소 가치

**작업 후보**:
- captain-hook decision log에 "API_ERROR 누적 N회" 임계 → 자체 SIGTERM + launchd KeepAlive 활용
- 또는 watchdog 별도 daemon에서 봇 health check + self-restart

**의존**:
- 봇 launchd 등록 (현재 nohup 직접 가동, launchd 미설치)
- 기존 R16(단일 인스턴스 검증) 가이드와 통합 필요

---

## P-004 — Transcript fsync 보강 (Stop hook race 후속)

**우선순위**: 🟢 낮음 (v1.1 STOP_HOOK_RACE 처방으로 1차 해결)

**증상**:
- Stop hook fire 시점에 transcript JSONL flush 지연
- v1.1에서 stop_hook_active + UUID + 폴링으로 우회

**근본 보강 후보**:
- harness 측 transcript writer에 fsync 강제 옵션 (upstream PR 후보)
- captain-hook 영역 외 — 메모만 박제

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

**의존**:
- 라이브 자연 누적 5건 후 패턴 분석 (P0 dump 재활용)

---

## 메모 — 박제 정책

- 새 사각지대 발견 시 P-NNN 형식으로 추가 (NNN = 발견 순)
- 우선순위 🔴 / 🟡 / 🟢 (RISKS.md 표기와 동일)
- "박제 트리거 = N회 재발 시 정식 진입" 명시
- 정식 진입 후엔 RISKS.md 또는 SESSION_HANDOFF로 이동 + 본 파일에 ✅ 마킹

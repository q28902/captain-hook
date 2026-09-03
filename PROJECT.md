---
id: captain-hook
name: captain-hook
parent: telegram-cc , sample2 , law-bot
generation: 2기-개인화
purpose: 백그라운드 작업이 조용히 끝나는 것을 알리기 위한 알림 신뢰성 계층
instances:
  - ~/Projects/claude-captain-hook
domain: 도구
period: 2026.04~2026.08
declared: 보존
stack: [stream-json 파서]
---

## 결정 (append only)
- 2026-09-02 | [declared] — → 보존 | 초기 등록(5차 승인, 근거 PROJECT.md 최초 커밋(~/Projects/claude-captain-hook)) · 이 날짜는 선언일이 아니라 **정본이 처음 버전관리에 들어온 날**이다(2026-09-02 일괄 커밋). 선언 자체는 그 이전이나 시행일 근거가 이것뿐이다.
- 2026-04-26 | sample2 bridge.js 검토 → 단독 운용 거부 → Captain Hook 신설 결정 | 근거: 07_MEMORY_MAP.md §G 일일기록 타임라인
- 2026-04-27 | 누적 위험 R10~R22 처리. ProductionConfig 강제 override 회피(R18) · 텔레그램 spoiler 해석 차단(R19) · 단일 인스턴스 검증(R16) | 근거: 07_MEMORY_MAP.md §G 일일기록 타임라인
- 2026-04-28 | v1.1 Stop hook race 표준 처방. Aki 자동 호출 인프라 1차 마감(이틀 뒤 폐기됨). 채용알리미 패치 4건 | 근거: 07_MEMORY_MAP.md §G 일일기록 타임라인
- 2026-08-11 | 2026-08-11 정정 (감사 CH-1): 직전까지 이 절은 「최종 활동 2026-05-02 · 상태 v1.2 | 근거: AID:PROJECTS.md §captain-hook
- 2026-08-23 | [계보] parent `Aki-자동-호출` 가 `law-bot` 로 병합돼 참조를 옮김 | 근거: approval_input_제안.md §D-2

## 자원
- AID:captain-hook-dumps — 봇이 매 턴 쓰는 덤프 (상한: 30일 롤링 · 집행 보류)

## 대기열

- [ ] **「조용한 종료」 오판 — 실행 경로가 죽어 있어 지금은 무해** · 2026-09-03 실측: `DISABLE_CAPTAIN_HOOK=true` 가 **두 plist 모두**에 있고(`com.inseyeol.claude-code-telegram`·`com.inseyeol.waki`), `sdk_integration.py:1560` 이 그 값으로 `_captain_available = False` 를 준다 — `captain.py` 의 분류 코드는 어느 채널에서도 실행되지 않는다. **버그는 실재하지만 지금 아무 일도 안 한다.** 죽은 코드를 검증 없이 고치면 새 오류만 심는다 — 되살릴 때 먼저 고친다. 원래 진단: `captain.py:159-162` 가 `stop_reason="tool_use"` 를 보존해 뒤에 텍스트가 와도 안 덮고, 그 값으로 `TURN_END_SILENT` 가 나간다. | 해소: grep "DISABLE_CAPTAIN_HOOK" /Users/inseyeol/Library/LaunchAgents/com.inseyeol.waki.plist
> `AID:PROJECTS.md` 에서 이관(2026-08-24). 원문은 `AID:PROJECTS.legacy.md` 에 동결.

- [ ] 미커밋 5건 처리 판단 — 커밋할지 버릴지 (P-001 watchdog 포함)
- [ ] `com.captain.wakeup-fire` 재적재 여부 판단 — 끌 거면 P-001 을 폐기 처리해야 앞뒤가 맞는다
- [ ] **P-004** Transcript fsync 보강 (Stop hook race 후속) — *보류 상태*
- [ ] **P-005** Outbound 도구 호출(WebFetch/Curl) silent fail 검출 — *상태 표기 없음*
- ℹ️ 위 P-00N 은 `PATCHTODO.md`(158줄)에서 흡수했다. **`PATCHTODO` 는 CLAUDE.md 가 이름까지 지목해 금지한 todo 분산처**인데 실제로 운용되고 있었다(2026-08-11 감사 후속 발견 — 원 감사에서는 core 문서가 아니라 놓쳤다). 완료분 P-001·P-002·P-003 ✅ / P-006 폐기 는 이력이므로 그 파일에 남긴다. **새 미결은 여기에만 적을 것.**

- 2026-08-28 | [결정] **DISABLE 유지** — 되살렸을 때 실효성 불확실(사용자 「일단 disable로 두고 나중에 필요하면 더 파보자」). DISABLE_CAPTAIN_HOOK=true 그대로. ⓒ합병 권고도 보류. | 근거: 사용자 지시 2026-08-28
<!-- 마이그레이션 메모 (frontmatter 아님)
  정본 판정: **C-0 인스턴스가 하나뿐이라 자명** → `~/Projects/claude-captain-hook`  [§C 집행, 사용자 승인 2026-08-23]
  purpose 출처: ~/Projects/claude-captain-hook/README.md 첫 줄
-->

## 흐름

**입력**
- `~/Projects/claude/LAYER5/.env · ~/Projects/claude/LAYER3/.env` ← **geostock-analyzer** — 근거 `~/Projects/claude-captain-hook/scripts/wakeup_watchdog.py:32`
- `~/Projects/claude-captain-hook/dumps/*.jsonl` ← **telegram-cc** — 근거 `~/Projects/claude/claude-code-telegram/src/captain.py:51`
- `AID:claude-code-telegram/.env` ← **자격증명** — 근거 `~/Projects/claude-captain-hook/scripts/wakeup_watchdog.py:31`

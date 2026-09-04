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

- [x] **종결 2026-09-04 — 가드를 고쳤다.** `captain.py:224` 가 `has_text_block` 을 함께 본다. `has_text_block` 이 옳은 값임을 덤프 실측으로 확인했다(turn 1,945건에서 「마지막 도구 뒤 텍스트 존재」와 100% 일치 · thinking 은 안 셈). 주입 3방향 전부 잡힘(옛 판 되돌리기 3 failed · 신호원 차단 2 failed · 항상통과 3 failed) · 49 시험. ⚠️ **이 가드는 오경보만 없애고 검출력을 더하지 않는다** — `classify()` 가 `type=result` 에서만 돌아 결과 이벤트 없이 끊긴 조각은 분류에 도달조차 못 한다. 진짜 무언 종료 검출은 P-001 몫이고 그건 `_disabled_` 에 있다. 실행 경로는 여전히 죽어 있다(`DISABLE_CAPTAIN_HOOK=true` 불변). 원래 기록: 「조용한 종료」 오판 | 해소: grep+ "state.has_text_block" /Users/inseyeol/Projects/claude/claude-code-telegram/src/captain.py  ※ 2026-09-04 방향 정정 — 옛 판정식은 `grep "DISABLE_CAPTAIN_HOOK" waki.plist`(안 잡히면 해소)라 **가드를 없애면 해소**로 읽혔다. 버그를 되살리는 것이 해소가 되는 구조였다. 진짜 해소는 오판 자체를 고치는 것이므로 「글쓴이 가드가 실제로 소비되는가」로 바꾼다  ※ **2026-09-04 실측 후속 — 가드는 고쳤고(아래 항목) 오판의 뿌리는 남았다.** 덤프 raw 65파일 1,304,216줄로 turn 1,945건을 재구성하니 SILENT 가 1,174건(60%)인데 **그 전부가** 마지막 도구 뒤에 텍스트를 냈고 `result.result` 도 비어 있지 않았다(median 1,013자) — 결과 시점 분류의 오판률이 100% 다. 실제 `p1_decisions` 2,037건에서 `text_response_count` 는 2,029건이 0(=가드 한 번도 발동 안 함)이었고 push 는 1,513건(silent 1,159 · tool_error 309 · api_error 45)이었다. 가드를 고치면 그중 1,424건(silent+tool_error)이 **전부 0** 이 된다. 그리고 **진짜 무언 종료는 이 경로로 안 잡힌다** — `classify()` 는 `type=result` 에서만 도는데 결과 이벤트 없이 끊긴 조각이 65일 동안 14건 있었다(9건은 06-27 한 날). 그건 P-001 inter-turn watchdog 몫이다. **주의: 이 항목의 판정식은 이제 가드 수정만으로 맞아떨어진다 — 분류식(any-패턴 stop_reason)은 그대로이므로 자동 해소로 읽지 말 것.**
> `AID:PROJECTS.md` 에서 이관(2026-08-24). 원문은 `AID:PROJECTS.legacy.md` 에 동결.

- [x] 🔴 **글쓴이 가드가 무력하다** (2026-09-04 발견 → 같은 날 해소) — 옛 `captain.py:224` 의 `if state.text_response_count > 0: return None` 은 그 값을 올리는 곳이 `sdk_integration.py:1559,1566` **두 곳뿐이고 둘 다 captain 이 이미 push 한 뒤**라 봇 본체의 텍스트 출력으로는 절대 안 올라갔다. `has_text_block` 은 선언·대입만 있고 소비처가 0건이었다. **고침**: 가드를 `if state.text_response_count > 0 or state.has_text_block:` 로 바꿨다.
  - 값이 맞는지 먼저 실측했다 — ① `:128` 은 `assistant` 의 `text` 블록에서만 오르고 `thinking` 은 안 센다(사고 평문은 `sdk_integration.py` 의 ThinkingBlock 분기로 빠져 텔레그램 본문에 안 나간다) ② 서브에이전트 오염은 65일 text 블록 6,401개 중 **2개**(0.03%, 06-27 하루)뿐이고 그 경로도 `_handle_stream_message` 에 부모 필터가 없어 사용자에게 똑같이 흘러간다 ③ turn 1,945건에서 `has_text_block` 은 「마지막 도구 뒤 텍스트 존재」·「`result.result` 비어있지 않음」과 **100% 일치**했다.
  - 시험: `tests/unit/test_captain_writer_guard.py` 6건(주입). 옛 판으로 되돌리면 3건이 깨진다 — 실측으로 확인.
  - **효과**: 65일 표본 기준 silent+tool_error push 1,424건 → 0건. 즉 이 가드는 오경보를 없앨 뿐 **검출력을 더하지 않는다**(위 항목 참조). | 해소: grep+ "state.has_text_block" /Users/inseyeol/Projects/claude/claude-code-telegram/src/captain.py
- [ ] 미커밋 5건 처리 판단 — 커밋할지 버릴지 (P-001 watchdog 포함)  ※ 2026-09-04 — **판정식을 붙이지 않는다.** 옛 5건은 2026-09-03 `5804ab2` 로 **이미 커밋됐다**. 남은 것은 「미푸시 4커밋을 공개 저장소에 밀지」이고 **사람 결정**이다. 하드코딩 시크릿 0건 확인됐으나 절대경로·내부 운영 서술이 공개된다. 이 게이트는 미등록이라 위생 검사가 잡을 것 — 사람 결정 항목이라 판정식을 억지로 만들지 않는다
- [ ] **`com.captain.wakeup-fire` — 조건부 대기(할 일 없음)** · plist 가 `~/Library/LaunchAgents/_disabled_20260727/` 에 **온전히 보관돼 있고**(2026-09-04 정정 — 옛 서술 「0건·신설」은 틀렸다. 최상위에 없을 뿐이고 복구는 신설이 아니라 `mv` + `plist_reload.sh` 다) 저장소엔 스크립트만 저장소엔 스크립트만 있다 — 재적재할 대상이 없다. 그리고 짝인 P-001 은 `PATCHTODO.md:84` 에 **박제 트리거**가 이미 적혀 있다: 「실제 inter-turn watchdog 미수신 사고 1건 더 발생하면 정식 진입」. **조건이 안 걸렸으므로 지금 할 일이 없다.** 사고가 나면 그때 신설한다 (재적재가 아니라 신설이다). (2026-09-04 재범위) | 해소: grep "ScheduleWakeup" /Volumes/AIDRIVE/.claude/settings.json  ※ 2026-09-04 — 폐기가 권고다. `AGENTS.md` Never 절이 `ScheduleWakeup` **사용 자체를 금지**하므로 감시 대상 행위가 규칙상 존재하지 않는다(전제 소멸). plist 는 `_disabled_20260727/` 에 보존돼 있으니 원칙 서열 ① 대로 그대로 두고, **PreToolUse 훅 배선만** 걷으면 해소다
- [ ] **P-004** Transcript fsync 보강 (Stop hook race 후속) — *보류 상태* | 해소: grep+ "fsync" /Users/inseyeol/Projects/claude/claude-code-telegram/hooks/file-send-guard.py  ※ 2026-09-04 — 진입 조건이 **외부**다(Anthropic harness 가 fsync 옵션을 노출해야 한다). 1차 처방(stop_hook_active + UUID + 3초 폴링)은 라이브에 살아 있어 지금 위험하지 않다. harness 가 옵션을 주면 이 판정식이 켜진다
- [ ] **P-005** Outbound 도구 호출(WebFetch/Curl) silent fail 검출 — *미착수(구현 0건)*. 진입 조건 데드락(「라이브 자연 누적 5건 후 분석」인데 `DISABLE_CAPTAIN_HOOK=true` 가 P0 덤프를 막아 표본이 영원히 안 쌓임 — 통과가 아니라 **미성립**)은 **2026-09-04 선분석으로 풀었다**. 라이브를 기다리지 않고 이미 쌓인 덤프를 읽었다. 임계가 서야 코드를 만들 수 있으므로 구현은 아직 없다 | 해소: grep+ "WebFetch" /Users/inseyeol/Projects/claude/claude-code-telegram/src/captain.py
  - **표본**(읽기만 함 · 덤프 무수정) — raw 65파일 1,304,216줄. 「131파일 620MB(04-26~09-02)」는 과대표현이다: 실제 알맹이는 **2026-04-27~06-28** 이고 07-31·09-02 파일은 각각 233·260줄짜리 껍데기다(DISABLE 이후). turn 재구성 1,945건, outbound `tool_result` **619건 / 43일** — Bash+curl 457 · WebFetch 98 · WebSearch 64.
  - **WebFetch 하드 실패는 이미 갈려 있다** — `is_error=true` 17건은 길이 12~123자("Request failed with status code 404/403" 류), `is_error=false` 81건은 최소 206자. 두 분포가 안 겹친다(123 < 206). 여기엔 새 규칙이 필요 없다 — 기존 TOOL_ERROR 경로가 덮는다.
  - **진짜 silent fail 은 「에러가 아닌데 알맹이가 없다」** — `is_error=false` 81건 중 **21건(26%)**이 "Loading… 상태", "No datasets found. `num_found:0`", "등록된 기사가 없습니다", "ERROR-301", "REDIRECT DETECTED" 류다. 21건 전부 육안 확인했다(정밀도 21/21). 비매치 60건을 다시 훑어 **8건쯤 더** 놓친 것을 봤다(REDIRECT DETECTED 3건 포함) → 실제 비율은 **약 29/81 ≈ 36%**.
  - **길이 임계 후보 = 400자.** `<400` 은 8건 중 7건이 진짜(정밀도 88%)지만 재현율은 7/21(33%)뿐이다. `<300` 은 4/4(100%)로 정밀하나 재현율 19%. `<500` 으로 늘리면 23건 중 10건(43%)으로 무너진다 — 성공 최소가 386자이고 실패 median 이 513자라 400자 위로는 두 분포가 겹친다. **길이 단독으로는 판정식이 안 선다.**
  - **Bash+curl 은 길이 임계 미성립 — 제외 권고.** `is_error=false` 429건 중 50자 미만이 59건인데 그중 실패는 6건(10%)뿐이다. 나머지는 `ok` · `tunnel 502` · `HTTP:200 SIZE:74003` 같은 **의도적 압축 출력**이다. 짧다 = 실패가 아니다. 이 계열은 길이가 아니라 명령에 이미 들어 있는 `-w "%{http_code}"` 나 종료코드를 봐야 한다.
  - **만들 수 있는 것** — 「WebFetch 한정 · `is_error=false` · 본문 400자 미만 **또는** 무응답 문구 매치」의 **경고 1종**(차단 아님). 문구 매치가 길이보다 강하다(육안 정밀도 21/21, 재현율 ~72%). 표본은 임계 **후보**를 세우기엔 충분하지만 400자 경계의 근거는 n=8 이라 **확정 근거로는 부족하다** — 되살린 뒤 라이브에서 다시 잰다.
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

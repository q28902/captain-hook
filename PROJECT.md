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

- **2026-09-04 — 감시자 자신의 침묵을 없앴다(P1.7).** 인세열님 지적: 「지금 우리가 감사하면서 했던 실수들이 여기 몇개 있다」. 실제로 있었다. `classify()` 가 예외를 만나면 `TURN_PROGRESS`(=아직 진행 중)를, `silent_detector_decide()` 가 예외를 만나면 `None`(=푸시 안 함)을 돌려줬다. **둘 다 「알림 없음」과 같은 뜻**이라, 조용한 종료를 잡는 도구가 **자기 고장에는 조용해지는** 구조였다. 이 프로젝트가 막으려는 형태를 이 프로젝트가 갖고 있던 셈이다. 오늘 감사에서 같은 형태를 여러 번 잡았다 — 「미성립을 통과로 세기」·「게이트가 빈 통과」·「stderr 만 찍고 아무도 안 봄」. 수리: `TURN_CLASSIFY_FAILED` 분류 신설 · 두 예외 경로 모두 **`level="error"` 푸시**로 전환 · 사유를 `state.classify_error` 에 보존. 실측: 분류기 고장 → `classify_failed` + error 푸시, 감시자 고장(직렬화 불가 입력) → error 푸시. 테스트 3건 추가, 전 분기 PASS
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
- [ ] **미푸시 커밋을 공개 저장소에 밀지 — 사람 결정** (제목 정정 2026-09-04: 「미커밋 5건」은 실체와 다르다. 미커밋은 **0건**이고 옛 5건은 2026-09-03 `5804ab2` 로 이미 커밋됐다). `git status` 깨끗 · **미푸시 8커밋**(2026-09-04 회차에 4개 추가돼 4→8). 원격은 공개 `github.com/q28902/captain-hook`. **노출 실측(2026-09-04, 미푸시 전체 diff)**: 7파일 · +515줄. 🟢 시크릿 의심 **0** · 이메일·실명 **0**. 🟡 노출되는 것은 경로와 내부 운영 서술뿐 — `/Users/inseyeol` **6건**(`PROJECT.md` 4 · `scripts/wakeup_watchdog.py` 2) · `/Volumes/AIDRIVE` **9건**. 즉 선택지는 ⓐ 그대로 push ⓑ 경로를 `~`·환경변수로 바꾼 뒤 push ⓒ 계속 로컬 보관. **판정식을 붙이지 않는다** — 사람 결정 항목이라 기계가 대신 닫으면 안 된다
- [ ] **`com.captain.wakeup-fire` — 조건부 대기(할 일 없음)** · plist 가 `~/Library/LaunchAgents/_disabled_20260727/` 에 **온전히 보관돼 있고**(2026-09-04 정정 — 옛 서술 「0건·신설」은 틀렸다. 최상위에 없을 뿐이고 복구는 신설이 아니라 `mv` + `plist_reload.sh` 다) 저장소엔 스크립트만 저장소엔 스크립트만 있다 — 재적재할 대상이 없다. 그리고 짝인 P-001 은 `PATCHTODO.md:84` 에 **박제 트리거**가 이미 적혀 있다: 「실제 inter-turn watchdog 미수신 사고 1건 더 발생하면 정식 진입」. **조건이 안 걸렸으므로 지금 할 일이 없다.** 사고가 나면 그때 신설한다 (재적재가 아니라 신설이다). (2026-09-04 재범위) | 해소: grep "ScheduleWakeup" /Volumes/AIDRIVE/.claude/settings.json  ※ 2026-09-04 — 폐기가 권고다. `AGENTS.md` Never 절이 `ScheduleWakeup` **사용 자체를 금지**하므로 감시 대상 행위가 규칙상 존재하지 않는다(전제 소멸). plist 는 `_disabled_20260727/` 에 보존돼 있으니 원칙 서열 ① 대로 그대로 두고, **PreToolUse 훅 배선만** 걷으면 해소다
- [ ] **P-004** Transcript fsync 보강 (Stop hook race 후속) — *보류 상태* | 해소: grep+ "fsync" /Users/inseyeol/Projects/claude/claude-code-telegram/hooks/file-send-guard.py  ※ 2026-09-04 — 진입 조건이 **외부**다(Anthropic harness 가 fsync 옵션을 노출해야 한다). 1차 처방(stop_hook_active + UUID + 3초 폴링)은 라이브에 살아 있어 지금 위험하지 않다. harness 가 옵션을 주면 이 판정식이 켜진다
- [x] **P-005 종결 2026-09-04 — 구현하지 않는다(반증).** Outbound 도구 호출 silent fail 검출. **2026-09-04 전수 실측 — 가정한 증상이 실재하지 않는다.** 덤프 262개에서 `tool_use`↔`tool_result` 를 짝지어 본문 길이와 소요시간을 둘 다 쟀다(내용은 읽지 않고 길이만 — 덤프엔 민감정보가 있을 수 있다).    - **길이 축 기각**: `WebFetch` 성공분(`is_error=false`) 81건의 **최소가 206자**다. 제안됐던 「body < 100」 은 **0건을 잡는 죽은 규칙**이었다. 짧은 응답(min 12 · p10 35)은 전부 이미 `is_error=true` 로 잡히고 있었다. `WebSearch` 성공분 최소 1336자로 동일. 전역 길이 임계는 더 위험하다 — `ToolSearch` 는 정상인데 본문 0 이 59/62, `Bash` 는 `< 100` 에 17%(1,036건)가 걸린다(정상적으로 짧은 출력).    - **시간 축 기각**: `WebFetch` 중앙 4.8s · p90 8.2s · **최대 31.8s**(60s 초과 0건), `WebSearch` 최대 25.5s. `Bash` 만 60s 초과가 236건인데 이건 빌드·테스트의 정상 장기 실행이지 silent fail 이 아니다.    - **표본은 충분했다** — 원래 진입 조건이 「자연 누적 5건」이었는데 실제로는 WebFetch 81건 · WebSearch 64건을 봤다. 대상 0건이 아니라 **대상이 많은데 증상이 0건**이므로 이것은 미성립이 아니라 정당한 반증이다.    - ⚠️ **실측 없이 임계를 박았다면** 「0건 잡는 규칙」이 매번 초록을 내며 감시하는 척했을 것이다 — 이 프로젝트가 잡으려는 바로 그 실패 유형이다.    - **재진입 조건**: 「200 OK인데 본문이 비었다」를 사람이 실제로 겪은 사례 1건. 그때는 길이가 아니라 **그 사례의 실제 형태**에서 판정식을 만든다. 원래 기록: P-005 Outbound 도구 호출(WebFetch/Curl) silent fail 검출 — 미착수(구현 0건) | 해소: grep+ 가정한 증상이 실재하지 않는다 /Users/inseyeol/Projects/claude-captain-hook/PATCHTODO.md
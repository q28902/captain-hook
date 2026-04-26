# Captain Hook — SESSION HANDOFF

**Repo**: `q28902/captain-hook` (private)
**로컬**: `~/Projects/claude-captain-hook/`
**상태**: Phase 1 착수 대기
**최종 업데이트**: 2026-04-26
**완성 목표**: 2026-05-02 이전 (news_intel 재개 전 1주일)

---

## 한 줄 정체

claude-code-telegram 봇에 stream-json 파서 추가 → Claude의 백그라운드 작업·조용한 종료를 외부 강제로 100% 가시화.

## 현재까지

- 설계 문서 4종 작성·push 완료 (`README.md`, `docs/PROBLEM.md`, `docs/DESIGN.md`, `docs/COMPARISON.md`)
- sample2 검토 완료 → 본체 운영 X 결정, 핵심 패턴만 흡수 (P4)
- 3층 구조 + Phase 1~4 로드맵 확정

## 다음 세션 즉시 착수 — Phase 1 (P1)

**목표**: 봇 stream-json에서 백그라운드 도구 호출 자동 감지 → cct-notifier 자동 등록.

### 단계
1. **진입점 분석**: `/Volumes/AIDRIVE/claude-code-telegram/src/claude/sdk_integration.py` 읽고 stream-json 이벤트 흐름 파악
2. **모듈 신설**: `src/captain_hook/stream_parser.py`, `src/captain_hook/auto_register.py`
3. **감지 패턴 구현**:
   - `Bash(run_in_background=true)` → tool_use 이벤트에서 PID 추출
   - `Bash(command="nohup ... &")` → 정규식 매칭
   - `Agent(run_in_background=true)` → marker file 약속 추출
4. **cct-notifier 등록**: `~/Projects/claude/cct-notifier/scripts/notify-when-done.sh` subprocess 호출
5. **봇 응답 첨부**: turn 종료 메시지에 "🔔 추적 등록: N개" 자동 추가
6. **테스트**: 5분짜리 백그라운드 명령 실행 → 자동 등록 → 5분 후 알림 확인

### 코드 위치 약속

봇 본체(`/Volumes/AIDRIVE/claude-code-telegram/`)에 새 모듈 추가:
- `src/captain_hook/__init__.py`
- `src/captain_hook/stream_parser.py`
- `src/captain_hook/auto_register.py`
- `src/captain_hook/silent_detector.py` (Phase 2)

이 repo(`~/Projects/claude-captain-hook/`)는 **설계 문서·테스트 시나리오·릴리즈 노트만** 보관. 실제 코드는 봇 repo에 들어감.

> 봇 repo는 RichardAtCT/claude-code-telegram fork. push 권한 확인 필요. 권한 없으면 q28902로 fork 생성 후 진행.

## Phase 2~4 후순위

- Phase 2 (P2): 빈 응답·조용한 종료 자동 가시화 — `silent_detector.py`
- Phase 3 (P3): 봇 안 `POST /notify` 외부 호출용 엔드포인트
- Phase 4 (P4): `~/.claude/settings.json` Stop Hook 등록 (sample2 차용)

## 검증 체크리스트 (DESIGN.md 발췌)

- [ ] 백그라운드 작업 5분짜리 시작 → 자동 등록 → 5분 후 알림 도착
- [ ] Subagent marker 약속 → marker touch → 알림 도착
- [ ] Turn 종료 시 빈 응답 → "조용한 종료" 메시지 푸시
- [ ] CLI 직접 사용 시 Stop Hook 발화 확인
- [ ] 봇 재시작 후에도 등록된 작업 polling 지속

## 다음 세션 진입 시

1. ACTIVE_PROJECTS.md → captain-hook Top entry 확인
2. 이 문서 읽기
3. 봇 repo push 권한 확인 (`gh repo view RichardAtCT/claude-code-telegram --json viewerPermission`)
4. Phase 1 단계 1부터 진행
5. 작업 종료 시 이 문서 + ACTIVE_PROJECTS.md 갱신

## 관련 자산

- 봇 본체: `/Volumes/AIDRIVE/claude-code-telegram/` (origin: `RichardAtCT/claude-code-telegram`)
- cct-notifier: `~/Projects/claude/cct-notifier/`
- sample2 참고용: `/Volumes/AIDRIVE/sample2/telegram-bridge/` (운영 X)
- 영감 출처: https://www.gpters.org/nocode/post/claude-code-telegram-automatic-iye3YWTeNJoYxhz

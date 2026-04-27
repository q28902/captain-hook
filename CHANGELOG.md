# CHANGELOG

## v0.9-rc (2026-04-27)

P3 라이브 검증 통과 후 v1.0 정식 마감.

핵심 미션 4건 작동:

1. **봇 내부 누락 검출** — P0/P1 (SILENT/TOOL_ERROR/ASK_USER/API_ERROR 분기) ✅
2. **글쓴이 미해결 영역 보장** — R12/R10/false-positive 가드 ✅
3. **외부 시스템 → captain 채널** — P3 코드 + unit test 5/5 ⚠️ (라이브 미검증)
4. **진단 인프라** — R10~R17 누적 박제 + INTEGRATE.md 표준 가이드 ✅

### v1.0 마감 조건 (P3 라이브 검증 4건)

- ENABLE_API_SERVER 통과
- API 포트 확정 + curl 정상 호출
- 텔레그램 📡 prefix 도착
- captain decision log 분리 (또는 R17 보강)

### 글쓴이 Stop Hook 대비 가치

- bg SILENT 추가 보장
- ASK_USER forwarding 추가 보장 (P1.7-ext)
- false-positive 차단 (P1.6 가드)
- API_ERROR turn 도중 종료 push (R12 자연 5건+ 검증)
- 단일 봇 검증 (R16)
- 평문 키 차단 + redaction 6패턴 (R13/R13-ext)
- 외부 시스템 진입점 (P3, 코드 단계)

### 라이브 검증

- 1주일 안정화 (4-22 ~ 4-27, **5일 압축**)
- ASK_USER plain text 도착 확인 ✅
- SILENT bg 도착 확인 ✅
- API_ERROR 자연 발생 5건+ ✅
- P3 코드 + unit test 5/5 통과 ⚠️ (라이브 검증 미실시 — 다음 회차에 실측)

### 미해결 (v1.x 영역)

- bot.db 평문 잔존 분석 (외부 유출 0이라 보류)
- 봇 self-restart 트리거 (R12 마찰 해소)
- P3 rate limit 추가
- captain 분기와 P3 알림 통합 dump 분리

### 다음 활동

news_intel 5월 2일 재개 또는 v1.x 유지보수.

---

## 진행 history (참고)

- **P0** (스키마 덤프): stream-json 실측 → SCHEMA.md
- **P1 v1**: 마지막 값 보존 단순 설계
- **P1.5**: silently fail 진단 (오인 — 어제 dumps 파일만 봐서)
- **P1 v2**: any-pattern 누적 재설계
- **P1 v3**: caller + self-noise path 통합
- **P1 v3.1**: R12 API_ERROR push
- **P1.6**: self-noise SILENT 가드 + Idle 1번 흡수
- **P1.7**: orchestrator stderr print + plain fallback (silent fail 진단용)
- **P1.7-ext**: captain ask_user_forwarding plain text 변환
- **P1.7-ext-final**: orchestrator parse_mode="Markdown" 제거
- **R13-ext**: 봇 본체 CLAUDE.md 평문 키 sanitize
- **R16**: pkill + 인스턴스 검증 (다중 봇 차단)
- **P3**: /notify endpoint + Bearer 인증 + EventBus publish + R17 prefix

총 누적 commit 35건 (q28902/captain-hook public).

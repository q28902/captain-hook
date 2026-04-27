# Contributing to Captain Hook

## 기여 절차

1. **Fork** → 자기 GitHub 계정에 fork
2. **Branch** 생성 — `feat/<기능>` / `fix/R<번호>` / `docs/<범위>` 패턴
3. **Test** 통과 — `python3 tests/test_captain.py && python3 tests/test_orchestrator_patch.py && python3 tests/test_notify_endpoint.py`
4. **PR 생성** — 변경 요약 + 관련 R 번호 + 라이브 검증 결과 (해당 시)

## 코드 스타일

- captain.py 본체: 의존성 0 유지 (stdlib만)
- 모든 함수 fail-safe (`try/except` + stderr 로그, 절대 raise X)
- 분기·결정 함수는 unit test fixture 1건 이상 필수
- README/INTEGRATE/RISKS 변경 시 같은 PR에 박제 (`Note: R{번호} 추가/처리`)

## 머지 기준

- ✅ CI green (`tests` workflow)
- ✅ Reviewer 1명 이상 승인 (현재: q28902)
- ✅ 위험 박제 동기화 (RISKS.md 또는 README "알려진 한계" 갱신)

## 위험 박제 규칙

신규 결함·한계 발견 시 `docs/RISKS.md`에 R 시리즈로 박제:
- 표 행 1줄 추가 (위험 #, 설명, 처리 시점)
- 본문 섹션 (증상 + 근본 원인 + 처리 옵션 + 처리 시점)
- 처리 완료 시 별도 commit으로 박제 갱신

## v1.x 우선순위

GitHub Issues 라벨 `v1.x`:
- **R20**: TOOL_ERROR 분기 P1.6 가드 확장 (false-positive 차단)
- **R21**: SDK 스키마 watchdog (`tests/test_schema_watchdog.py`)
- **R22**: bot.db 평문 sanitize 스크립트

## 라이센스

기여한 코드는 [MIT](LICENSE) 라이선스로 배포.

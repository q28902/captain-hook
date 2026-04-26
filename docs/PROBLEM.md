# PROBLEM — 박제된 문제 정의

## 한 문장

**"Claude는 알고 조용히 끝나지만, 사용자에겐 전달되지 않는다."**

## 누락 패턴 4종

### A) Turn 안 보고 누락
- 봇은 turn 종료는 안다 → 빈 응답이 가는 정도
- Claude가 마지막 도구 결과를 *해석·요약·보고*하지 않은 채 종료
- 본질: Claude의 보고 의무 위반 (정책 문제)
- **A-AUQ**: AskUserQuestion 호출 시 SDK 자동 빈 응답으로 질문 자체가 사용자 미노출 ([RISKS.md R10](RISKS.md) 참조)

### B) 백그라운드 작업 turn 후 완료/실패
- Claude가 `nohup ... &` / `Bash(run_in_background=true)`로 던지고 turn 종료
- 작업 완료 시점엔 Claude도 봇도 호출되지 않음
- cct-notifier가 PID polling으로 보완 중이나, **Claude가 등록을 깜빡하면 알림 0**
- 룰("자동 등록 의무")로 강제 중이지만 룰 위반 발생 가능

### C) Agent SubAgent 백그라운드 완료
- `Agent(run_in_background=true)`로 띄운 서브에이전트
- marker file 패턴(`touch /tmp/<id>.done`)으로 보완 중
- 동일하게 "marker touch 깜빡 위험"

### E) Turn 외부 강제 종료에 의한 응답 침묵 ⚠️ 2026-04-26 자연 발생 1건

D와 다른 패턴:
- D: 백그라운드 작업 자체 실패 (turn 종료 *후* 시점)
- E: turn 자체가 외부 요인으로 강제 종료 (Claude 응답 생성 *전*)

증상:
- result.is_error: true + result: null + terminal_reason: null
- 봇 응답 0건 (Claude가 응답 생성 전 끊김)
- 사용자가 본 마지막 = 마지막 tool_use 호출만, 그 다음 침묵
- 사용자는 turn이 끝났는지 진행 중인지 모름

트리거 후보: rate limit, 네트워크 단절, OOM, 시간 초과, 외부 kill.

처리: P1 v3.1 captain.silent_detector_decide의 API_ERROR 분기 — 글쓴이 가드 무시 + "🛑 Claude turn 비정상 종료" 강제 푸시. RISKS.md R12 + SCHEMA.md API_ERROR 페이로드 참조.

### D) 백그라운드 실패의 침묵 ⚠️ 실무 페인포인트 1번
- 사용자: "harness 돌려둬"
- Claude: "OK, 백그라운드로 돌립니다 PID 12345" → turn 종료
- bg 작업: 5초 만에 import error → exit 1 → 프로세스 사라짐
- cct-notifier polling: PID 사라짐 = 완료? 실패? **구분 없으면 모두 "완료"로 잘못 알림**
- 결과: 사용자는 "성공한 줄" 알고 30분 뒤 결과 보러 갔다가 빈 손
- 본 시스템 동기 1번에 해당하는 패턴 — 반드시 잡아야 함

#### 분기 요구사항
- `exit_code == 0` → ✅ 완료 알림
- `exit_code != 0` → ⚠️ 실패 알림 + stderr tail 30줄 첨부
- `exit_code 잡지 못함` (PID 단순 사라짐) → ❓ "비정상 종료 가능성" 알림
- 위 3분기는 cct-notifier 또는 wrapper 레이어에서 보장 필요

## 왜 sample2의 Stop Hook으로는 못 푸는가

Stop Hook은 **turn 종료 시점**에 발화. 백그라운드 작업 완료 시점은 turn 종료 *후*. 두 시점 사이엔 Claude도 Hook도 호출되지 않음 → Hook 무의미.

Stop Hook은 A) 패턴의 "turn 종료 자체 알림"은 보장하나, *내용*은 강제 못함. Claude가 보고 안 한 채 끝내면 "turn 끝났음"만 알림.

## 진짜 해결책의 조건

1. **Claude의 의지에 의존하지 말 것** (gpters 글의 통찰 그대로)
2. 백그라운드 작업 *시작* 시점에 자동 등록 (Claude 등록 망각 무력화)
3. 백그라운드 작업 *완료* 시점에 외부 daemon이 polling 알림 (cct-notifier 활용)
4. Turn 종료 시 빈 응답·조용한 종료 자동 가시화

## 수단 — 왜 봇 stream-json 파서인가

봇은 SDK로 Claude를 호출하며 모든 도구 호출·이벤트를 stream-json으로 100% 본다. 봇 코드는 Claude가 끄거나 우회할 수 없는 외부 프로세스 → **봇 자체가 외부 강제 레이어**.

- `Bash(run_in_background=true)` 호출 발견 → 즉시 cct-notifier 등록
- `Bash(command="nohup ... &")` 패턴 매칭 → PID 추출 → 등록
- `Agent(run_in_background=true)` 호출 발견 → marker file 약속 추출 → 등록
- Turn 종료 시 텍스트 응답 0건 → "⚠️ 조용한 종료" 자동 푸시

Claude가 보고 안 해도 봇이 강제로 노출.

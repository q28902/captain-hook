# P3 DESIGN — HTTP /notify endpoint

**상태**: 진입 점검 완료, 작업량 1x 확정 (2026-04-27).
**근거**: 봇 본체 `src/api/server.py` FastAPI 서버 이미 가동 중 (GitHub HMAC webhook 등). endpoint 추가만 하면 됨.

## 목적

외부 시스템 (news_intel n8n, 다른 봇, 외부 스크립트 등)이 captain 채널로 텔레그램 메시지 송신 — captain의 push 흐름 재사용.

## 명세

### endpoint
- `POST /notify`

### 인증
- shared secret: 헤더 `X-Captain-Token`
- `.env`에 `CAPTAIN_HOOK_NOTIFY_TOKEN=<random>` 보관 (gitignored)
- 토큰 불일치 → 401
- localhost 바인딩이라도 인증 필수 (다른 컨테이너·n8n 같은 네트워크 접근 가능)

### payload schema
```json
{
  "target_chat_id": 2138498623,         // optional, 미지정 시 NOTIFICATION_CHAT_IDS 첫 값
  "message_type": "info",                // info | warn | error (이모지 매핑)
  "content": "메시지 본문",
  "parse_mode": "HTML"                   // optional, 기본 plain
}
```

### 응답
- 200: `{"ok": true, "message_id": <telegram_message_id>}`
- 401: `{"ok": false, "error": "auth"}`
- 400: payload 검증 실패
- 500: 텔레그램 송신 실패 (rate limit 등)

### 호출 예시
```bash
curl -X POST http://localhost:8080/notify \
  -H "X-Captain-Token: $CAPTAIN_HOOK_NOTIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "🟢 news_intel digest 완료", "message_type": "info"}'
```

## 구현 위치

`src/api/server.py`에 핸들러 함수 추가:

```python
@app.post("/notify")
async def captain_notify(
    request: Request,
    x_captain_token: Optional[str] = Header(None),
):
    expected_token = os.environ.get("CAPTAIN_HOOK_NOTIFY_TOKEN")
    if not expected_token or x_captain_token != expected_token:
        raise HTTPException(status_code=401, detail="auth")

    payload = await request.json()
    chat_id = payload.get("target_chat_id") or settings.notification_chat_ids[0]
    content = payload.get("content", "")
    parse_mode = payload.get("parse_mode")

    # 봇 facade 접근 — server.py가 bot_application 보유하는지 확인 필요
    sent = await bot_application.bot.send_message(
        chat_id=chat_id,
        text=content,
        parse_mode=parse_mode,
    )
    return {"ok": True, "message_id": sent.message_id}
```

**의존성 점검 필요**: `src/api/server.py`가 봇 application 객체에 접근 가능한지. 만약 별도 process라면 EventBus 또는 NotificationService 경유 권장.

## Unit test

```python
# tests/test_p3_notify.py
async def test_notify_auth_fail():
    response = await client.post("/notify", json={"content": "x"})
    assert response.status_code == 401

async def test_notify_success():
    response = await client.post(
        "/notify",
        headers={"X-Captain-Token": "test_token"},
        json={"content": "hello"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
```

## 검증 시나리오 (라이브)

1. `.env`에 `CAPTAIN_HOOK_NOTIFY_TOKEN` 추가 + 봇 재시작 (R16 가이드)
2. `curl POST /notify` (토큰 + payload) → 텔레그램 메시지 도착 확인
3. 토큰 누락 → 401
4. 외부 호출자 통합 (news_intel n8n workflow 한 곳 시범 적용)

## 1주일 마감 후 별도 회차 작업

P3는 1주일 안정화 작업 외 별도. 다음 라운드 진입 시 본 문서 그대로 활용.

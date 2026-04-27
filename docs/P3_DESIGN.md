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
  "target_chat_id": <YOUR_TELEGRAM_CHAT_ID>,         // optional, 미지정 시 NOTIFICATION_CHAT_IDS 첫 값
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

---

## 📌 보강 (2026-04-27 events/notifications 점검 결과)

**작업량 1.0x 확정** (1.2x 아님). 봇 본체에 모든 인프라 이미 박혀있음.

### 실측 발견

| 자산 | 위치 | 활용 |
|---|---|---|
| `AgentResponseEvent` | `src/events/types.py:46` | payload schema 그대로 차용 (chat_id+text+parse_mode+reply_to_message_id) |
| `NotificationService` | `src/notifications/service.py:24` | `AgentResponseEvent` 구독 + chat_id 라우팅 + rate-limited send 자동 |
| `EventBus.publish(event)` | `src/events/bus.py:68` | publish 한 줄로 송신 흐름 trigger |
| `verify_shared_secret(auth, secret)` | `src/api/auth.py` | `Bearer <secret>` 표준 |
| webhook publish 패턴 | `src/api/server.py` `event_bus.publish(event)` | 그대로 차용 |

### 보강 명세

**1. handler 코드 — AgentResponseEvent publish**
```python
@app.post("/notify")
async def captain_notify(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    secret = settings.captain_notify_secret
    if not secret or not verify_shared_secret(authorization, secret):
        raise HTTPException(status_code=401, detail="auth")

    payload = await request.json()
    chat_id = payload.get("chat_id", 0)
    text = payload.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    # 외부 호출자 식별 prefix (R17 차단)
    source = payload.get("source", "external")
    text = f"📡 [{source}] {text}"

    event = AgentResponseEvent(
        chat_id=chat_id,
        text=text,
        parse_mode=payload.get("parse_mode", "HTML"),
        reply_to_message_id=payload.get("reply_to_message_id"),
        source="captain_notify",
    )
    await event_bus.publish(event)
    return {"ok": True, "event_id": event.id}
```

**2. 인증** — 새 헤더 만들 필요 X. `Authorization: Bearer <secret>` 표준 헤더 + `verify_shared_secret` 재사용.

**3. settings 추가** — `captain_notify_secret: Optional[str] = None`

**4. target_chat_id 라우팅** — `chat_id=0` 보내면 NotificationService의 `_resolve_chat_ids`가 자동으로 `default_chat_ids` fallback. 외부 호출자가 명시 시 그쪽으로 송신.

**5. 메시지 prefix (R17 사전 박제)** — `📡 [source] <text>` 형태로 captain 본래 메시지(🔔/❓/⚠️/🛑)와 시각 분리.

### 호출 예시 (보강)

```bash
curl -X POST http://localhost:8080/notify \
  -H "Authorization: Bearer $CAPTAIN_NOTIFY_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"text": "digest 완료", "source": "news_intel", "parse_mode": "HTML"}'
```

### Unit test 보강

```python
async def test_notify_auth_fail(client):
    r = await client.post("/notify", json={"text": "x"})
    assert r.status_code == 401

async def test_notify_publish_event(client, mock_event_bus):
    r = await client.post(
        "/notify",
        headers={"Authorization": "Bearer test_secret"},
        json={"text": "hello", "source": "test"},
    )
    assert r.status_code == 200
    # mock_event_bus.publish 호출 1회 + AgentResponseEvent type + text "📡 [test] hello"
    mock_event_bus.publish.assert_called_once()
    event = mock_event_bus.publish.call_args[0][0]
    assert event.text.startswith("📡 [test]")
```

"""TelegramBot — chat_id 인증 게이트 + 발신 모드 태그 + webhook 멱등성 검증."""


def _update(chat_id, text="/help", update_id=None):
    u = {"message": {"chat": {"id": chat_id}, "text": text}}
    if update_id is not None:
        u["update_id"] = update_id
    return u


def test_unregistered_chat_is_ignored(bot, sender):
    handled = bot.handle_update(_update(999))
    assert handled is False
    assert sender.sent == []  # 미등록 chat_id 에는 아무것도 보내지 않는다


def test_registered_chat_gets_reply_with_mode_tag(bot, sender):
    handled = bot.handle_update(_update(42))
    assert handled is True
    assert len(sender.sent) == 1
    chat_id, text = sender.sent[0]
    assert chat_id == 42
    assert text.startswith("[모의]")  # 기본 모드 virtual


def test_send_message_is_always_tagged(bot, sender):
    bot.send_message("테스트")
    assert sender.sent[0][1].startswith("[모의]")


def test_missing_chat_id_is_unauthorized(bot):
    assert bot.is_authorized(None) is False


def test_duplicate_update_is_processed_once(bot, sender):
    # Telegram 이 같은 update 를 재전송해도(느린 응답·cold-start) 명령은 1회만 처리·응답한다.
    dup = _update(42, "/status", update_id=777)
    assert bot.handle_update(dup) is True       # 첫 수신 — 처리
    assert bot.handle_update(dup) is False      # 재전송 — 무시
    assert len(sender.sent) == 1                # 응답 메시지는 정확히 1개


def test_distinct_update_ids_each_processed(bot, sender):
    # 멱등성 게이트가 서로 다른 update 까지 막아버리면 안 된다.
    assert bot.handle_update(_update(42, "/status", update_id=1)) is True
    assert bot.handle_update(_update(42, "/status", update_id=2)) is True
    assert len(sender.sent) == 2


def test_update_without_id_still_processed(bot, sender):
    # update_id 가 없는 비정상/구버전 페이로드는 dedup 을 건너뛰고 정상 처리(폴백).
    assert bot.handle_update(_update(42, "/help")) is True
    assert len(sender.sent) == 1

"""TelegramBot — chat_id 인증 게이트 + 발신 모드 태그 검증."""


def _update(chat_id, text="/help"):
    return {"message": {"chat": {"id": chat_id}, "text": text}}


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

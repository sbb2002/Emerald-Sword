-- 002_processed_updates: Telegram webhook 멱등성(중복 처리·중복 발신 방지)
-- 단일 진실 원천: blueprints/PRD_momentum_bot.md (TelegramBot 절)
--
-- Telegram 은 webhook 응답이 느리면(특히 Render free-tier cold-start + /status 의
-- 다중 KIS 호출 throttle) 같은 update 를 재전송한다. 그러면 같은 명령이 두 번 처리되어
-- 응답 메시지가 두 번 발송된다. update_id 를 1회만 통과시키기 위해 처리 이력을 기록한다.

CREATE TABLE IF NOT EXISTS processed_updates (
    update_id    BIGINT PRIMARY KEY,         -- Telegram update_id (계정 전역 단조 증가)
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

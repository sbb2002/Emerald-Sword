-- 004_trade_nav: trade_log 에 거래 전후 총자산(NAV) 컬럼 추가.
-- 단일 진실 원천: blueprints/PRD_momentum_bot.md (User Story 10 — "잔고 변화" 통보)
--
-- 기존 balance_before/after 는 get_cash()=주문가능 외화현금(USD)만이라, 원화 자동환전
-- 모의계좌에서는 환전 전 원화 매수여력이 빠져 총자산과 어긋나 보인다(혼란의 원인).
-- 통화 모호성이 없는 총자산(NAV=보유 평가금액+현금)을 별도로 기록해 /log·사후보고가
-- '총자산 + 현금'을 함께 보여줄 수 있게 한다. (소급 안 됨 — 기존 행은 NULL → 표시 생략)

ALTER TABLE trade_log ADD COLUMN IF NOT EXISTS nav_before NUMERIC(18, 4);
ALTER TABLE trade_log ADD COLUMN IF NOT EXISTS nav_after  NUMERIC(18, 4);

-- 001_init: Phase A 워킹 스켈레톤 스키마
-- 단일 진실 원천: blueprints/PRD_momentum_bot.md (StateStore 절)
-- 포지션은 저장하지 않는다(PositionService가 KIS API로 실시간 조회).

-- 전역 상태(싱글톤 행): is_paused, trading_mode
CREATE TABLE IF NOT EXISTS bot_state (
    id            SMALLINT PRIMARY KEY DEFAULT 1,
    is_paused     BOOLEAN NOT NULL DEFAULT FALSE,
    trading_mode  TEXT NOT NULL DEFAULT 'virtual'
                  CHECK (trading_mode IN ('virtual', 'real')),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT bot_state_singleton CHECK (id = 1)
);
INSERT INTO bot_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- 거래 로그 (체결가·수량·사유·시각·모드)
CREATE TABLE IF NOT EXISTS trade_log (
    id              BIGSERIAL PRIMARY KEY,
    executed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    mode            TEXT NOT NULL CHECK (mode IN ('virtual', 'real')),
    signal          TEXT,                       -- NASDAQ | GOLD | CASH
    side            TEXT,                       -- BUY | SELL
    ticker          TEXT,                       -- QQQM | GLDM
    quantity        INTEGER,
    fill_price      NUMERIC(18, 4),
    reason          TEXT,                       -- monthly_signal | emergency_stop | ...
    balance_before  NUMERIC(18, 4),
    balance_after   NUMERIC(18, 4),
    details         JSONB
);
CREATE INDEX IF NOT EXISTS idx_trade_log_executed_at ON trade_log (executed_at DESC);

-- 승인 상태 기계 (PENDING/APPROVED/REJECTED/EXPIRED/RE_REQUESTED)
CREATE TABLE IF NOT EXISTS approvals (
    id            BIGSERIAL PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind          TEXT NOT NULL,                -- outlier | large_order | signal
    status        TEXT NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'RE_REQUESTED')),
    signal        TEXT,
    payload       JSONB,
    expires_at    TIMESTAMPTZ,
    responded_at  TIMESTAMPTZ,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals (status);

-- 마지막 계산 신호 스냅샷 (싱글톤 행)
CREATE TABLE IF NOT EXISTS last_signal (
    id            SMALLINT PRIMARY KEY DEFAULT 1,
    signal        TEXT,                         -- NASDAQ | GOLD | CASH
    score_nasdaq  NUMERIC(12, 6),
    score_gold    NUMERIC(12, 6),
    computed_at   TIMESTAMPTZ,
    CONSTRAINT last_signal_singleton CHECK (id = 1)
);
INSERT INTO last_signal (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

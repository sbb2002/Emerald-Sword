-- 003_cash_flows: 입출금 기록 (수익률 TWR/CAGR 계산의 기준)
-- 단일 진실 원천: blueprints/PRD_momentum_bot.md
--
-- 자금을 주기적으로 추가하는 운용에서 단순 (총자산−총입금)/총입금 은 입금 타이밍을
-- 무시해 왜곡된다. 입출금 시점의 NAV(nav_before)를 기록해 두면 시간가중수익률(TWR)을
-- 구간 분할로 계산할 수 있다(매일 스냅샷 불필요). 모드별로 자금이 분리되므로 mode 컬럼을 둔다.

CREATE TABLE IF NOT EXISTS cash_flows (
    id           BIGSERIAL PRIMARY KEY,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    mode         TEXT NOT NULL CHECK (mode IN ('virtual', 'real')),
    amount       NUMERIC(18, 4) NOT NULL CHECK (amount > 0),   -- 항상 양수, 방향은 direction 으로
    direction    TEXT NOT NULL CHECK (direction IN ('deposit', 'withdraw')),
    nav_before   NUMERIC(18, 4) NOT NULL,                      -- 입출금 직전 총자산(USD) — TWR 구간 분할 기준
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_cash_flows_mode_time ON cash_flows (mode, occurred_at);

-- 모의계좌 초기 시드 $100,000 (nav_before=0 → TWR 기준점). 실전 자금은 /deposit 으로 기록한다.
INSERT INTO cash_flows (mode, amount, direction, nav_before, note)
VALUES ('virtual', 100000, 'deposit', 0, '모의 초기 시드 $100k');

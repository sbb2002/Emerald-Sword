# 모의투자(Virtual) 검증 테스트 가이드

> **목적**: 이 봇을 **모의투자 모드로 처음부터 끝까지 검증**하기 위한 순서별 실행 런북.
> 각 단계는 **🧰 준비 → ▶️ 실행 → ✅ 검증** 으로 나뉜다. 위에서 아래로 순서대로 진행한다.
>
> - 계정·키 발급(사람의 사전 준비): [`blueprints/SETUP_사용자_준비절차.md`](../blueprints/SETUP_사용자_준비절차.md)
> - 현재 구현 상태 스냅샷(검증된 것/미검증/설계 결정): [`docs/reports/`](reports/)
>
> 명령 예시는 Windows PowerShell 기준이다(레포 루트에서 실행). bash 는 주석으로 병기.

---

## 전체 흐름 한눈에

```
0 준비물  →  1 로컬세팅  →  2 자동테스트  →  3 DB 마이그레이션
        →  4 KIS 어댑터 라이브 검증 (★ 모의 주문의 전제)
        →  5 봇 구동(배포 or 로컬)  →  6 명령 스모크  →  7 cron 1사이클
        →  8 완료 기준 충족 → 모의검증 끝
```

---

## 0. 준비물 체크리스트

🧰 **준비**
- [ ] SETUP §1~4 완료, 아래 값 확보(모의 검증엔 **PAPER/모의** 값이 핵심):
  - `KIS_APP_KEY`, `KIS_APP_SECRET`
  - `KIS_BASE_URL_PAPER`(모의 도메인), `KIS_CANO_PAPER`(모의 계좌번호), `KIS_ACNT_PRDT_CD`(보통 `01`)
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`(내 숫자 chat_id)
  - `DATABASE_URL`(Neon, 빈 DB 가능)
- [ ] 로컬에 **Python 3.13** + git
- [ ] (§5-A 텔레그램 명령 검증 시) Render 계정 — webhook 은 공개 URL 이 필요하다

> 실전(REAL) 값은 이 단계에선 필요 없다. 모의검증이 끝난 뒤 승격할 때 채운다.

---

## 1. 로컬 환경 세팅

▶️ **실행**
```powershell
git clone <레포 URL> ; cd emerald-sword
git switch phase-c/telegram-commands       # 전체 기능이 들어있는 브랜치
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt        # 테스트 포함(런타임은 requirements.txt)
Copy-Item .env.example .env                # 그리고 .env 값 채우기
# bash:  source .venv/Scripts/activate ; cp .env.example .env
```
`.env` 에 **최소한** 다음을 채운다(따옴표 없이):
```
DATABASE_URL=postgresql://...:...@.../...?sslmode=require
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_BASE_URL_PAPER=...        # 모의 도메인
KIS_CANO_PAPER=...            # 모의 계좌번호
KIS_ACNT_PRDT_CD=01
```

✅ **검증**
- [ ] `.env` 에 위 PAPER 값들이 채워졌다(비밀값은 절대 커밋하지 않는다 — `.env` 는 `.gitignore` 대상)

---

## 2. 로컬 자동 테스트 (로직 회귀 확인)

▶️ **실행**
```powershell
python -m pytest
```

✅ **검증**
- [ ] `83 passed, 1 skipped` (skip 1건은 실데이터 CSV 부재 — 정상). 실패가 있으면 코드 회귀이니 먼저 해결.

---

## 3. DB 마이그레이션

🧰 **준비**: `.env` 의 `DATABASE_URL`(Neon).

▶️ **실행**
```powershell
python -m src.migrate
```

✅ **검증**
- [ ] "적용된 마이그레이션: 001_init.sql" 또는 "최신 상태" 출력
- [ ] Neon 콘솔에 `bot_state`·`trade_log`·`approvals`·`last_signal` 테이블 생성, `bot_state.trading_mode` 기본값 `virtual`

---

## 4. KIS 어댑터 라이브 검증 (모의) — ★ 모의 주문의 전제

봇 로직은 테스트로 검증됐지만, `src/kis_client.py` 의 **실제 KIS REST 호출**(엔드포인트·`tr_id`·응답 필드명)은 모의 서버에서 1회 확인해야 한다. 이게 안 되면 `/status`·`/signal`·cron 주문이 실패한다.

🧰 **준비**: `.env` 의 PAPER 값. **토큰은 분당 1회 발급 제한** — 재발급을 남발하지 말 것.

▶️ **실행 (1) 읽기 경로** — 레포 루트에서 `python` REPL:
```python
from src.config import get_settings
from src.kis_client import build_kis_client
kis = build_kis_client(get_settings(), "virtual")
kis.issue_token()                              # 토큰 1회 발급
print("cash  =", kis.get_cash())               # 주문가능 외화현금
print("price =", kis.get_price("QQQM"))        # 현재가
print("daily =", kis.get_daily_closes("QQQM", 30)[:3])  # 일별 종가(최신순)
```

✅ **검증 (1)**
- [ ] 토큰 발급에 예외가 없다
- [ ] `get_cash()` 가 숫자(주문가능 외화현금)
- [ ] `get_price("QQQM")` 가 양수
- [ ] `get_daily_closes` 가 `DailyClose(date, close)` 리스트를 최신순으로 충분히 반환(월말 추출에 13개월≈300거래일 필요)

> **실패하면 여기만 고친다** — `src/kis_client.py`:
>
> | 안 되는 것 | 확인/수정 위치 |
> |---|---|
> | 잔고·현금 필드가 빔 | `get_holdings`/`get_cash` 의 `ovrs_cblc_qty`·`frcr_ord_psbl_amt1` 등 필드명, `_TR[...]["balance"]` tr_id |
> | 현재가 0 | `get_price` 의 `output.last`, `_PRICE_TR`, `_EXCG`(거래소코드) |
> | 일별 종가 빔 | `get_daily_closes` 의 `output2`/`xymd`/`clos`, `_DAILY_TR` |
>
> 로직 계층(MomentumEngine·OrderExecutor 등)은 `KisClient` *인터페이스* 에만 의존하므로 **어댑터만 고치면** 상위 로직·테스트는 그대로다.

▶️ **실행 (2) 주문 경로** — 읽기가 통과한 뒤에만:
```python
print(kis.place_order("QQQM", "BUY", 1))       # 모의 소량 매수
print(kis.get_open_orders())
```

✅ **검증 (2)**
- [ ] `OrderResult.accepted == True`(KIS `rt_cd == "0"`)
- [ ] (선택) `get_executions(order_id)` 체결 수량 — 현재 **스텁(0 반환)**. cron 정산까지 완전 검증하려면 `inquire-ccnl` 응답 매핑을 채워야 한다(리포트 §1 참조).

---

## 5. 봇 구동

텔레그램 명령(§6)을 검증하려면 webhook 이 닿을 **공개 URL** 이 필요하다 → **5-A 배포** 경로. cron 만 빠르게 보려면 **5-B 로컬** 으로 충분하다.

### 5-A. Render 배포 (텔레그램 명령 검증용)
▶️ **실행**
1. `render.yaml` Blueprint 로 배포(연결 브랜치 = `phase-c/telegram-commands`).
2. `emerald-sword-secrets` env 그룹에 §0 값 입력(여기에 실전 값은 비워도 모의검증엔 무방).
3. webhook 등록(봇 토큰을 경로에 그대로):
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<your-host>/webhook/<BOT_TOKEN>
   ```
4. UptimeRobot 으로 `https://<your-host>/healthcheck` 5분 핑.

✅ **검증**
- [ ] `GET /healthcheck` → `{"status":"ok"}`
- [ ] 봇에 `/help` → **`[모의]`** 태그와 함께 명령어 목록이 온다

### 5-B. cron 로컬 1회 (텔레그램 명령 없이)
▶️ **실행**
```powershell
python -m src.cron
```
✅ **검증**: §7 과 동일(텔레그램으로 사이클 보고 도착).

---

## 6. 텔레그램 명령 스모크 테스트 (5-A 배포 후, 순서대로)

각 항목을 텔레그램에서 직접 입력하고 기대 동작을 확인한다. (y/n·코드는 `/` 로 시작하지 않는 일반 메시지로 입력)

- [ ] `/status` → 상단 `[모의]` + 보유·현금·다음거래 잔고부족·**서버: 정상**
- [ ] `/signal` → 예상 신호(NASDAQ/GOLD/CASH) + 두 점수
- [ ] `/log` → 거래 전이면 "거래 내역이 없습니다."
- [ ] `/pause` → "(y/n)" → `y` → 일시정지. 직후 `/status` 로 확인. 다시 `/pause` → "이미 일시정지 상태입니다."
- [ ] `/resume` → 재개. 다시 `/resume` → "이미 작동 중입니다."
- [ ] `/virtual` → 이미 모의면 "이미 모의투자 모드입니다."
- [ ] `/real` → 코드 제시 → **틀린 코드** 입력 → 거부(모드 불변) 확인
- [ ] `/emergency-stop` → "(y/n)" → `y` → 코드+60초 → **코드 입력** → 청산 시도 + 자동 일시정지 → `/log` 에 `⚠️비상청산` 표시(보유 없으면 "청산할 보유 종목이 없었습니다")
  - [ ] **타임아웃 별도 확인**: `/emergency-stop` → `y` → 코드를 **60초 넘겨** 입력 → "시간이 초과되어 청산이 취소되었습니다."
- [ ] **펜딩 취소 규칙**: `/pause` 직후 `y` 대신 `/status` 입력 → 이전 확인이 취소되고 `/status` 가 실행됨(일시정지 안 됨)
- [ ] **오류 격리**: (예: KIS 키를 일시적으로 틀리게 두고) `/signal` → 봇이 죽지 않고 "⚠️ 명령 처리 중 오류가 발생했습니다…" 친절 응답
- [ ] 테스트 후 `/resume` 으로 일시정지 해제, 모드가 `virtual` 인지 `/status` 로 확인

---

## 7. cron 자동 사이클 검증 (모의)

🧰 **준비**: `bot_state.trading_mode = virtual`, `is_paused = false`(`/resume` 상태).

▶️ **실행**: Render cron 서비스 **Run now**, 또는 로컬 `python -m src.cron`.

✅ **검증** (텔레그램 보고로 확인)
- [ ] `is_paused=True` 면 "일시정지 중 — 사이클 건너뜀" 보고
- [ ] `is_paused=False` 면 신호 산출 → 직전과 같으면 "변동 없음(무거래)", 다르면 **2-leg 전환 보고**(매도/매수 + 잔고 변화)
- [ ] ⚠️ `get_executions` 스텁이면 "미완료(INCOMPLETE)" 로 보고될 수 있음 → §4 검증(2)에서 체결 매핑을 채우면 해소(리포트 §1)

---

## 8. 모의검증 완료 기준 (Definition of Done)

아래가 모두 통과하면 **모의검증 완료**. 실전(real) 승격은 별도 절차(리포트 부록 B)다.

- [ ] §2 `pytest` 통과 (`83 passed`)
- [ ] §3 마이그레이션 적용, 기본 모드 `virtual`
- [ ] §4 KIS 읽기 3종 + 모의 주문 1회 성공
- [ ] §5-A `/help` 응답(또는 §5-B cron 보고)
- [ ] §6 명령 스모크 전 항목
- [ ] §7 cron 1 사이클 정상 보고

> 막히면 → 리포트 [`docs/reports/phase-c-telegram-commands_2026-06-16.md`](reports/phase-c-telegram-commands_2026-06-16.md) §8 트러블슈팅, 또는 Render 서버 로그(명령 실패 스택은 거기 남는다).

---

## 부록 — `.env` / Render 환경변수 (모의검증 기준)

```
# 필수
DATABASE_URL=postgresql://...:...@.../...?sslmode=require
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
# KIS 모의(PAPER) — 모의검증의 핵심
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_BASE_URL_PAPER=...
KIS_CANO_PAPER=...
KIS_ACNT_PRDT_CD=01
# KIS 실전(REAL) — 모의검증 단계에선 비워도 됨(승격 시 채움)
KIS_BASE_URL_REAL=
KIS_CANO_REAL=
```
> `trading_mode`(virtual/real)는 환경변수가 아니라 **DB** 에 저장된다. 기본 `virtual`, `/real`·`/virtual` 로 전환.
> 비밀값은 코드·git 에 절대 두지 않는다(전부 `.env` 로컬 또는 Render 환경변수).

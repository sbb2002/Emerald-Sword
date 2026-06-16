# 프로젝트 상태 리포트 — Phase C (`phase-c/telegram-commands`, 2026-06-16)

> **이 문서**: Phase A·B·C 구현 완료 시점의 **상태 스냅샷 리포트** — 검증된 것 / 라이브 검증이 필요한 것 / 배포 브랜치 / 안전장치 / 설계 결정의 근거를 기록한다.
> 실제로 모의검증을 *수행*하는 순서별 런북은 [`docs/USER_MANUAL.md`](../USER_MANUAL.md) 를, 사람의 사전 준비(계정·키 발급)는 [`blueprints/SETUP_사용자_준비절차.md`](../../blueprints/SETUP_사용자_준비절차.md) 를 참조.
> 아래 본문의 "§n" 절 참조와 "이 매뉴얼" 표현은 작성 시점 기준이며 본 리포트 내부를 가리킨다. 또한 SETUP 링크 경로는 `../../blueprints/...` 로 읽는다(리포트가 `docs/reports/` 하위로 이동).

---

## 0. 한눈에 — SETUP 만으로 충분한가?

| 단계 | 어디서 | 상태 |
|---|---|---|
| 계정·키·DB·배포·webhook·환전 준비 | SETUP 문서 1~8 | ✅ 그대로 따르면 됨 |
| 배포할 **브랜치** 선택 | 이 매뉴얼 §2 | ⚠️ main 미반영(스택 상태) |
| **KIS 어댑터 라이브 검증** | 이 매뉴얼 §4 | ⚠️ **모의투자 전 필수** — 아직 미검증 |
| 모의투자 테스트 시나리오 | 이 매뉴얼 §5~6 | ✅ 본 문서 제공 |

**결론**: SETUP 의 사전 준비는 끝내되, **실제로 모의 주문이 나가려면 §4(KIS 어댑터 검증)를 반드시 먼저** 통과해야 한다. 그 전까지 `/status`·`/signal`·cron 주문은 실패할 수 있다.

---

## 1. 지금 되는 것 / 검증이 필요한 것 (정직한 상태)

### ✅ 검증된 것 (테스트 81 passed, 1 skipped)
- **전략 로직**: 모멘텀 신호 산출, 2-leg 전환 멱등성, 부분체결 재시도, 승인 상태기계, 폴백 분기.
- **명령 상태머신**: `/status`·`/signal`·`/log`·`/pause`·`/resume`·`/virtual`·`/real`·`/emergency-stop` 의 다중턴 확인·챌린지·60초 타임아웃.
- **모드 태그·인증 게이트·DB 영속**(`is_paused`·`trading_mode`·`trade_log`).
- 이 검증들은 KIS·텔레그램·DB 를 **mock 으로 대체**한 것 — *로직*은 옳지만 *실제 외부 호출*은 별개다(아래).

### ⚠️ 라이브 검증이 필요한 것 (모의투자의 전제)
- **`src/kis_client.py` 의 KIS REST 호출**: 엔드포인트 경로·`tr_id`·응답 필드명(`ovrs_cblc_qty`, `frcr_ord_psbl_amt1`, `ODNO` 등)이 KIS 문서 기준 **최종 확인 전**이다. 모의투자 잔고조회/시세/주문이 실제로 성공하는지 §4 에서 1회 확인해야 한다.
- **`get_executions`(체결 조회)** 는 현재 **스텁**(항상 `filled_qty=0`). 이대로면 cron 의 2-leg 정산이 "미체결"로 보고될 수 있다(→ `INCOMPLETE`). `/status`·`/signal`·`/emergency-stop` 의 *읽기/주문 접수* 에는 영향이 적지만, **cron 자동매매 사이클의 완결 보고**에는 영향이 있다.
- **cron 스케줄**: `render.yaml` 은 `30 15 28-31 * *`(매일 UTC 15:30=KST 00:30, 월말 근사). "월 마지막 거래일 + 미국 DST" 게이트는 미구현. 모의 테스트엔 무방하나 실운영 전 보강 권장.

> 요약: **"봇이 무엇을 결정하는가"는 검증됐고, "KIS 에 어떻게 말 거는가"는 아직 미검증.** §4 가 그 간극을 메운다.

---

## 2. 배포할 브랜치

현재 Phase A·B·C 는 **스택 브랜치**로 있고 `main` 에는 아직 머지되지 않았다.

- `phase-a/skeleton` → `phase-b/momentum-engine` → `phase-c/telegram-commands` (이 브랜치가 **전체 포함**)

**두 가지 선택지:**

| 방식 | 절차 | 권장 |
|---|---|---|
| **A. main 정리 후 배포** | PR #15→#16→#17 순서로 머지(또는 base 재타깃)해 `main` 에 A+B+C 반영 → Render 를 `main` 에 연결 | ✅ 운영용 |
| **B. 브랜치 직접 배포** | Render Blueprint 를 `phase-c/telegram-commands` 에 연결(빠른 모의 테스트) | 테스트용 |

> Render Blueprint 는 연결한 브랜치를 배포한다. 테스트만 빠르게 하려면 B, 정식 운영은 A.

---

## 3. 배포 (SETUP 1~8 완료 가정)

1. **requirements 확인**: 빌드는 `pip install -r requirements.txt`(web·cron 공통, `render.yaml`).
2. **Blueprint 배포**: `render.yaml` 로 `emerald-sword-web`(web) + `emerald-sword-cron`(cron) 두 서비스 생성.
   - 진입점: web = `uvicorn src.web:app`, cron = `python -m src.cron`.
   - 시작 시 DB 마이그레이션이 **자동 실행**된다(빈 Neon DB 면 됨).
3. **환경변수**: `emerald-sword-secrets` 그룹에 부록 표의 값 입력(코드·git 금지).
4. **텔레그램 webhook 등록** — 경로는 **봇 토큰을 그대로 경로에** 넣는다(경로 비밀):
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<your-host>/webhook/<BOT_TOKEN>
   ```
   `<your-host>` = web 서비스 공개 도메인(예: `emerald-sword-web.onrender.com`).
5. **keep-alive**: UptimeRobot HTTP 모니터를 `https://<your-host>/healthcheck` 에 5분 간격으로.
6. **연결 확인**: 봇에게 `/help` → 명령어 목록이 `[모의]` 태그와 함께 오면 성공.

---

## 4. KIS 어댑터 라이브 검증 — 모의투자 전 **필수**

`/status`·`/signal`·cron 주문이 실제로 동작하려면 `src/kis_client.py` 의 호출이 KIS 모의투자(VTS) 서버에서 실제로 200 응답하고, 응답을 코드가 올바른 필드로 파싱하는지 확인해야 한다.

### 4.1 무엇을 확인하나
| KIS 호출 | 코드 메서드 | 쓰는 명령 |
|---|---|---|
| 잔고/현금 조회 (`inquire-balance`) | `get_holdings` / `get_cash` | `/status`, 주문 수량 계산 |
| 현재가 (`quotations/price`) | `get_price` | `/status` 잔고부족 판정, 매수 수량 |
| 일별 종가 (`quotations/dailyprice`) | `get_daily_closes` | `/signal`, cron 모멘텀 |
| 주문 (`trading/order`) | `place_order` | cron 매매, `/emergency-stop` 청산 |
| 미체결 (`inquire-nccs`) | `get_open_orders` | 멱등성 |
| 체결 (`inquire-ccnl`) | `get_executions` ⚠️스텁 | cron 정산 |

### 4.2 빠른 검증 방법 (로컬)
1. `.env` 에 **모의투자(PAPER)** 값을 채운다: `KIS_APP_KEY/SECRET`, `KIS_BASE_URL_PAPER`, `KIS_CANO_PAPER`, `KIS_ACNT_PRDT_CD`.
2. 로컬 파이썬에서 모의 클라이언트로 읽기부터 확인:
   ```python
   from src.config import get_settings
   from src.kis_client import build_kis_client
   kis = build_kis_client(get_settings(), "virtual")
   kis.issue_token()                 # 토큰 1회 발급(분당 1회 제한 주의)
   print(kis.get_cash())             # 주문가능 외화현금이 숫자로 오는가
   print(kis.get_price("QQQM"))      # 현재가가 양수로 오는가
   print(kis.get_daily_closes("QQQM", 30)[:3])  # 일별 종가가 최신순으로 오는가
   ```
3. 값이 비거나 KeyError·HTTP 오류가 나면 → 해당 메서드의 **엔드포인트/`tr_id`/필드명**을 KIS 개발자센터 문서로 맞춘다. 고치는 곳은 `src/kis_client.py` 상단 `_TR`·`_EXCG`·`_PRICE_TR`·`_DAILY_TR` 와 각 메서드의 `.get("필드명")` 부분.
4. 읽기가 되면 **모의 주문 1회**(소량 BUY)를 `place_order` 로 시도해 접수(`rt_cd=="0"`)를 확인.

> **중요**: 로직 계층(MomentumEngine·OrderExecutor 등)은 `KisClient` *인터페이스* 에만 의존한다. 따라서 **어댑터(`kis_client.py`)만 고치면** 상위 로직·테스트는 건드릴 필요가 없다. 토큰은 **1분당 1회** 제한이 있으니 재발급을 남발하지 말 것.

---

## 5. 모의투자(virtual) 테스트 시나리오

§3 배포 + §4 검증이 끝났다면, 아래 순서로 모의 운용을 검증한다.

### 5.1 명령 스모크 테스트 (텔레그램에서)
- [ ] `/status` → 상단에 **`[모의]`** 태그 + 보유·현금·서버 상태. ("서버: 오류" 면 §4 미검증/키·URL 문제)
- [ ] `/signal` → 현재 기준 예상 신호(NASDAQ/GOLD/CASH) + 두 점수.
- [ ] `/log` → 아직 거래 없으면 "거래 내역이 없습니다."
- [ ] `/pause` → "(y/n)" 재확인 → `y` → 일시정지. `/status` 재확인.
- [ ] `/resume` → 재개.
- [ ] `/virtual` → 이미 모의면 "이미 모의투자 모드입니다."
- [ ] `/real` → 코드 제시 → **틀린 코드** 입력 → 거부(모드 불변) 확인 → 다시 `/virtual` 로 복귀.
- [ ] `/emergency-stop` → "(y/n)" → `y` → 코드+60초 → 코드 입력 → 청산 시도 + 자동 일시정지. `/log` 에 `⚠️비상청산` 표시 확인. (보유가 없으면 "청산할 보유 종목이 없었습니다")
- [ ] 테스트 후 `/resume` 으로 일시정지 해제.

### 5.2 cron 자동 사이클 1회 검증
모의 모드에서 월말 사이클을 직접 돌려본다.
- 로컬: `python -m src.cron` (DB의 `is_paused`·`trading_mode` 읽고, 모멘텀 계산 → 모의 주문 → 텔레그램 보고).
- Render: cron 서비스에서 **Run now** (또는 스케줄 도달 대기).
- 기대: `is_paused=True` 면 "일시정지 중 건너뜀" 보고 / `False` 면 신호 산출 → (직전과 같으면) 무거래 보고 또는 2-leg 전환 보고.
- ⚠️ `get_executions` 스텁 때문에 "미완료(INCOMPLETE)" 로 보고될 수 있다(§1). 모의에서 정산까지 완전 검증하려면 이 메서드도 §4 로 채워야 한다.

---

## 6. 텔레그램 명령 레퍼런스 (현재 구현 그대로)

| 명령 | 동작 | 확인 절차 |
|---|---|---|
| `/help`, `/start` | 명령어 목록 | — |
| `/status` | 보유·현금·다음거래 잔고부족·서버상태 (상단 모드 태그) | — |
| `/signal` | 지금 시점 기준 예상 신호 + NASDAQ/GOLD 점수 | — |
| `/log [N]` | 최근 N개(없으면 전체) 거래 최신순. 비상청산은 `⚠️비상청산` 표시 | — |
| `/pause` | 자동거래 일시정지 | **y/n 재확인** 후 `y` |
| `/resume` | 재개 | 즉시 |
| `/virtual` | 모의 모드 전환 | **y/n** 후 `y` |
| `/real` | 실전 모드 전환 | **봇 제시 코드를 그대로 입력** |
| `/emergency-stop` | 전량 청산 후 자동 일시정지 | **y/n → 코드(60초 내)** |

**공통 규칙**
- **인증 게이트**: 등록된 `TELEGRAM_CHAT_ID` 에서 온 명령만 처리, 그 외 무시.
- **모드 태그**: 모든 발신 머리에 `[모의]`/`[실전]`. `/real` 성공 직후 메시지부터 `[실전]`.
- **펜딩 취소**: 확인(y/n·코드) 대기 중에 **새 `/명령`** 을 보내면 이전 확인은 **취소**되고 새 명령이 실행된다(오발 방지). y/n·코드는 `/` 로 시작하지 않는 일반 메시지로 입력.
- **확인 응답**: `y`/`yes` 만 승인. 그 외(또는 `n`)는 취소.
- **emergency-stop 60초**: 코드가 60초를 넘기면 정확한 코드라도 거부(자동 취소). 다시 `/emergency-stop` 부터.

---

## 7. 안전장치 요약 (왜 안심하고 모의 테스트해도 되는가)

- **기본 모드 `virtual`**: DB 기본값이 모의. `/real` 은 챌린지-응답 없이는 절대 전환 안 됨.
- **`is_paused` 게이트**: `/pause` 시 cron 이 다음 기상 때 **사이클 전체를 스킵**(KIS 주문취소 API 가 없어, "안 깨우는" 방식으로 멈춘다).
- **emergency-stop early-pause**: 청산 주문 *전에* 먼저 일시정지 → 청산 도중 장애가 나도 다음 월말 **재매수가 차단**된다. `/status`(KIS 실시간 조회)로 실제 잔고를 언제든 확인 가능.
- **멱등성**: 목표 보유 시 매수 스킵 + 미체결 동일주문 재주문 스킵 → 재실행·재시도해도 이중 주문 없음.
- **정수 주문 / 무캐시 포지션**: 소수점 미사용, 포지션은 항상 KIS 실시간 조회(봇 메모리 불신).
- **명령 실패 격리**: KIS·네트워크 오류가 나도 webhook 은 항상 200(텔레그램 재시도 폭주 방지), 사용자에겐 친절한 오류 메시지로 응답하고 원인 스택은 **Render 로그**에 남는다.

---

## 8. 트러블슈팅

| 증상 | 원인 후보 | 조치 |
|---|---|---|
| `/help` 무응답 | webhook 미등록 / spin-down / 경로 오타 | §3-4 webhook URL 재등록, UptimeRobot 확인, 경로는 `/webhook/<BOT_TOKEN>` |
| 명령은 되는데 `/status` 가 "서버: 오류" | KIS 어댑터 미검증 / 키·URL 오류 | §4 라이브 검증 |
| `/signal`·`/status` 가 "오류가 발생했습니다" 응답 | KIS 호출 실패(미검증·키·URL) 또는 월말 종가 13개 미만 | §4 검증. 상세 스택은 **Render 로그** 확인 |
| cron 이 "미완료(INCOMPLETE)" 보고 | `get_executions` 스텁(체결 0) | §1·§4 — 체결 조회 매핑 구현 |
| 토큰 발급 차단 | 1분당 1회 제한 초과(테스트 중 잦은 재발급) | 잠시 대기 후 재시도, 재발급 남발 금지 |
| 타인이 명령? | 인증 게이트로 무시됨 | `TELEGRAM_CHAT_ID` 정확히 입력됐는지 |

---

## 부록 A — 환경변수 (Render `emerald-sword-secrets` 그룹, 코드·git 금지)

```
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_CHAT_ID=123456789
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_CANO_REAL=...            # 실전 계좌번호
KIS_CANO_PAPER=...           # 모의투자 계좌번호
KIS_ACNT_PRDT_CD=01
KIS_BASE_URL_REAL=...        # 실전 도메인
KIS_BASE_URL_PAPER=...       # 모의투자 도메인
```
> `trading_mode`(virtual/real)는 환경변수가 아니라 **DB** 에 저장된다. 기본 `virtual`, `/real`·`/virtual` 로 전환.

## 부록 B — 모의 → 실전 승격 순서

1. 모의(virtual)에서 §5 스모크 + cron 1 사이클 정상 확인.
2. §4 의 `place_order`·`get_executions` 까지 모의로 완전 검증.
3. 달러 잔고 충전(SETUP §8).
4. `/real` → 코드 입력으로 실전 전환(상단 `[실전]` 확인).
5. **소액으로 1 사이클 실거래** 후 확대.

> 실전 전환은 되돌릴 수 있다(`/virtual`). 의심스러우면 즉시 `/pause` 또는 `/emergency-stop`.

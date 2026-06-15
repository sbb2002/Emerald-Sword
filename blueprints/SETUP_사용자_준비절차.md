# 사용자 준비 절차서 — 복합모멘텀 QQQM/GLDM 봇

> **이 문서의 목적**: 봇 코드와 별개로, **사람인 당신이 직접 손으로 준비해야 하는 것들**만 모았다. 대부분 "계정 만들기·키 발급·콘솔에서 값 복사"처럼 자동화할 수 없는 작업이다. LLM이나 코드가 대신 해줄 수 없으니, 구현을 시작하기 전(또는 배포 직전)에 이 체크리스트를 끝내두면 막힘 없이 진행된다.
>
> **보안 원칙**: 이 문서에서 발급하는 모든 키·토큰·비밀번호는 **절대 코드나 GitHub에 직접 넣지 말 것.** 전부 Render의 환경변수(Environment Variables)에만 입력한다. 이 문서 자체에도 실제 키 값을 적어두지 말 것.

---

## 0. 준비물 한눈에 보기

| # | 항목 | 발급처 | 결과물(환경변수로 보관) |
|---|------|--------|------------------------|
| 1 | 한국투자증권 계좌 + Open API 신청 (실전+모의) | 한국투자증권 | App Key, App Secret, 실전/모의 계좌번호·URL |
| 2 | 텔레그램 봇 생성 | BotFather | Bot Token |
| 3 | 내 텔레그램 chat_id 확인 | 텔레그램 | chat_id (숫자) |
| 4 | Neon PostgreSQL 생성 | Neon | DB 연결 문자열(DATABASE_URL) |
| 5 | GitHub 레포 준비 | GitHub | 레포 URL |
| 6 | Render 계정 + Blueprint 배포 | Render | 두 서비스 배포 |
| 7 | UptimeRobot keep-alive 설정 | UptimeRobot | 5분 핑 모니터 |
| 8 | 초기 자금 + 수동 환전 | 한국투자증권 앱 | 달러 잔고 |

---

## 1. 한국투자증권 계좌 및 Open API 신청

봇이 실제 주문을 내려면 KIS Open API 사용 신청과 키 발급이 필요하다.

1. 한국투자증권 **계좌 개설**(이미 있으면 생략). 본 봇은 **일반 위탁계좌** 기준이다. ISA·연금저축 계좌는 API 주문 대상이 아니므로 사용하지 않는다.
2. 홈페이지 상단 **[트레이딩] → [Open API] → [KIS Developers]** 진입 후 API 사용 신청.
3. 신청 과정에서 **App Key**와 **App Secret**이 발급된다. 이 두 값을 안전하게 보관한다.
4. **계좌번호(CANO)**와 상품코드(ACNT_PRDT_CD, 보통 `01`)를 확인해둔다.
5. **모의투자(VTS) 신청도 함께** 해둔다. 봇은 `/virtual`·`/real` 명령으로 두 모드를 전환하므로, **실전과 모의투자 양쪽 계좌·URL이 모두 필요**하다.
   - 실전 BASE URL과 모의투자 BASE URL이 다르다(모의투자는 별도 도메인). **둘 다** 메모.
   - 모의투자 계좌번호(CANO)가 실전과 다를 수 있으니 각각 확인.
   - **모의투자 계좌는 주기적으로 초기화·만료될 수 있다.** 검증용으로만 쓰고, 장기 무인 운용은 실전(real) 모드로 한다.

> **확인 사항(직접 챙겨야 함)**
> - 미국주식 **소수점 주문은 API 미지원** → 봇은 정수 주문만. (이미 설계 반영됨)
> - 접근토큰은 24시간 유효, **발급 빈도 제한(1분당 1회)** 존재 → 봇은 사이클당 1회 발급. 당신이 테스트하며 토큰을 자주 재발급하면 일시 차단될 수 있으니 주의.
> - 2026년 이후 **초당 호출 제한**이 적용 중. 월 1회 저빈도 운영이라 문제는 없으나 인지.

**보관할 값**: `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_CANO_REAL`, `KIS_CANO_PAPER`, `KIS_ACNT_PRDT_CD`, `KIS_BASE_URL_REAL`, `KIS_BASE_URL_PAPER`
> 실전/모의는 App Key·Secret이 동일하게 쓰일 수도, 별도 발급될 수도 있다(신청 형태에 따라 다름). 발급 화면에서 모의투자용 키가 따로 나오면 `_PAPER` 접미사로 구분해 보관한다.

---

## 2. 텔레그램 봇 생성

봇이 당신에게 알림을 보내고 명령을 받으려면 텔레그램 봇 토큰이 필요하다.

1. 텔레그램에서 **@BotFather** 검색 후 대화 시작.
2. `/newbot` 입력 → 봇 이름과 사용자명(@로 끝나는 고유 ID) 지정.
3. 생성 완료 시 **Bot Token**(예: `123456:ABC-...` 형태)이 발급된다. 보관.

**보관할 값**: `TELEGRAM_BOT_TOKEN`

---

## 3. 내 텔레그램 chat_id 확인

봇이 **나에게만** 알림을 보내고, **나의 명령만** 받도록(인증 게이트) 하려면 내 chat_id가 필요하다.

1. 방금 만든 봇과 대화를 시작하고 아무 메시지나 한 번 보낸다(예: `hi`).
2. chat_id 확인 방법 중 하나:
   - 텔레그램에서 **@userinfobot** 에게 말을 걸면 내 숫자 chat_id를 알려준다, 또는
   - 브라우저에서 `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` 호출 → 응답 JSON의 `chat.id` 확인.
3. 이 chat_id(숫자)를 보관한다. 봇은 이 chat_id에서 온 명령만 처리한다.

**보관할 값**: `TELEGRAM_CHAT_ID`

---

## 4. Neon PostgreSQL 데이터베이스 생성

봇의 상태(`is_paused`), 거래 로그, 미응답 승인 상태를 영속 저장할 DB. **Render 무료 PostgreSQL은 30일 후 데이터가 삭제되므로 쓰지 않고, 무기한 무료인 Neon을 쓴다.**

1. **neon.tech** 가입(무료 티어).
2. 새 **Project / Database** 생성.
3. 대시보드의 **Connection String**(예: `postgresql://user:password@host/dbname?sslmode=require`)을 복사한다.
4. 이 연결 문자열을 보관한다. Render의 web service와 cron job **양쪽 모두**에 같은 값으로 넣을 것이다.

> **참고**: 테이블 생성(스키마)은 봇 코드의 마이그레이션이 담당하도록 만들 예정이라, 당신은 빈 DB와 연결 문자열만 준비하면 된다. (구현 시 결정)

**보관할 값**: `DATABASE_URL`

---

## 5. GitHub 레포지토리 준비

Render Blueprint 배포는 GitHub 레포에서 코드를 가져온다.

1. GitHub에 **새 레포**(private 권장) 생성.
2. 봇 코드와 `render.yaml`(Blueprint 정의)이 이 레포에 올라갈 것이다.
3. **주의**: 키·토큰·`historical_data.csv`의 민감 여부를 점검하고, 비밀 값은 절대 커밋하지 않는다. `.gitignore`에 `.env`, 토큰 캐시 파일 등을 추가.

**보관할 값**: 레포 URL

---

## 6. Render 계정 및 Blueprint 배포

두 서비스(web service + cron job)를 한 번에 띄운다.

1. **render.com** 가입 후 GitHub 레포 연결.
2. 레포의 `render.yaml`을 이용해 **Blueprint**로 배포하면 web service와 cron job이 함께 생성된다.
3. **환경변수 입력**: 두 서비스 각각(또는 공통 그룹)에 아래 값을 입력한다. **코드가 아니라 Render 대시보드의 Environment에만 입력.**

   | 환경변수 | 출처 | web | cron |
   |----------|------|:---:|:---:|
   | `KIS_APP_KEY` | 1번 | ✅ | ✅ |
   | `KIS_APP_SECRET` | 1번 | ✅ | ✅ |
   | `KIS_CANO_REAL` | 1번 | ✅ | ✅ |
   | `KIS_CANO_PAPER` | 1번 | ✅ | ✅ |
   | `KIS_ACNT_PRDT_CD` | 1번 | ✅ | ✅ |
   | `KIS_BASE_URL_REAL` | 1번 | ✅ | ✅ |
   | `KIS_BASE_URL_PAPER` | 1번 | ✅ | ✅ |
   | `TELEGRAM_BOT_TOKEN` | 2번 | ✅ | ✅ |
   | `TELEGRAM_CHAT_ID` | 3번 | ✅ | ✅ |
   | `DATABASE_URL` | 4번 | ✅ | ✅ |

   (web은 명령 응답·알림에, cron은 주문·알림에 각각 필요하므로 대부분 공통이다. 모드 전환을 위해 실전/모의 URL·계좌를 모두 넣어두고, 봇은 DB의 `trading_mode` 값에 따라 둘 중 하나를 선택한다. `trading_mode` 자체는 환경변수가 아니라 DB에 저장되며 `/virtual`·`/real`로 바뀐다.)
4. **텔레그램 webhook 등록**: web service가 배포되어 공개 URL(예: `https://yourbot.onrender.com`)이 생기면, 그 URL을 텔레그램 webhook으로 등록해야 한다.
   - 브라우저/터미널에서 `https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://yourbot.onrender.com/<webhook_path>` 호출.
   - (이 호출은 1회성. 코드에 자동화 로직을 둘 수도 있으나, 최초엔 직접 확인 권장.)
5. **cron 스케줄 확인**: `render.yaml`의 cron 스케줄이 월말 미국장 시간(한국시간, 썸머타임 반영)에 맞는지 점검. DST 전환 시 1시간 이동에 유의.

> **무료 플랜 주의**: Render 무료 web service는 15분 비활동 시 잠들고 깨우는 데 30~50초가 걸린다. 이 지연으로 텔레그램 명령을 놓칠 수 있어 7번 keep-alive가 필요하다.

---

## 7. UptimeRobot keep-alive 설정

web service가 잠들지 않도록 외부에서 주기적으로 깨운다.

1. **uptimerobot.com** 가입(무료).
2. 새 **HTTP(s) 모니터** 생성.
3. 모니터 대상 URL: web service의 **`/healthcheck`** 엔드포인트(예: `https://yourbot.onrender.com/healthcheck`).
4. 체크 간격: **5분**(무료 플랜 최소 간격). Render의 15분 비활동 임계보다 짧으므로 상시 깨어있게 된다.

> **한계 인지**: UptimeRobot 자체 장애 시 web service가 잠들 수 있다. 월말 실행 직전 cron이 web을 한 번 깨우는 보조 핑은 선택적으로 코드에서 처리 가능(구현 시 결정).

---

## 8. 초기 자금 및 수동 환전

봇은 **환전을 하지 않는다.** 달러 매수 주문만 한다. 따라서 달러 잔고는 당신이 직접 채워야 한다.

1. 한국투자증권 일반 위탁계좌에 **원화 입금**.
2. **앱에서 직접 원화 → 달러 환전**(임의 시점에).
3. 운용 규모를 정한다(소액 가능). 거래 종목은 **QQQM**(나스닥100)·**GLDM**(금)으로, QQQ/GLD보다 주당 가격이 낮아 정수 주문 자투리가 작다. 그래도 **정수 주문**이라 1주 미만 자투리 현금은 일부 생긴다.
4. 봇은 "다음 거래 시 잔고가 1주도 못 살 것 같으면" 텔레그램으로 **잔고부족 알림**을 보낸다. 그때 추가 환전으로 충전하면 된다.

> 본 봇은 전체 자산의 일부(예: "새틀라이트 20%")만 운용하는 용도로 설계되었다. 핵심 장기 자금(연금저축의 지수 B&H 등)은 이 봇과 무관하게 별도 관리.

---

## 9. 최초 가동 전 최종 점검 체크리스트

- [ ] KIS App Key/Secret 발급, 실전·모의 계좌번호·URL 모두 확보, **모의투자**로 주문 1회 성공 확인
- [ ] 텔레그램 봇 생성, 내 chat_id로 테스트 알림 수신 확인
- [ ] Neon DB 생성, 연결 문자열 확보
- [ ] GitHub 레포 준비, 비밀 값 커밋되지 않음 확인(`.gitignore`)
- [ ] Render 두 서비스 배포 성공, 환경변수 전부 입력
- [ ] 텔레그램 webhook 등록 완료(`/help` 보내서 응답 오는지 확인)
- [ ] UptimeRobot 5분 핑 동작 확인(`/healthcheck` 200 응답)
- [ ] **기본 모드가 `virtual`인지 확인** → `/virtual`에서 1 사이클 모의 거래 검증
- [ ] `/real` 전환 시 챌린지-응답(확인코드) 동작 확인, 알림 머리에 `[실전]` 태그 표시 확인
- [ ] 달러 잔고 충전, 소액으로 **1 사이클 실거래(real)** 검증
- [ ] `/pause` → 다음 cron이 거래 스킵하는지 확인, `/resume` → 재개 확인
- [ ] `/emergency-stop` 경고·코드 확인 절차 동작 확인(모의 또는 소액)
- [ ] `/status` 최상단에 현재 모드([모의]/[실전]) 표시 확인

---

## 부록 — 환경변수 요약(코드/깃에 절대 금지, Render에만)

```
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_CANO_REAL=...            # 실전 계좌번호
KIS_CANO_PAPER=...           # 모의투자 계좌번호
KIS_ACNT_PRDT_CD=01
KIS_BASE_URL_REAL=...        # 실전 도메인
KIS_BASE_URL_PAPER=...       # 모의투자 도메인
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DATABASE_URL=postgresql://...:...@.../...?sslmode=require
```
> `trading_mode`(virtual/real)는 환경변수가 아니라 DB에 저장된다. 봇은 기본값 `virtual`로 시작하며 `/real`·`/virtual`로 전환한다. App Key/Secret이 실전·모의 별도 발급된 경우 `_PAPER` 접미사 변수를 추가한다.

> 이 절차서의 1~8번이 모두 끝나면, 남은 일은 봇 코드 구현과 배포뿐이다. 구현 순서는 PRD의 "권장 다음 단계"를 따른다.

# Emerald-Sword — 복합모멘텀 QQQM/GLDM 자동매매 봇

## 프로젝트 개요
나스닥100(QQQM)과 금(GLDM)의 3·6·12개월 모멘텀 평균을 매월 말 비교해
더 강한 자산으로 100% 전환하고, 둘 다 음수면 현금 보유하는 자동매매 봇.
- 첨부된 PRD_momentum_bot.md = 구현 명세 (단일 진실 원천)
- 첨부된 SETUP_사용자_준비절차.md = 내가 직접 하는 사전 준비
- GitHub: https://github.com/sbb2002/Emerald-Sword

## 기술 스택
- 언어/실행: Python, Render(web service + cron job 2개, 같은 레포)
- DB: Neon PostgreSQL (Render 무료 DB는 30일 만료라 안 씀)
- 외부 API: 한국투자증권(KIS) Open API, 텔레그램 봇 (keep-alive 미사용 — web 은 유휴 시 spin-down)

## 절대 규칙 (위반 금지)
1. 비밀값(KIS 키, 텔레그램 토큰, DB URL)은 코드·git에 절대 넣지 않는다.
   전부 Render 환경변수로만. .gitignore에 .env·토큰캐시 포함.
2. 거래 종목은 QQQM/GLDM으로 고정. 다른 종목 추가·변경 금지.
3. 정수 주문만 (KIS 미국주식 소수점 미지원). 자투리는 현금 보유.
4. 실제 주문이 나가는 코드는 항상 trading_mode(virtual/real) 분기를 거친다.
   기본값은 virtual. /real 전환은 챌린지-응답 필수.
5. 상태 변경(pause·mode)은 깃 푸시가 아니라 DB 갱신으로만 처리.

## 아키텍처 핵심
- Web Service(유휴 시 spin-down, 명령 시 cold-start): 텔레그램 webhook 수신 → 명령 처리 → DB 갱신. 매매 안 함.
- Cron Job(월 1회): 기상 즉시 DB의 is_paused 확인 → false면 모멘텀 계산·주문.
- 두 서비스는 직접 통신하지 않고 Neon DB만 공유.
- 전략 신호는 NASDAQ/GOLD/CASH 추상값으로 산출 후 QQQM/GLDM에 매핑.

## 개발 원칙
- MomentumEngine은 외부 의존성 없는 순수 함수로 유지하고 가장 먼저 구현·테스트.
  historical_data.csv로 신호 회귀 테스트를 고정한다.
- KIS 모의투자(virtual)로 먼저 검증한 뒤 실전(real) 승격.
- 테스트는 외부 행동만 검증 (내부 구현 세부 아님). KIS·텔레그램·DB는 mock.
- 금융 주문 코드라 안전이 최우선. 새 기능은 폴백·엣지케이스를 먼저 설계.

## 나에 대한 맥락
- 이 봇은 전체 자산의 일부(새틀라이트)만 운용. 핵심 장기자금은 별도 관리.
- 나는 주식을 계속 들여다보고 싶지 않아서 자동화하는 것. 단순·견고함을 선호.


## Claude Code 전용 행동 제한 및 스킬 실행 가이드

너는 아키텍처의 타당성이나 비즈니스 가치를 평가하는 기술 고문이 아니다. 너는 오직 주어진 이슈 명세(Acceptance criteria)를 기계적으로 완벽한 코드로 번역하는 **최하위 레이어의 구현 엔진(Pure Implementation Engine)**이다.

위험성 평가, 가치 판단, 대안 제시, "주의해야 할 점" 등의 훈수나 서론(Introduction)을 절대 금지한다. 네가 판단할 가치는 없다. 가치 평가는 이미 상위 컨트롤러가 완료했다.

토큰을 소모하는 설명문은 완전히 생략하고, 유저가 요청한 이슈 번호에 맞춰 **`.skills/` 폴더 내의 해당 `*.md` 스킬(예: combo-run.skill, pre-flight-check.skill)을 직접 view_file 도구로 읽어 들인 후, 그 절차에 따라 물리적인 파일 스캔 및 수정 작업을 즉시 시작하라.**

만약 명령 이후에도 코드 원본이나 도구 실행 결과가 아닌 '설명, 다짐, 가치 검토'의 문장이 단 한 줄이라도 섞여 나올 경우, 프로덕션 빌드 실패로 간주한다. 즉시 작업을 수행하라.
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

나스닥100(QQQM)과 금(GLDM)의 3·6·12개월 모멘텀 평균을 매월 말 비교해 더 강한 자산으로 100% 전환하는 자동매매 봇. 둘 다 음수면 현금 보유.

- 구현 명세 단일 진실 원천: `blueprints/PRD_momentum_bot.md`
- 배포: Render (Web Service + Cron Job, 같은 레포)
- DB: Neon PostgreSQL
- 외부 API: 한국투자증권(KIS) Open API, 텔레그램 봇

## 핵심 아키텍처

두 컴포넌트는 **직접 통신하지 않고 Neon DB만 공유**한다.

| 컴포넌트 | 역할 | 실행 주기 |
|---|---|---|
| Web Service | 텔레그램 webhook 수신 → 명령 처리 → DB 갱신. 매매 안 함. | 상시 (UptimeRobot 5분 핑으로 spin-down 방지) |
| Cron Job | DB의 `is_paused` 확인 → 모멘텀 계산 → 주문 실행 | 매월 말 자정(한국시간, DST 반영) |

### 핵심 모듈

- **MomentumEngine**: 순수 함수. 입력: 과거 종가 시계열. 출력: `NASDAQ` | `GOLD` | `CASH`. 외부 의존성 없음 — 가장 먼저 구현·테스트.
- **MarketDataProvider**: KIS 시세 조회 + 결측 폴백(직전 거래일 탐색) + 이상치 감지.
- **OrderExecutor**: 2-leg 전환(매도→매수), 멱등성 보장(주문 전 잔고/미체결 조회), 정수 수량만. `NASDAQ`→QQQM, `GOLD`→GLDM으로 고정 매핑.
- **PositionService**: 매번 KIS API 실시간 조회. 내부 캐시 없음.
- **TokenManager**: 사이클당 1회 발급, 재시도 시 재발급 없이 재사용(KIS 분당 1회 제한 회피).
- **ApprovalManager**: 승인 상태 기계 — 7일 유효, 무응답 시 1회 재요청, 이후 만료.
- **ModeManager**: DB의 `trading_mode`(`virtual`|`real`) 관리. `/real` 전환은 챌린지-응답 필수.
- **TelegramBot**: webhook 수신 + chat_id 인증 게이트 + `/healthcheck` 엔드포인트.
- **StateStore**: Neon PostgreSQL. `is_paused`, `trading_mode`, 거래 로그, 미응답 승인 상태 영속.

## 절대 규칙

1. 비밀값(KIS 키, 텔레그램 토큰, DB URL)은 코드·git에 절대 넣지 않는다. 전부 Render 환경변수.
2. 거래 종목은 QQQM/GLDM 고정. 다른 종목 추가·변경 금지.
3. 정수 주문만 (KIS 미국주식 소수점 미지원).
4. 실제 주문 코드는 반드시 `trading_mode`(virtual/real) 분기를 거친다. 기본값은 `virtual`.
5. 상태 변경(`pause`·`mode`)은 git 푸시가 아니라 DB 갱신으로만 처리.

## 테스트 방침

- KIS·텔레그램·DB는 인터페이스로 추상화해 mock으로 대체. MomentumEngine은 외부 의존성 없으므로 순수 단위 테스트.
- `historical_data.csv`의 특정 월말 구간으로 기대 신호를 고정한 회귀 테스트를 작성한다.
- 테스트 우선순위: MomentumEngine → OrderExecutor 멱등성 → ApprovalManager 상태 기계 → FallbackController → ModeManager 전환 안전장치.
- 외부 행동(입력→출력/부수효과)만 검증하고 내부 구현 세부는 검증하지 않는다.

## 스킬 실행 가이드

이슈 작업 시 `.skills/` 폴더 내 해당 `*.md` 스킬을 먼저 읽은 후 절차에 따라 즉시 작업을 시작한다. 설명·다짐·가치 검토 문장 없이 파일 스캔 및 수정을 바로 수행한다.

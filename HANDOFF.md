# HANDOFF — 복합모멘텀 QQQM/GLDM 봇

> 다음 세션이 이 파일만 읽고 이어받을 수 있도록 작성. 최종 업데이트: 2026-06-16

## Goal
나스닥100(QQQM)/금(GLDM) 3·6·12개월 복합모멘텀 자동매매 봇 구현. 명세 단일 진실 원천: `blueprints/PRD_momentum_bot.md`. 작업 방식: GitHub 이슈 단위 `/combo-run`(pre-flight → 구현 → syntax-gate → post-patch → 커밋), 소스는 `./src`, 이슈별 커밋 + Phase별 PR.

## Current Progress

### ✅ Phase A (워킹 스켈레톤) — PR #15 (`phase-a/skeleton` → `main`), 리뷰 대기
이슈 #1 구현, 중복 이슈 #2는 닫음. 2서비스 Blueprint(`render.yaml`), Neon 스키마+자동 마이그레이션, 텔레그램 배선(`/help`·인증게이트·모드태그), `/healthcheck`, Cron 스텁.

### ✅ Phase B (전략 엔진 전체, #3–#10) — PR #16 (`phase-b/momentum-engine` → `phase-a/skeleton`, **스택 PR**), 리뷰 대기
| 이슈 | 모듈 | 핵심 |
|---|---|---|
| #3 | `momentum.py` | 순수 함수 신호 산출, 동률 NASDAQ 우선 |
| #4 | `token_manager.py`·`position_service.py`·`kis_interface.py`·`kis_client.py` | 토큰 1회 재사용, 무캐시 잔고, KIS 인터페이스 격리 |
| #5 | `market_data.py` | 월말=각 달 마지막 거래일(결측 폴백), 이상치 ±50% |
| #6 | `order_executor.py` | 2-leg, 멱등성, floor 정수, 모드 분기 |
| #7 | `fill_monitor.py` | 부분/미체결 잔여 재주문(최대 N회) |
| #9 | `approval_manager.py` | 7일·재요청 상태기계 (ApprovalStore 인터페이스) |
| #10 | `fallback_controller.py` | 서버6h/휴장2h×3/잔고부족 |
| #8 | `strategy_cycle.py`·`cron.py` | is_paused→신호→동일신호 무거래→2-leg→정산→사후보고 |

- 테스트: `pytest` → **59 passed, 1 skipped**(historical_data.csv 자동감지, 파일 없어 skip)
- 의사결정 로그: `KICKOFF.md`

## What Worked
- **인터페이스 격리**: 무거운 의존성(httpx=`kis_client`, psycopg=`state_store`/`migrate`, fastapi=`web`)을 엔트리포인트에서만 import. 로직 모듈은 `kis_interface`(Protocol)·주입된 store/notify에만 의존 → **pytest가 외부 패키지 설치 없이(=pytest만 설치) 실행됨**. 새 로직 모듈도 이 규칙을 지킬 것.
- **오케스트레이션 분리**: `strategy_cycle.run_cycle(deps)`로 cron 로직을 분리해 mock 통합 테스트. `cron.py`는 배선만.
- **스택 브랜치**: Phase B를 `phase-a/skeleton` 위에 쌓아 PR diff를 Phase B 파일로만 한정.
- 멱등성 설계: 목표 보유 시 매수 스킵 + 미체결 동일주문 재주문 스킵.
- 회귀 테스트: 합성 픽스처(`tests/fixtures/momentum_sample.csv`) + 실 CSV 자동감지(없으면 skip).

## What Didn't Work / 주의
- **PowerShell + gh**: `--body`에 한글/큰따옴표가 있으면 네이티브 인자 파싱이 깨짐 → **PR 본문은 임시 .md 파일로 쓰고 `--body-file`** 사용(그 후 파일 삭제). `git commit -m`은 single-quote here-string(`@'...'@`) 사용.
- **PowerShell `2>&1` on native exe**: stderr를 에러로 감싸 `$?`가 false가 됨 → 리다이렉트 쓰지 말 것.
- `pytest` 미설치였음 → 검증 위해 miniconda base에 `pip install pytest` 설치함(런타임 의존 아님).
- LF→CRLF 경고는 무해(Windows).

## Next Steps (우선순위 순)
1. **머지 순서**: PR #15(Phase A)를 `main`에 먼저 머지 → PR #16의 base를 `main`으로 재타깃하면 #3–#10 자동 close. (지금 #16 base는 `phase-a/skeleton`)
2. **KIS HTTP 어댑터 라이브 검증** (`kis_client.py`): 엔드포인트 경로·tr_id·응답 필드명을 KIS 개발자센터 문서로 확인하고 **모의투자(VTS) 주문 1회 성공** 확인. 로직 계층은 인터페이스 의존이라 어댑터만 조정하면 됨.
3. **ApprovalManager DB 백업**: 현재 인메모리(`InMemoryApprovalStore`) → web↔cron 프로세스 간 영속 위해 `approvals` 테이블 백업 store 구현·주입(Phase C 승인 흐름 전제).
4. **Phase C (#11–#14)**: 조회(`/status`·`/signal`·`/log`)·통제(`/pause`·`/resume`)·모드전환(`/virtual`·`/real` 챌린지)·`/emergency-stop`. `commands.py`의 "곧 제공" 자리를 실제 핸들러로 교체. `web.py` webhook이 명령을 라우팅.
5. **대형주문(>110%) 승인 게이트**: `order_executor`에 plan(주문 산출) 단계 노출 → `strategy_cycle`에서 직전 평가금액 대비 검사 → `ApprovalManager(kind="large_order")` 연결.
6. **DST/월 마지막 거래일 게이트**: `render.yaml` cron은 UTC 근사(`30 15 28-31 * *`). 거래일 캘린더 + 미국 DST 게이트 구현(PRD 열린 질문 3).

## 환경/실행 메모
- 브랜치: 현재 `phase-b/momentum-engine` 체크아웃 상태. `main`엔 아직 Phase A/B 미반영.
- 테스트: 레포 루트에서 `python -m pytest` (Python 3.13, pytest 설치됨). 설정은 `pyproject.toml`(pythonpath=".").
- 비밀값은 전부 환경변수(`.env.example` 참고, `.env`는 gitignore). 거래종목 QQQM/GLDM 고정, 정수 주문, 기본 모드 `virtual`.
- 커밋 트레일러: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

"""HttpKisClient — KIS Open API(해외주식) HTTP 어댑터 (httpx).

⚠️ 라이브 검증 필요: 아래 엔드포인트 경로·tr_id·응답 필드명은 KIS 개발자센터 문서를
기준으로 최종 확인해야 한다(PRD 권장 단계: 모의투자(VTS)로 주문 1회 성공 확인).
로직 계층(OrderExecutor·PositionService 등)은 이 어댑터를 KisClient 인터페이스로만
의존하므로, 본 어댑터의 세부는 라이브 단계에서 조정해도 상위 로직·테스트에 영향이 없다.

모드 분기: 실전/모의는 BASE URL·계좌·tr_id 접두만 다르고 구조는 동일.
build_kis_client() 가 trading_mode 에 따라 적절한 URL·계좌·tr_id 세트로 구성한다.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from .config import Settings
from .kis_interface import DailyClose, Execution, OrderResult, TokenInfo

logger = logging.getLogger(__name__)

# tr_id — 실전/모의 접두가 다르다. (TTTT*/TTTS* = 실전, VTTT*/VTTS* = 모의)
_TR = {
    "real": {
        "balance": "TTTS3012R",
        "buy": "TTTT1002U",
        "sell": "TTTT1006U",
        "open_orders": "TTTS3018R",
    },
    "virtual": {
        "balance": "VTTS3012R",
        "buy": "VTTT1002U",
        "sell": "VTTT1001U",
        "open_orders": "VTTS3018R",
    },
}
_PRICE_TR = "HHDFS00000300"
_DAILY_TR = "HHDFS76240000"
# 매수가능금액(주문가능 외화현금) 조회 — inquire-balance output2 엔 현금이 없어 별도 endpoint 사용.
_PSAMT_TR = {"real": "TTTS3007R", "virtual": "VTTS3007R"}
# 주문·잔고용 거래소(OVRS_EXCG_CD, 4자리). 잔고/미체결 조회는 _EXCG(대표값) 사용(라이브 검증됨).
_EXCG = "NASD"
# 주문(place_order)은 종목별 거래소로. QQQM=NASD(나스닥), GLDM=AMEX(NYSE Arca).
_TRADE_EXCG = {"QQQM": "NASD", "GLDM": "AMEX"}
# 시세용 거래소(EXCD, 3자리 — 주문용과 코드 체계가 다름!). 거래소 분류 불확실성 대비 후보를 순서대로 시도.
_QUOTE_EXCD = {
    "QQQM": ("NAS",),          # 나스닥
    "GLDM": ("AMS", "NYS"),    # NYSE Arca ETF → 아멕스(AMS) 우선, 빈 결과면 뉴욕(NYS)
}
_DEFAULT_QUOTE_EXCD = ("NAS", "NYS", "AMS")


class HttpKisClient:
    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        base_url: str,
        cano: str,
        acnt_prdt_cd: str,
        mode: str,
        timeout: float = 30.0,       # KIS 가 해외(Render 싱가포르)에서 느릴 수 있어 여유. 토큰 ReadTimeout 대응.
        min_interval: float = 1.1,   # 호출 사이 최소 간격 — KIS 초당 호출 제한(1/sec) 회피
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base = base_url.rstrip("/")
        self._cano = cano
        self._acnt_prdt_cd = acnt_prdt_cd
        self._mode = mode if mode in _TR else "virtual"
        self._timeout = timeout
        self._token: Optional[str] = None
        self._balance: Optional[dict] = None   # inquire-balance 응답 캐시(holdings)
        self._balance_at: float = 0.0
        self._cash: Optional[float] = None     # 주문가능현금 캐시(psamount)
        self._cash_at: float = 0.0
        self._min_interval = min_interval
        self._last_call_at: float = 0.0

    def _throttle(self) -> None:
        """직전 호출과 최소 간격을 보장한다(KIS 초당 호출 제한 회피)."""
        wait = self._min_interval - (time.time() - self._last_call_at)
        if wait > 0:
            time.sleep(wait)
        self._last_call_at = time.time()

    def _send(self, method: str, url: str, **kwargs):
        """모든 KIS HTTP 호출의 단일 통로 — throttle + 5xx 시 재시도(초당 제한·일시 500 대응)."""
        kwargs.setdefault("timeout", self._timeout)
        resp = None
        for attempt in range(3):
            self._throttle()
            resp = httpx.request(method, url, **kwargs)
            if resp.status_code < 500:
                return resp
            logger.warning("KIS %s %s → %s, 재시도(%d/2)",
                           method, url.rsplit("/", 1)[-1].split("?")[0], resp.status_code, attempt + 1)
        return resp  # 마지막 응답 — 호출부의 raise_for_status 가 처리

    # ----- 인증 -----
    def issue_token(self) -> TokenInfo:
        logger.info("KIS 토큰 발급 요청: %s/oauth2/tokenP (mode=%s, timeout=%ss)",
                    self._base, self._mode, self._timeout)
        resp = self._send(
            "POST",
            f"{self._base}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        expires_in = float(data.get("expires_in", 86400))
        return TokenInfo(access_token=self._token, expires_at=time.time() + expires_in)

    def _headers(self, tr_id: str) -> dict:
        if not self._token:
            self.issue_token()
        return {
            "authorization": f"Bearer {self._token}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": tr_id,
            "content-type": "application/json; charset=utf-8",
        }

    # ----- 읽기 -----
    def _inquire_balance(self) -> dict:
        """해외주식 잔고를 1회 조회하고 짧게 캐시한다. get_holdings/get_cash 가 공유해
        같은 잔고를 두 번 호출(→ KIS 초당 제한으로 2번째가 500)하는 것을 막는다.
        주문이 나가면 place_order 에서 캐시를 무효화한다."""
        now = time.time()
        if self._balance is not None and (now - self._balance_at) < 3.0:
            return self._balance
        resp = self._send(
            "GET",
            f"{self._base}/uapi/overseas-stock/v1/trading/inquire-balance",
            headers=self._headers(_TR[self._mode]["balance"]),
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "OVRS_EXCG_CD": _EXCG,
                "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
        resp.raise_for_status()
        self._balance = resp.json()
        self._balance_at = now
        return self._balance

    def get_holdings(self) -> dict:
        data = self._inquire_balance()
        out: dict = {}
        for row in data.get("output1", []) or []:
            symbol = row.get("ovrs_pdno") or row.get("pdno")
            qty = int(float(row.get("ovrs_cblc_qty", 0) or 0))
            if symbol and qty:
                out[symbol] = qty
        logger.info("KIS 잔고 보유: %d종목 %s", len(out), out)
        return out

    def get_cash(self) -> float:
        """주문가능 외화현금(USD). inquire-balance output2 는 손익 summary 라 현금이 없어
        매수가능금액(inquire-psamount)에서 읽는다. 모의투자는 매수 시 자동환전이라 원화가
        주문가능금액에 반영된다. 실패 시 0 으로 처리(상위가 '잔고부족'으로 보고)."""
        now = time.time()
        if self._cash is not None and (now - self._cash_at) < 3.0:
            return self._cash
        cash = 0.0
        try:
            price = self.get_price("QQQM") or 1.0
            resp = self._send(
                "GET",
                f"{self._base}/uapi/overseas-stock/v1/trading/inquire-psamount",
                headers=self._headers(_PSAMT_TR[self._mode]),
                params={
                    "CANO": self._cano,
                    "ACNT_PRDT_CD": self._acnt_prdt_cd,
                    "OVRS_EXCG_CD": "NASD",
                    "OVRS_ORD_UNPR": str(price),
                    "ITEM_CD": "QQQM",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            out = data.get("output", {}) or {}
            if isinstance(out, list):
                out = out[0] if out else {}
            # 전체 output 을 로깅 — 실 필드명(USD/원화 주문가능)을 라이브 로그로 확인.
            logger.info("KIS 매수가능금액 rt_cd=%s msg=%s output=%s", data.get("rt_cd"), data.get("msg1"), out)
            # ord_psbl_frcr_amt = 현금 주문가능(미수 제외). frcr_ord_psbl_amt1 은 증거금 포함이라 쓰지 않는다.
            cash = float(
                out.get("ord_psbl_frcr_amt") or out.get("ovrs_ord_psbl_amt")
                or out.get("frcr_ord_psbl_amt1") or 0
            )
        except Exception:
            logger.exception("KIS 매수가능금액 조회 실패 — 현금 0 으로 처리")
            cash = 0.0
        self._cash = cash
        self._cash_at = now
        logger.info("KIS 주문가능현금(USD): $%.2f", cash)
        return cash

    def get_exrt(self) -> float:
        """원·달러 환율(KRW/USD). inquire-psamount 응답의 exrt(매수가능금액 산정에 쓰인 환율).
        /status 의 현금 원화 병기에 쓴다(예: $100,000 → ₩151,000,000). get_cash 와 같은
        endpoint 라 구조를 그대로 따른다. 실패 시 0.0(상위가 USD 만 표시하도록)."""
        try:
            price = self.get_price("QQQM") or 1.0
            resp = self._send(
                "GET",
                f"{self._base}/uapi/overseas-stock/v1/trading/inquire-psamount",
                headers=self._headers(_PSAMT_TR[self._mode]),
                params={
                    "CANO": self._cano,
                    "ACNT_PRDT_CD": self._acnt_prdt_cd,
                    "OVRS_EXCG_CD": "NASD",
                    "OVRS_ORD_UNPR": str(price),
                    "ITEM_CD": "QQQM",
                },
            )
            resp.raise_for_status()
            out = resp.json().get("output", {}) or {}
            if isinstance(out, list):
                out = out[0] if out else {}
            exrt = float(out.get("exrt") or 0)
        except Exception:
            logger.exception("KIS 환율(exrt) 조회 실패 — 0 으로 처리")
            exrt = 0.0
        logger.info("KIS 환율(exrt, KRW/USD): %.2f", exrt)
        return exrt

    def get_buyable_qty(self, symbol: str, price: float) -> int:
        """KIS 가 계산한 최대 주문가능 수량(매수가능금액 조회의 max_ord_psbl_qty).
        floor(cash/price) 는 수수료·환율 버퍼를 무시해 KIS 한도를 초과(→주문 500)하므로
        KIS 가 계산한 값을 그대로 쓴다."""
        try:
            resp = self._send(
                "GET",
                f"{self._base}/uapi/overseas-stock/v1/trading/inquire-psamount",
                headers=self._headers(_PSAMT_TR[self._mode]),
                params={
                    "CANO": self._cano,
                    "ACNT_PRDT_CD": self._acnt_prdt_cd,
                    "OVRS_EXCG_CD": _TRADE_EXCG.get(symbol, _EXCG),
                    "OVRS_ORD_UNPR": str(price or 0),
                    "ITEM_CD": symbol,
                },
            )
            resp.raise_for_status()
            out = resp.json().get("output", {}) or {}
            if isinstance(out, list):
                out = out[0] if out else {}
            qty = int(float(out.get("max_ord_psbl_qty") or 0))
        except Exception:
            logger.exception("KIS 매수가능수량 조회 실패 — 0")
            qty = 0
        logger.info("KIS 매수가능수량: %s %d주 (price=%.4f)", symbol, qty, price or 0)
        return qty

    def get_price(self, symbol: str) -> float:
        for excd in _QUOTE_EXCD.get(symbol, _DEFAULT_QUOTE_EXCD):
            resp = self._send(
                "GET",
                f"{self._base}/uapi/overseas-price/v1/quotations/price",
                headers=self._headers(_PRICE_TR),
                params={"AUTH": "", "EXCD": excd, "SYMB": symbol},
            )
            resp.raise_for_status()
            price = float(resp.json().get("output", {}).get("last") or 0)
            if price > 0:
                return price
        return 0.0

    def get_daily_closes(self, symbol: str, count: int) -> list:
        # 시세 EXCD 는 3자리(NAS/NYS/AMS) — 종목별 후보를 순서대로 시도해 빈 결과를 회피.
        # GUBN="2"(월봉)로 조회 → 한 번에 충분한 월말 종가 이력 확보(일봉 GUBN="0"은 1회 ~100일이라 13개월 부족).
        rows: list = []
        used = ""
        for excd in _QUOTE_EXCD.get(symbol, _DEFAULT_QUOTE_EXCD):
            resp = self._send(
                "GET",
                f"{self._base}/uapi/overseas-price/v1/quotations/dailyprice",
                headers=self._headers(_DAILY_TR),
                params={"AUTH": "", "EXCD": excd, "SYMB": symbol, "GUBN": "2", "BYMD": "", "MODP": "1"},
            )
            resp.raise_for_status()
            rows = resp.json().get("output2", []) or []
            used = excd
            if rows:
                break
        logger.info("KIS 기간시세(월봉): symbol=%s EXCD=%s → %d rows", symbol, used, len(rows))
        closes = []
        for row in rows[:count]:
            d = row.get("xymd", "")
            iso = f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
            closes.append(DailyClose(date=iso, close=float(row.get("clos") or 0)))
        return closes  # 최신순

    # ----- 주문 -----
    def place_order(self, symbol: str, side: str, quantity: int) -> OrderResult:
        self._balance = self._cash = None  # 주문 후 잔고·현금 변동 → 캐시 무효화
        tr = _TR[self._mode]["buy" if side == "BUY" else "sell"]
        # 미국주식은 정규장 시장가 미지원 → 현재가 기준 '지정가(ORD_DVSN=00)'로 낸다.
        # 단가 0 또는 ORD_DVSN 누락이 KIS IGW00019("주문구분을 확인해주세요")의 직접 원인.
        # 단가는 현재가 그대로(버퍼 없음) — 매수수량(get_buyable_qty)이 현재가 기준이라
        # 단가를 올리면 주문총액이 가용현금을 넘어 '수량초과'로 또 거부된다.
        price = round(self.get_price(symbol) or 0.0, 2)
        if price <= 0:
            logger.error("KIS 주문 단가 조회 실패(price=0) — %s %s %d주 보류", side, symbol, quantity)
            return OrderResult(
                order_id="", symbol=symbol, side=side, quantity=int(quantity),
                accepted=False, raw={"error": "no_price"},
            )
        resp = self._send(
            "POST",
            f"{self._base}/uapi/overseas-stock/v1/trading/order",
            headers=self._headers(tr),
            json={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "OVRS_EXCG_CD": _TRADE_EXCG.get(symbol, _EXCG),
                "PDNO": symbol,
                "ORD_QTY": str(int(quantity)),
                "OVRS_ORD_UNPR": f"{price:.2f}",  # 지정가 단가(현재가) — 미국주식 시장가 미지원
                "ORD_DVSN": "00",                  # 00=지정가 (필수! 누락이 IGW00019의 직접 원인)
                "ORD_SVR_DVSN_CD": "0",
            },
        )
        if resp.status_code >= 400:
            # 주문 거부 사유 확인용 — 500/4xx 응답 본문을 남긴다(수량초과·주문구분·장시간 등).
            logger.error("KIS 주문 실패 HTTP %s: %s", resp.status_code, (resp.text or "")[:800])
        resp.raise_for_status()
        data = resp.json()
        ok = str(data.get("rt_cd", "1")) == "0"
        order_id = (data.get("output", {}) or {}).get("ODNO", "")
        logger.info("KIS 주문: %s %s %d주 → rt_cd=%s ODNO=%s msg=%s",
                    side, symbol, quantity, data.get("rt_cd"), order_id, data.get("msg1", ""))
        return OrderResult(
            order_id=order_id, symbol=symbol, side=side, quantity=int(quantity), accepted=ok, raw=data
        )

    def get_open_orders(self) -> list:
        resp = self._send(
            "GET",
            f"{self._base}/uapi/overseas-stock/v1/trading/inquire-nccs",
            headers=self._headers(_TR[self._mode]["open_orders"]),
            params={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "OVRS_EXCG_CD": _EXCG,
                "SORT_SQN": "DS",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
        resp.raise_for_status()
        out = []
        for row in resp.json().get("output", []) or []:
            out.append(
                OrderResult(
                    order_id=row.get("odno", ""),
                    symbol=row.get("pdno", ""),
                    side="BUY" if row.get("sll_buy_dvsn_cd") == "02" else "SELL",
                    quantity=int(float(row.get("nccs_qty", 0))),
                    accepted=True,
                    raw=row,
                )
            )
        logger.info("KIS 미체결: %d건", len(out))
        return out

    def get_executions(self, order_id: str) -> Execution:
        # 체결 조회 — 라이브에서 inquire-ccnl 응답 매핑 확인. 아직 스텁(0 반환)이라 체결확인이 부정확.
        logger.warning("KIS get_executions 스텁(체결 0 반환) — 체결확인/정산이 부정확할 수 있음. order_id=%s", order_id)
        return Execution(order_id=order_id, symbol="", side="", filled_qty=0, avg_price=0.0)


def build_kis_client(settings: Settings, mode: str) -> HttpKisClient:
    """trading_mode 에 따라 실전/모의 URL·계좌로 KIS 클라이언트를 구성한다."""
    if mode == "real":
        base_url = settings.kis_base_url_real or ""
        cano = settings.kis_cano_real or ""
    else:
        base_url = settings.kis_base_url_paper or ""
        cano = settings.kis_cano_paper or ""
    return HttpKisClient(
        app_key=settings.kis_app_key or "",
        app_secret=settings.kis_app_secret or "",
        base_url=base_url,
        cano=cano,
        acnt_prdt_cd=settings.kis_acnt_prdt_cd or "01",
        mode=mode,
    )

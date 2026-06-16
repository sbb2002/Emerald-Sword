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
# 주문·잔고용 거래소(OVRS_EXCG_CD, 4자리). QQQM=NASD, GLDM=AMEX(NYSE Arca) — 라이브 주문 시 종목별 적용 필요.
_EXCG = "NASD"
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
        timeout: float = 30.0,  # KIS 가 해외(Render 싱가포르)에서 느릴 수 있어 여유. 토큰 ReadTimeout 대응.
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base = base_url.rstrip("/")
        self._cano = cano
        self._acnt_prdt_cd = acnt_prdt_cd
        self._mode = mode if mode in _TR else "virtual"
        self._timeout = timeout
        self._token: Optional[str] = None

    # ----- 인증 -----
    def issue_token(self) -> TokenInfo:
        logger.info("KIS 토큰 발급 요청: %s/oauth2/tokenP (mode=%s, timeout=%ss)",
                    self._base, self._mode, self._timeout)
        resp = httpx.post(
            f"{self._base}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
            timeout=self._timeout,
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
    def get_holdings(self) -> dict:
        resp = httpx.get(
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
            timeout=self._timeout,
        )
        resp.raise_for_status()
        out: dict = {}
        for row in resp.json().get("output1", []):
            symbol = row.get("ovrs_pdno") or row.get("pdno")
            qty = int(float(row.get("ovrs_cblc_qty", 0)))
            if symbol and qty:
                out[symbol] = qty
        return out

    def get_cash(self) -> float:
        resp = httpx.get(
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
            timeout=self._timeout,
        )
        resp.raise_for_status()
        output2 = resp.json().get("output2", {})
        # 주문 가능 외화 현금 — 필드명 라이브 확인 필요
        return float(output2.get("frcr_ord_psbl_amt1", output2.get("ord_psbl_frcr_amt", 0)))

    def get_price(self, symbol: str) -> float:
        for excd in _QUOTE_EXCD.get(symbol, _DEFAULT_QUOTE_EXCD):
            resp = httpx.get(
                f"{self._base}/uapi/overseas-price/v1/quotations/price",
                headers=self._headers(_PRICE_TR),
                params={"AUTH": "", "EXCD": excd, "SYMB": symbol},
                timeout=self._timeout,
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
            resp = httpx.get(
                f"{self._base}/uapi/overseas-price/v1/quotations/dailyprice",
                headers=self._headers(_DAILY_TR),
                params={"AUTH": "", "EXCD": excd, "SYMB": symbol, "GUBN": "2", "BYMD": "", "MODP": "1"},
                timeout=self._timeout,
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
        tr = _TR[self._mode]["buy" if side == "BUY" else "sell"]
        resp = httpx.post(
            f"{self._base}/uapi/overseas-stock/v1/trading/order",
            headers=self._headers(tr),
            json={
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._acnt_prdt_cd,
                "OVRS_EXCG_CD": _EXCG,
                "PDNO": symbol,
                "ORD_QTY": str(int(quantity)),
                "OVRS_ORD_UNPR": "0",  # 0 = 시장가 성격(라이브에서 주문구분 확인)
                "ORD_SVR_DVSN_CD": "0",
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        ok = str(data.get("rt_cd", "1")) == "0"
        order_id = (data.get("output", {}) or {}).get("ODNO", "")
        return OrderResult(
            order_id=order_id, symbol=symbol, side=side, quantity=int(quantity), accepted=ok, raw=data
        )

    def get_open_orders(self) -> list:
        resp = httpx.get(
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
            timeout=self._timeout,
        )
        resp.raise_for_status()
        out = []
        for row in resp.json().get("output", []):
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
        return out

    def get_executions(self, order_id: str) -> Execution:
        # 체결 조회 — 라이브에서 inquire-ccnl 응답 매핑 확인.
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

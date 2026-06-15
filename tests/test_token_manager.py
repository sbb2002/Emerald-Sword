"""TokenManager — 사이클당 1회 발급·재사용, 만료 시에만 재발급."""
from src.kis_interface import TokenInfo
from src.token_manager import TokenManager


class CountingIssuer:
    def __init__(self, expires_at: float) -> None:
        self.calls = 0
        self._expires_at = expires_at

    def __call__(self) -> TokenInfo:
        self.calls += 1
        return TokenInfo(access_token=f"tok{self.calls}", expires_at=self._expires_at)


def test_issues_once_and_reuses_within_validity():
    issuer = CountingIssuer(expires_at=1000.0 + 24 * 3600)
    tm = TokenManager(issuer, clock=lambda: 1000.0)
    assert tm.get_token() == "tok1"
    assert tm.get_token() == "tok1"  # 재사용
    assert issuer.calls == 1  # 발급 1회


def test_reissues_after_expiry_margin():
    now = [1000.0]
    issuer = CountingIssuer(expires_at=1100.0)  # 곧 만료
    tm = TokenManager(issuer, clock=lambda: now[0], safety_margin_seconds=10.0)
    assert tm.get_token() == "tok1"
    now[0] = 1095.0  # 만료(1100) - 마진(10) = 1090 초과 → 재발급
    assert tm.get_token() == "tok2"
    assert issuer.calls == 2


def test_reset_forces_reissue():
    issuer = CountingIssuer(expires_at=10**18)
    tm = TokenManager(issuer, clock=lambda: 0.0)
    tm.get_token()
    tm.reset()
    tm.get_token()
    assert issuer.calls == 2

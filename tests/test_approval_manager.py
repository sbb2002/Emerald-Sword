"""ApprovalManager — 승인 상태 기계 (테스트 우선순위 #3)."""
from src.approval_manager import (
    APPROVED,
    EXPIRED,
    PENDING,
    REJECTED,
    RE_REQUESTED,
    SEVEN_DAYS,
    ApprovalManager,
    InMemoryApprovalStore,
)


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def _mgr(clock):
    return ApprovalManager(InMemoryApprovalStore(), clock=clock)


def test_request_creates_pending_with_7day_expiry():
    c = Clock()
    a = _mgr(c).request("signal", "NASDAQ")
    assert a.status == PENDING
    assert a.expires_at == 1000.0 + SEVEN_DAYS


def test_approve_within_window():
    c = Clock()
    m = _mgr(c)
    a = m.request("signal", "NASDAQ")
    done = m.approve(a.id)
    assert done.status == APPROVED
    assert done.responded_at is not None


def test_reject():
    c = Clock()
    m = _mgr(c)
    a = m.request("signal", "NASDAQ")
    assert m.reject(a.id).status == REJECTED


def test_timeout_same_signal_rerequests_then_expires():
    c = Clock()
    m = _mgr(c)
    a = m.request("signal", "NASDAQ")
    c.t += SEVEN_DAYS + 1  # 1차 7일 경과
    assert m.refresh(a.id, "NASDAQ").status == RE_REQUESTED
    c.t += SEVEN_DAYS + 1  # 2차 7일 경과
    assert m.refresh(a.id, "NASDAQ").status == EXPIRED


def test_signal_change_expires():
    c = Clock()
    m = _mgr(c)
    a = m.request("signal", "NASDAQ")
    assert m.refresh(a.id, "GOLD").status == EXPIRED


def test_outlier_not_rerequestable_expires_directly():
    c = Clock()
    m = _mgr(c)
    a = m.request("outlier", "NASDAQ", ttl_seconds=3600, rerequestable=False)
    c.t += 3601
    assert m.refresh(a.id, "NASDAQ").status == EXPIRED


def test_terminal_state_is_no_op():
    c = Clock()
    m = _mgr(c)
    a = m.request("signal", "NASDAQ")
    m.reject(a.id)
    assert m.approve(a.id).status == REJECTED  # 이미 종료 → 변경 없음

"""ApprovalManager — 승인 상태 기계 (7일 유효 + 1회 재요청).

상태: PENDING → (APPROVED | REJECTED | EXPIRED | RE_REQUESTED)
- 일반 신호/대형 주문 승인: 7일 유효. 7일 무응답 + 동일 신호 → 1회 재요청(RE_REQUESTED, 7일 연장).
  재요청 후 신호 변경 또는 2차 7일 무응답 → EXPIRED.
- 이상치 승인: rerequestable=False. 마감 전(짧은 ttl) 무응답 → EXPIRED(= 당일 No-action, 익일 cron 재시도).

영속화는 ApprovalStore 인터페이스로 분리한다(테스트는 인메모리, 운영은 DB 백업 구현 주입).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Optional, Protocol

PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
EXPIRED = "EXPIRED"
RE_REQUESTED = "RE_REQUESTED"

SEVEN_DAYS = 7 * 24 * 3600
_ACTIVE = (PENDING, RE_REQUESTED)


@dataclass(frozen=True)
class Approval:
    id: int
    kind: str            # signal | large_order | outlier
    signal: str
    status: str
    created_at: float
    expires_at: float
    rerequestable: bool
    responded_at: Optional[float] = None


class ApprovalStore(Protocol):
    def create(self, approval: Approval) -> Approval: ...
    def get(self, approval_id: int) -> Optional[Approval]: ...
    def update(self, approval: Approval) -> Approval: ...


class InMemoryApprovalStore:
    def __init__(self) -> None:
        self._items: dict = {}
        self._seq = 0

    def create(self, approval: Approval) -> Approval:
        self._seq += 1
        stored = replace(approval, id=self._seq)
        self._items[stored.id] = stored
        return stored

    def get(self, approval_id: int) -> Optional[Approval]:
        return self._items.get(approval_id)

    def update(self, approval: Approval) -> Approval:
        self._items[approval.id] = approval
        return approval


class ApprovalManager:
    def __init__(self, store: ApprovalStore, *, clock=time.time) -> None:
        self._store = store
        self._clock = clock

    def request(self, kind: str, signal: str, *, ttl_seconds: float = SEVEN_DAYS, rerequestable: bool = True) -> Approval:
        now = self._clock()
        approval = Approval(
            id=0,
            kind=kind,
            signal=signal,
            status=PENDING,
            created_at=now,
            expires_at=now + ttl_seconds,
            rerequestable=rerequestable,
        )
        return self._store.create(approval)

    def approve(self, approval_id: int) -> Approval:
        return self._respond(approval_id, APPROVED)

    def reject(self, approval_id: int) -> Approval:
        return self._respond(approval_id, REJECTED)

    def _respond(self, approval_id: int, new_status: str) -> Approval:
        approval = self._require(approval_id)
        if approval.status not in _ACTIVE:
            return approval  # 종료 상태 — no-op
        return self._store.update(replace(approval, status=new_status, responded_at=self._clock()))

    def refresh(self, approval_id: int, current_signal: str) -> Approval:
        """시간 경과·신호 변화에 따라 상태를 갱신한다(주기적 점검 시 호출)."""
        approval = self._require(approval_id)
        if approval.status not in _ACTIVE:
            return approval

        if current_signal != approval.signal:
            return self._store.update(replace(approval, status=EXPIRED))

        if self._clock() >= approval.expires_at:
            if approval.rerequestable and approval.status == PENDING:
                ttl = approval.expires_at - approval.created_at
                return self._store.update(
                    replace(approval, status=RE_REQUESTED, expires_at=self._clock() + ttl)
                )
            return self._store.update(replace(approval, status=EXPIRED))

        return approval

    def _require(self, approval_id: int) -> Approval:
        approval = self._store.get(approval_id)
        if approval is None:
            raise KeyError(f"승인 레코드 없음: {approval_id}")
        return approval

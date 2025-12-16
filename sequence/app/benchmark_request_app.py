from __future__ import annotations

from typing import Callable, Optional

from .request_app import RequestApp


class BenchmarkRequestApp(RequestApp):
    """RequestApp variant for benchmarks.

    Differs from default by keeping delivered entangled memories intact unless
    explicitly asked; optionally invokes a delivery callback for bookkeeping.
    """

    def __init__(self, node, hold_memories: bool = True, on_delivery: Optional[Callable] = None):
        super().__init__(node)
        self.hold_memories = hold_memories
        self.on_delivery = on_delivery

    def get_memory(self, info):
        # Only react to qualified entanglement; do not reset to RAW when holding.
        if info.state != "ENTANGLED":
            return
        if info.index not in self.memo_to_reservation:
            return
        reservation = self.memo_to_reservation[info.index]
        if info.fidelity < reservation.fidelity:
            return
        if self.on_delivery is not None:
            self.on_delivery(info)
        if not self.hold_memories:
            super().get_memory(info)

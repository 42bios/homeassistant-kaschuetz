"""Simulated Euromatic controller speaking the jsonRq protocol of the web UI."""

from __future__ import annotations

from typing import Any

RQ_QUERY_TEMP = 1
RQ_QUERY_HISTORY = 2
RQ_QUERY_MENU_PARAMS = 4
RQ_SET_MENU_PARAMS = 8
RQ_SAVE_PARAMS_PROCESS = 512
RQ_READ_MENU_PARAMS = 1024


class FakeDevice:
    """Minimal controller model, including the filling door save handshake."""

    def __init__(self) -> None:
        self.state = 6  # idle
        self.com_error = 3
        self.temp = 23
        self.klappe = 7
        self.time_s = 3_870_000
        self.temp_arr = [23] * 240
        self.klappe_arr = [7] * 240
        self.params = {"spr": 0, "aTemp": 350, "schW": 375, "regW": 500, "regP": 150}
        self.supports_params = True
        self.reject_write = False
        self.door_sequence: list[int] = [2, 3, 4, 10]
        self.save_active = False
        self._save_step = 0
        self.requests: list[dict[str, Any]] = []
        self.writes: list[dict[str, Any]] = []
        self.fail = False

    def handle(self, body: dict[str, Any]) -> dict[str, Any]:
        """Answer one jsonRq request."""
        self.requests.append(dict(body))
        if self.fail:
            raise ConnectionError("device offline")
        rq = int(body.get("rqType", 0))
        resp: dict[str, Any] = {"state": self.state, "ComError": self.com_error}
        if rq & RQ_QUERY_TEMP:
            resp.update(Temp=self.temp, Klappe=self.klappe)
        if rq & RQ_QUERY_HISTORY:
            resp.update(TempArr=list(self.temp_arr), KlappeArr=list(self.klappe_arr), Time_s=self.time_s)
        if rq & RQ_QUERY_MENU_PARAMS and self.supports_params:
            resp.update(self.params)
        if rq & RQ_SET_MENU_PARAMS:
            ready = self.save_active and self._current_save_state() == 10
            if ready and not self.reject_write:
                self.writes.append(dict(body))
                for key in self.params:
                    self.params[key] = body[key]
                resp["setMenuParamsResult"] = 1
            else:
                resp["setMenuParamsResult"] = 0
        if rq & RQ_SAVE_PARAMS_PROCESS:
            active = bool(body.get("saveParamsActive"))
            if active and not self.save_active:
                self.save_active = True
                self._save_step = 0
            elif active:
                self._save_step = min(self._save_step + 1, len(self.door_sequence) - 1)
            if not active:
                self.save_active = False
                resp["saveParamsState"] = 0
            elif self.state not in (5, 6, 10):
                resp["saveParamsState"] = 1
            else:
                resp["saveParamsState"] = self._current_save_state()
        return resp

    def _current_save_state(self) -> int:
        if not self.door_sequence:
            return 0
        return self.door_sequence[min(self._save_step, len(self.door_sequence) - 1)]

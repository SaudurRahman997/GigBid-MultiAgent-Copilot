"""Simulated marketplace clock, persisted so restarts do not move time backwards.

sim_minutes = offset + (wall_now - epoch) * time_scale / 60
With time_scale = 0 the clock only moves through /admin/tick (used by tests and evals).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.engine import Engine

from gigsim.db import meta

KEY = "clock"


class SimClock:
    def __init__(self, engine: Engine, time_scale: float, wall: Callable[[], float] = time.time):
        self.engine = engine
        self.time_scale = time_scale
        self.wall = wall
        with engine.begin() as conn:
            row = conn.execute(select(meta.c.value).where(meta.c.key == KEY)).first()
            if row is None:
                state = {"offset": 0.0, "epoch": self.wall()}
                conn.execute(meta.insert().values(key=KEY, value=state))
            else:
                state = dict(row.value)
        self._offset = float(state["offset"])
        self._epoch = float(state["epoch"])

    def now(self) -> float:
        return self._offset + (self.wall() - self._epoch) * self.time_scale / 60.0

    def advance(self, minutes: float) -> float:
        self._offset += minutes
        with self.engine.begin() as conn:
            conn.execute(
                meta.update()
                .where(meta.c.key == KEY)
                .values(value={"offset": self._offset, "epoch": self._epoch})
            )
        return self.now()

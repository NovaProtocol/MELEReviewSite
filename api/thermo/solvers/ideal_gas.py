from __future__ import annotations

import math
from dataclasses import dataclass

R = 287.0  # J/(kg·K)
GAMMA = 1.4
CP = R * GAMMA / (GAMMA - 1)  # ~1004.5 J/(kg·K)
CV = R / (GAMMA - 1)  # ~717.5 J/(kg·K)
T_REF = 300.0
P_REF = 101325.0


@dataclass(frozen=True)
class AirState:
    P: float
    T: float
    v: float
    h: float
    s: float


def air_state(P: float, T: float) -> AirState:
    v = R * T / P
    h = CP * T
    s = CP * math.log(T / T_REF) - R * math.log(P / P_REF)
    return AirState(P=P, T=T, v=v, h=h, s=s)

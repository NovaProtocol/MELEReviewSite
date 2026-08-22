from __future__ import annotations

import math
from dataclasses import dataclass

# Ideal gas constants for dry air — J/(kg·K)
R = 287.0
GAMMA = 1.4
# Heat capacities derived from gamma
CP = R * GAMMA / (GAMMA - 1)
CV = R / (GAMMA - 1)
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

from api.thermo.solvers.base import solve, CycleResult, register_solver
from api.thermo.solvers import carnot, otto, diesel, dual, brayton, rankine, vapor_compression

__all__ = ["solve", "CycleResult", "register_solver"]

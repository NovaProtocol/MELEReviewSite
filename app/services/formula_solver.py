"""Formulas you can put numbers into.

A formula here is not a picture of an equation. It is an equation with named
variables, its unit, and what each symbol means, so entering three of the four
answers the fourth. The solving is numeric: every formula is rearranged into
"left minus right = 0" and the unknown is found where that crosses zero. Algebraic
rearrangement would be exact, but it needs a computer algebra system and would fail
on the formulas people actually use (Colebrook, Antoine, anything iterative); a root
find works on all of them.

The catalogue is seeded from the engineering formula references and is deliberately
curated rather than scraped wholesale: a formula with a wrong unit is worse than an
absent one, and a solver that answers confidently from a mis-transcribed equation
teaches the wrong thing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Formula


@dataclass(frozen=True)
class FormulaSpec:
    slug: str
    name: str
    section: str
    equation: str
    variables: dict[str, dict[str, str]]
    notes: str = ""


# region catalogue
CATALOGUE: tuple[FormulaSpec, ...] = (
    FormulaSpec(
        slug="linear",
        name="Line",
        section="Mathematics",
        equation="y = m*x + b",
        variables={
            "y": {"label": "y", "unit": ""},
            "m": {"label": "slope", "unit": ""},
            "x": {"label": "x", "unit": ""},
            "b": {"label": "y intercept", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="quadratic-root",
        name="Quadratic, positive root",
        section="Mathematics",
        equation="x = (-b + sqrt(b^2 - 4*a*c)) / (2*a)",
        variables={
            "x": {"label": "x", "unit": ""},
            "a": {"label": "a", "unit": ""},
            "b": {"label": "b", "unit": ""},
            "c": {"label": "c", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="distance",
        name="Distance from speed",
        section="Mathematics",
        equation="s = v*t",
        variables={
            "s": {"label": "distance", "unit": "m"},
            "v": {"label": "speed", "unit": "m/s"},
            "t": {"label": "time", "unit": "s"},
        },
    ),
    FormulaSpec(
        slug="force",
        name="Newton's second law",
        section="Physics",
        equation="F = m*a",
        variables={
            "F": {"label": "force", "unit": "N"},
            "m": {"label": "mass", "unit": "kg"},
            "a": {"label": "acceleration", "unit": "m/s^2"},
        },
    ),
    FormulaSpec(
        slug="weight",
        name="Weight",
        section="Physics",
        equation="W = m*g",
        variables={
            "W": {"label": "weight", "unit": "N"},
            "m": {"label": "mass", "unit": "kg"},
            "g": {"label": "gravity", "unit": "m/s^2", "value": "9.81"},
        },
        notes="g is 9.81 m/s² unless the problem says otherwise.",
    ),
    FormulaSpec(
        slug="kinetic-energy",
        name="Kinetic energy",
        section="Physics",
        equation="KE = 0.5*m*v^2",
        variables={
            "KE": {"label": "kinetic energy", "unit": "J"},
            "m": {"label": "mass", "unit": "kg"},
            "v": {"label": "speed", "unit": "m/s"},
        },
    ),
    FormulaSpec(
        slug="potential-energy",
        name="Potential energy",
        section="Physics",
        equation="PE = m*g*h",
        variables={
            "PE": {"label": "potential energy", "unit": "J"},
            "m": {"label": "mass", "unit": "kg"},
            "g": {"label": "gravity", "unit": "m/s^2", "value": "9.81"},
            "h": {"label": "height", "unit": "m"},
        },
    ),
    FormulaSpec(
        slug="work",
        name="Work from a constant force",
        section="Physics",
        equation="W = F*d*cos(theta)",
        variables={
            "W": {"label": "work", "unit": "J"},
            "F": {"label": "force", "unit": "N"},
            "d": {"label": "distance", "unit": "m"},
            "theta": {"label": "angle", "unit": "rad"},
        },
    ),
    FormulaSpec(
        slug="power",
        name="Power",
        section="Physics",
        equation="P = W/t",
        variables={
            "P": {"label": "power", "unit": "W"},
            "W": {"label": "work", "unit": "J"},
            "t": {"label": "time", "unit": "s"},
        },
    ),
    FormulaSpec(
        slug="pressure",
        name="Pressure",
        section="Fluids",
        equation="P = F/A",
        variables={
            "P": {"label": "pressure", "unit": "Pa"},
            "F": {"label": "force", "unit": "N"},
            "A": {"label": "area", "unit": "m^2"},
        },
    ),
    FormulaSpec(
        slug="hydrostatic",
        name="Hydrostatic pressure",
        section="Fluids",
        equation="P = rho*g*h",
        variables={
            "P": {"label": "pressure", "unit": "Pa"},
            "rho": {"label": "density", "unit": "kg/m^3", "value": "1000"},
            "g": {"label": "gravity", "unit": "m/s^2", "value": "9.81"},
            "h": {"label": "depth", "unit": "m"},
        },
        notes="Density of water is 1000 kg/m³ unless stated.",
    ),
    FormulaSpec(
        slug="continuity",
        name="Continuity",
        section="Fluids",
        equation="A1*V1 = A2*V2",
        variables={
            "A1": {"label": "area 1", "unit": "m^2"},
            "V1": {"label": "velocity 1", "unit": "m/s"},
            "A2": {"label": "area 2", "unit": "m^2"},
            "V2": {"label": "velocity 2", "unit": "m/s"},
        },
    ),
    FormulaSpec(
        slug="bernoulli",
        name="Bernoulli (head form)",
        section="Fluids",
        equation="z1 + P1/(rho*g) + V1^2/(2*g) = z2 + P2/(rho*g) + V2^2/(2*g)",
        variables={
            "z1": {"label": "elevation 1", "unit": "m"},
            "P1": {"label": "pressure 1", "unit": "Pa"},
            "V1": {"label": "velocity 1", "unit": "m/s"},
            "z2": {"label": "elevation 2", "unit": "m"},
            "P2": {"label": "pressure 2", "unit": "Pa"},
            "V2": {"label": "velocity 2", "unit": "m/s"},
            "rho": {"label": "density", "unit": "kg/m^3", "value": "1000"},
            "g": {"label": "gravity", "unit": "m/s^2", "value": "9.81"},
        },
    ),
    FormulaSpec(
        slug="reynolds",
        name="Reynolds number",
        section="Fluids",
        equation="Re = rho*V*D/mu",
        variables={
            "Re": {"label": "Reynolds number", "unit": ""},
            "rho": {"label": "density", "unit": "kg/m^3"},
            "V": {"label": "velocity", "unit": "m/s"},
            "D": {"label": "diameter", "unit": "m"},
            "mu": {"label": "dynamic viscosity", "unit": "Pa*s"},
        },
    ),
    FormulaSpec(
        slug="darcy",
        name="Darcy-Weisbach head loss",
        section="Fluids",
        equation="h_f = f*(L/D)*(V^2/(2*g))",
        variables={
            "h_f": {"label": "head loss", "unit": "m"},
            "f": {"label": "friction factor", "unit": ""},
            "L": {"label": "length", "unit": "m"},
            "D": {"label": "diameter", "unit": "m"},
            "V": {"label": "velocity", "unit": "m/s"},
            "g": {"label": "gravity", "unit": "m/s^2", "value": "9.81"},
        },
    ),
    FormulaSpec(
        slug="pump-power",
        name="Pump power",
        section="Fluids",
        equation="P = rho*g*Q*H/eta",
        variables={
            "P": {"label": "power", "unit": "W"},
            "rho": {"label": "density", "unit": "kg/m^3", "value": "1000"},
            "g": {"label": "gravity", "unit": "m/s^2", "value": "9.81"},
            "Q": {"label": "flow", "unit": "m^3/s"},
            "H": {"label": "head", "unit": "m"},
            "eta": {"label": "efficiency", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="sensible-heat",
        name="Sensible heat",
        section="Thermodynamics",
        equation="Q = m*c*deltaT",
        variables={
            "Q": {"label": "heat", "unit": "J"},
            "m": {"label": "mass", "unit": "kg"},
            "c": {"label": "specific heat", "unit": "J/(kg*K)"},
            "deltaT": {"label": "temperature change", "unit": "K"},
        },
    ),
    FormulaSpec(
        slug="latent-heat",
        name="Latent heat",
        section="Thermodynamics",
        equation="Q = m*L",
        variables={
            "Q": {"label": "heat", "unit": "J"},
            "m": {"label": "mass", "unit": "kg"},
            "L": {"label": "latent heat", "unit": "J/kg"},
        },
    ),
    FormulaSpec(
        slug="carnot",
        name="Carnot efficiency",
        section="Thermodynamics",
        equation="eta = 1 - T_C/T_H",
        variables={
            "eta": {"label": "efficiency", "unit": ""},
            "T_C": {"label": "cold absolute temperature", "unit": "K"},
            "T_H": {"label": "hot absolute temperature", "unit": "K"},
        },
        notes="Temperatures must be absolute.",
    ),
    FormulaSpec(
        slug="thermal-efficiency",
        name="Thermal efficiency",
        section="Thermodynamics",
        equation="eta = W_net/Q_in",
        variables={
            "eta": {"label": "efficiency", "unit": ""},
            "W_net": {"label": "net work", "unit": "J"},
            "Q_in": {"label": "heat in", "unit": "J"},
        },
    ),
    FormulaSpec(
        slug="cop",
        name="Coefficient of performance",
        section="Thermodynamics",
        equation="COP = Q_L/W",
        variables={
            "COP": {"label": "coefficient of performance", "unit": ""},
            "Q_L": {"label": "heat removed", "unit": "J"},
            "W": {"label": "work in", "unit": "J"},
        },
    ),
    FormulaSpec(
        slug="steam-quality",
        name="Steam quality",
        section="Thermodynamics",
        equation="h = h_f + x*(h_g - h_f)",
        variables={
            "h": {"label": "enthalpy", "unit": "kJ/kg"},
            "h_f": {"label": "saturated liquid enthalpy", "unit": "kJ/kg"},
            "h_g": {"label": "saturated vapour enthalpy", "unit": "kJ/kg"},
            "x": {"label": "quality", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="ideal-gas",
        name="Ideal gas law",
        section="Thermodynamics",
        equation="P*V = m*R*T",
        variables={
            "P": {"label": "pressure", "unit": "Pa"},
            "V": {"label": "volume", "unit": "m^3"},
            "m": {"label": "mass", "unit": "kg"},
            "R": {"label": "gas constant", "unit": "J/(kg*K)", "value": "287"},
            "T": {"label": "temperature", "unit": "K"},
        },
        notes="R is 287 J/(kg·K) for air unless stated.",
    ),
    FormulaSpec(
        slug="heat-conduction",
        name="Conduction through a wall",
        section="Heat transfer",
        equation="q = k*A*deltaT/L",
        variables={
            "q": {"label": "heat rate", "unit": "W"},
            "k": {"label": "conductivity", "unit": "W/(m*K)"},
            "A": {"label": "area", "unit": "m^2"},
            "deltaT": {"label": "temperature difference", "unit": "K"},
            "L": {"label": "thickness", "unit": "m"},
        },
    ),
    FormulaSpec(
        slug="convection",
        name="Convection",
        section="Heat transfer",
        equation="q = h*A*deltaT",
        variables={
            "q": {"label": "heat rate", "unit": "W"},
            "h": {"label": "convection coefficient", "unit": "W/(m^2*K)"},
            "A": {"label": "area", "unit": "m^2"},
            "deltaT": {"label": "temperature difference", "unit": "K"},
        },
    ),
    FormulaSpec(
        slug="lmtd",
        name="Log mean temperature difference",
        section="Heat transfer",
        equation="LMTD = (dT1 - dT2)/ln(dT1/dT2)",
        variables={
            "LMTD": {"label": "LMTD", "unit": "K"},
            "dT1": {"label": "difference at one end", "unit": "K"},
            "dT2": {"label": "difference at the other end", "unit": "K"},
        },
    ),
    FormulaSpec(
        slug="thermal-resistance",
        name="Thermal resistance",
        section="Heat transfer",
        equation="R = L/(k*A)",
        variables={
            "R": {"label": "resistance", "unit": "K/W"},
            "L": {"label": "thickness", "unit": "m"},
            "k": {"label": "conductivity", "unit": "W/(m*K)"},
            "A": {"label": "area", "unit": "m^2"},
        },
    ),
    FormulaSpec(
        slug="axial-stress",
        name="Axial stress",
        section="Strength of materials",
        equation="sigma = F/A",
        variables={
            "sigma": {"label": "stress", "unit": "Pa"},
            "F": {"label": "force", "unit": "N"},
            "A": {"label": "area", "unit": "m^2"},
        },
    ),
    FormulaSpec(
        slug="axial-strain",
        name="Axial strain",
        section="Strength of materials",
        equation="epsilon = deltaL/L",
        variables={
            "epsilon": {"label": "strain", "unit": ""},
            "deltaL": {"label": "change in length", "unit": "m"},
            "L": {"label": "original length", "unit": "m"},
        },
    ),
    FormulaSpec(
        slug="hookes-law",
        name="Hooke's law",
        section="Strength of materials",
        equation="sigma = E*epsilon",
        variables={
            "sigma": {"label": "stress", "unit": "Pa"},
            "E": {"label": "Young's modulus", "unit": "Pa"},
            "epsilon": {"label": "strain", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="thermal-expansion",
        name="Thermal expansion",
        section="Strength of materials",
        equation="deltaL = alpha*L*deltaT",
        variables={
            "deltaL": {"label": "change in length", "unit": "m"},
            "alpha": {"label": "expansion coefficient", "unit": "1/K"},
            "L": {"label": "original length", "unit": "m"},
            "deltaT": {"label": "temperature change", "unit": "K"},
        },
    ),
    FormulaSpec(
        slug="bending-stress",
        name="Bending stress",
        section="Strength of materials",
        equation="sigma = M*c/I",
        variables={
            "sigma": {"label": "stress", "unit": "Pa"},
            "M": {"label": "bending moment", "unit": "N*m"},
            "c": {"label": "distance to the extreme fibre", "unit": "m"},
            "I": {"label": "second moment of area", "unit": "m^4"},
        },
    ),
    FormulaSpec(
        slug="beam-deflection",
        name="Simply supported, centre load",
        section="Strength of materials",
        equation="delta = F*L^3/(48*E*I)",
        variables={
            "delta": {"label": "deflection", "unit": "m"},
            "F": {"label": "load", "unit": "N"},
            "L": {"label": "span", "unit": "m"},
            "E": {"label": "Young's modulus", "unit": "Pa"},
            "I": {"label": "second moment of area", "unit": "m^4"},
        },
    ),
    FormulaSpec(
        slug="torsion",
        name="Torsional shear stress",
        section="Strength of materials",
        equation="tau = T*r/J",
        variables={
            "tau": {"label": "shear stress", "unit": "Pa"},
            "T": {"label": "torque", "unit": "N*m"},
            "r": {"label": "radius", "unit": "m"},
            "J": {"label": "polar moment of area", "unit": "m^4"},
        },
    ),
    FormulaSpec(
        slug="shaft-power",
        name="Power through a shaft",
        section="Machine design",
        equation="P = 2*pi*N*T/60",
        variables={
            "P": {"label": "power", "unit": "W"},
            "N": {"label": "speed", "unit": "rev/min"},
            "T": {"label": "torque", "unit": "N*m"},
        },
    ),
    FormulaSpec(
        slug="gear-ratio",
        name="Gear ratio",
        section="Machine design",
        equation="n1/n2 = N2/N1",
        variables={
            "n1": {"label": "speed of gear 1", "unit": "rev/min"},
            "n2": {"label": "speed of gear 2", "unit": "rev/min"},
            "N1": {"label": "teeth on gear 1", "unit": ""},
            "N2": {"label": "teeth on gear 2", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="belt-ratio",
        name="Belt speed ratio",
        section="Machine design",
        equation="n1/n2 = D2/D1",
        variables={
            "n1": {"label": "speed of pulley 1", "unit": "rev/min"},
            "n2": {"label": "speed of pulley 2", "unit": "rev/min"},
            "D1": {"label": "diameter 1", "unit": "m"},
            "D2": {"label": "diameter 2", "unit": "m"},
        },
    ),
    FormulaSpec(
        slug="spring-rate",
        name="Helical spring rate",
        section="Machine design",
        equation="k = G*d^4/(8*D^3*N)",
        variables={
            "k": {"label": "spring rate", "unit": "N/m"},
            "G": {"label": "shear modulus", "unit": "Pa"},
            "d": {"label": "wire diameter", "unit": "m"},
            "D": {"label": "mean coil diameter", "unit": "m"},
            "N": {"label": "active coils", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="belt-length",
        name="Open belt length",
        section="Machine design",
        equation="L = 2*C + pi*(D1 + D2)/2 + (D2 - D1)^2/(4*C)",
        variables={
            "L": {"label": "belt length", "unit": "m"},
            "C": {"label": "centre distance", "unit": "m"},
            "D1": {"label": "diameter 1", "unit": "m"},
            "D2": {"label": "diameter 2", "unit": "m"},
        },
    ),
    FormulaSpec(
        slug="ohms-law",
        name="Ohm's law",
        section="Electricity",
        equation="V = I*R",
        variables={
            "V": {"label": "voltage", "unit": "V"},
            "I": {"label": "current", "unit": "A"},
            "R": {"label": "resistance", "unit": "ohm"},
        },
    ),
    FormulaSpec(
        slug="electrical-power",
        name="Electrical power",
        section="Electricity",
        equation="P = V*I",
        variables={
            "P": {"label": "power", "unit": "W"},
            "V": {"label": "voltage", "unit": "V"},
            "I": {"label": "current", "unit": "A"},
        },
    ),
    FormulaSpec(
        slug="simple-interest",
        name="Simple interest",
        section="Engineering economics",
        equation="I = P*r*n",
        variables={
            "I": {"label": "interest", "unit": ""},
            "P": {"label": "principal", "unit": ""},
            "r": {"label": "rate per period", "unit": ""},
            "n": {"label": "periods", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="compound-amount",
        name="Compound amount",
        section="Engineering economics",
        equation="F = P*(1 + i)^n",
        variables={
            "F": {"label": "future worth", "unit": ""},
            "P": {"label": "present worth", "unit": ""},
            "i": {"label": "interest per period", "unit": ""},
            "n": {"label": "periods", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="annuity",
        name="Annuity, future worth",
        section="Engineering economics",
        equation="F = A*((1 + i)^n - 1)/i",
        variables={
            "F": {"label": "future worth", "unit": ""},
            "A": {"label": "annuity", "unit": ""},
            "i": {"label": "interest per period", "unit": ""},
            "n": {"label": "periods", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="depreciation",
        name="Straight-line depreciation",
        section="Engineering economics",
        equation="D = (C - S)/n",
        variables={
            "D": {"label": "annual depreciation", "unit": ""},
            "C": {"label": "first cost", "unit": ""},
            "S": {"label": "salvage value", "unit": ""},
            "n": {"label": "life in years", "unit": ""},
        },
    ),
    FormulaSpec(
        slug="break-even",
        name="Break-even quantity",
        section="Engineering economics",
        equation="Q = FC/(p - vc)",
        variables={
            "Q": {"label": "quantity", "unit": ""},
            "FC": {"label": "fixed cost", "unit": ""},
            "p": {"label": "price per unit", "unit": ""},
            "vc": {"label": "variable cost per unit", "unit": ""},
        },
    ),
)
# endregion


async def seeded(db: AsyncSession) -> int:
    """Put the catalogue in the table, leaving anything already there alone."""
    existing = set(
        (await db.execute(select(Formula.slug))).scalars().all()
    )
    added = 0
    for spec in CATALOGUE:
        if spec.slug in existing:
            continue
        db.add(
            Formula(
                slug=spec.slug,
                name=spec.name,
                section=spec.section,
                equation=spec.equation,
                variables=spec.variables,
                notes=spec.notes,
            )
        )
        added += 1
    if added:
        await db.commit()
    return added


def _parse(expression: str):
    """Parse an expression where ^ means power rather than exclusive or.

    Done by rewriting the operator in the token stream rather than by editing the
    text: string surgery on "a^b" cannot tell a base from a coefficient, which is
    how "0.5*m*v^2" became nonsense. Python's tokenizer already knows where the
    operands are.
    """
    import ast
    import io
    import tokenize

    tokens: list[tuple[int, str]] = []
    for token in tokenize.generate_tokens(io.StringIO(expression).readline):
        if token.type == tokenize.OP and token.string == "^":
            # ** is right-associative and binds tighter than unary minus in Python,
            # which is what a reference sheet means by it.
            tokens.append((tokenize.OP, "**"))
            continue
        if token.type in (tokenize.ENCODING, tokenize.ENDMARKER, tokenize.NEWLINE,
                          tokenize.NL, tokenize.INDENT, tokenize.DEDENT):
            continue
        tokens.append((token.type, token.string))
    rebuilt = " ".join(value for _kind, value in tokens)
    return ast.parse(rebuilt, mode="eval")


def _compile(equation: str):
    """Turn an equation into a callable that returns left minus right.

    `=` becomes a subtraction, so a root is a solution. The names are gathered from
    the equation itself, so a formula can use any symbol it likes.
    """
    import ast

    left, _, right = equation.partition("=")
    expression = f"({left}) - ({right})"
    # Engineering notation writes powers as ^, which is XOR in Python. Rewrite it
    # before parsing, since the formulas come from reference sheets, not from code.
    tree = _parse(expression)

    names: set[str] = set()

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Name):
                names.add(child.id)
            walk(child)

    walk(tree)

    code = compile(tree, "<formula>", "eval")
    allowed = {
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "exp": math.exp,
        "log": math.log,
        "ln": math.log,
        "log10": math.log10,
        "abs": abs,
        "pi": math.pi,
        "e": math.e,
    }

    def evaluate(values: dict[str, float]) -> float:
        scope = dict(allowed)
        scope.update(values)
        return eval(code, {"__builtins__": {}}, scope)

    return evaluate, names


def solve(equation: str, known: dict[str, float], unknown: str) -> float:
    """Find the value of `unknown` that makes the two sides equal.

    A bracketing search then bisection: engineering formulas are well behaved over
    the range a person is asking about, and a method that cannot silently return a
    wrong branch is worth more here than speed.
    """
    evaluate, names = _compile(equation)
    if unknown not in names:
        raise ValueError(f"{unknown} is not part of this formula")

    def f(value: float) -> float:
        trial = dict(known)
        trial[unknown] = value
        return evaluate(trial)

    # Engineering laws are written in magnitudes: a speed is 14 m/s, not -14 m/s.
    # The search runs over positive values first, and only tries negatives when that
    # range has no root, because a square law has two and the reader wants the one a
    # machine could have.
    candidates = [0.0]
    for magnitude in (1e-9, 1e-6, 1e-3, 1.0, 1e2, 1e4, 1e6, 1e9, 1e12):
        candidates.append(magnitude)
    candidates = sorted(set(candidates))

    previous = None
    for value in candidates:
        try:
            current = f(value)
        except (ValueError, ZeroDivisionError):
            previous = None
            continue
        if current == 0:
            return value
        if previous is not None and previous[1] * current < 0:
            low, high = previous[0], value
            for _ in range(200):
                middle = (low + high) / 2
                try:
                    evaluated = f(middle)
                except (ValueError, ZeroDivisionError):
                    break
                if evaluated == 0:
                    return middle
                if f(low) * evaluated < 0:
                    high = middle
                else:
                    low = middle
            return (low + high) / 2
        previous = (value, current)

    # Nothing positive: try negatives, where a squared unknown also has a root.
    for magnitude in (1e-9, 1e-6, 1e-3, 1.0, 1e2, 1e4, 1e6):
        try:
            if abs(f(-magnitude)) < 1e-9:
                return -magnitude
        except (ValueError, ZeroDivisionError):
            continue

    raise ValueError(
        "No solution in the range this formula was searched over. "
        "Check the numbers you entered."
    )

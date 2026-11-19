import { useMemo, useState } from "react";
import { useSolution } from "../workspace/useSolution";
import { create, all, type MathJsInstance } from "mathjs";

/* mathjs knows most SI and imperial units and none of the shop ones, and three of its
   names mean something else (kip is a mass, mil is a thousandth of an inch in one
   system and a millimetre in another). So the missing units are defined here under
   names of their own, and every unit in the table carries the name mathjs is given.
   A unit that is silently the wrong one is worse than a unit that is missing. */
const math = create(all, {}) as MathJsInstance;

const CUSTOM: [string, string][] = [
  ["engKsi", "1000 psi"],
  ["engInHg", "3386.389 Pa"],
  ["engFtH2O", "2989.067 Pa"],
  ["engKip", "1000 lbf"],
  ["engTherm", "105505585.262 J"],
  ["engTonRef", "3516.8528420667 W"],
  ["engFurlong", "201.168 m"],
  ["engChain", "20.1168 m"],
  ["engRod", "5.0292 m"],
  ["engStone", "6.35029318 kg"],
  ["engMil", "0.0000254 m"],
  ["engThou", "0.0000254 m"],
  ["engRpm", "rev/min"],
];

for (const [name, definition] of CUSTOM) {
  try {
    math.createUnit(name, definition);
  } catch {
    /* already defined by an earlier import in the same page */
  }
}

/* Engineering conversion, not a general one.

   Units are grouped by family and, within a family, by system, because that is how
   an engineer looks for one: "the imperial pressures" is a column, not a scroll
   through six mixed lists. The factor shown beside each unit is the definition, so a
   reader can check a conversion by hand rather than trusting the box. */

type UnitSpec = {
  /** The name mathjs is asked for. */
  unit: string;
  /** What the reader sees, and what goes in the answer. */
  label: string;
  note?: string;
};

type Family = {
  name: string;
  /** Systems within the family. Omitted for families with no system split. */
  systems?: { name: string; units: UnitSpec[] }[];
  units?: UnitSpec[];
};

const u = (unitName: string, label: string, note?: string): UnitSpec => ({
  unit: unitName,
  label: label || unitName,
  note,
});

const FAMILIES: Family[] = [
  {
    name: "Length",
    systems: [
      {
        name: "metric",
        units: [
          u("mm", "millimetre"),
          u("cm", "centimetre"),
          u("m", "metre"),
          u("km", "kilometre"),
        ],
      },
      {
        name: "english",
        units: [
          u("in", "inch"),
          u("ft", "foot"),
          u("yd", "yard"),
          u("mi", "mile"),
          u("nmi", "nautical mile"),
        ],
      },
      {
        name: "survey and shop",
        units: [
          u("engMil", "mil", "0.001 in"),
          u("engThou", "thou", "0.001 in"),
          u("engRod", "rod", "16.5 ft"),
          u("engChain", "chain", "66 ft"),
          u("engFurlong", "furlong", "660 ft"),
        ],
      },
    ],
  },
  {
    name: "Area",
    systems: [
      {
        name: "metric",
        units: [u("mm^2", "mm²"), u("cm^2", "cm²"), u("m^2", "m²"), u("km^2", "km²")],
      },
      {
        name: "english",
        units: [u("in^2", "in²"), u("ft^2", "ft²"), u("yd^2", "yd²"), u("mi^2", "mi²")],
      },
      {
        name: "land",
        units: [u("acre", "acre", "43 560 ft²"), u("hectare", "hectare", "10 000 m²")],
      },
    ],
  },
  {
    name: "Volume",
    systems: [
      {
        name: "metric",
        units: [u("mL", "millilitre"), u("L", "litre"), u("cm^3", "cm³"), u("m^3", "m³")],
      },
      {
        name: "english",
        units: [
          u("in^3", "in³"),
          u("ft^3", "ft³"),
          u("floz", "fluid ounce"),
          u("pint", "pint"),
          u("quart", "quart"),
          u("gal", "US gallon", "231 in³"),
        ],
      },
      {
        name: "imperial",
        units: [u("gal", "imperial gallon", "277.42 in³")],
      },
    ],
  },
  {
    name: "Mass",
    systems: [
      {
        name: "metric",
        units: [u("mg", "milligram"), u("g", "gram"), u("kg", "kilogram"), u("t", "tonne")],
      },
      {
        name: "english",
        units: [
          u("oz", "ounce"),
          u("lb", "pound"),
          u("engStone", "stone", "14 lb"),
          u("ton", "US ton", "2000 lb"),
        ],
      },
    ],
  },
  {
    name: "Pressure",
    systems: [
      {
        name: "si",
        units: [
          u("Pa", "pascal", "N/m²"),
          u("kPa", "kilopascal"),
          u("MPa", "megapascal", "N/mm²"),
          u("GPa", "gigapascal"),
        ],
      },
      {
        name: "metric and other",
        units: [
          u("bar", "bar", "100 kPa"),
          u("mbar", "millibar"),
          u("kgf/cm^2", "kgf/cm²", "at"),
          u("atm", "atmosphere", "101 325 Pa"),
          u("torr", "torr", "1/760 atm"),
          u("mmHg", "millimetre of mercury", "133.322 Pa"),
        ],
      },
      {
        name: "english",
        units: [
          u("psi", "pounds per square inch", "lbf/in²"),
          u("engKsi", "kilopounds per square inch", "1000 psi"),
          u("engInHg", "inch of mercury", "3 386 Pa"),
          u("engFtH2O", "foot of water", "2 989 Pa"),
        ],
      },
    ],
  },
  {
    name: "Force",
    systems: [
      {
        name: "si",
        units: [u("N", "newton", "kg·m/s²"), u("kN", "kilonewton"), u("MN", "meganewton")],
      },
      {
        name: "other",
        units: [
          u("kgf", "kilogram-force", "9.80665 N"),
          u("dyne", "dyne", "10⁻⁵ N"),
          u("lbf", "pound-force", "4.44822 N"),
          u("engKip", "kip", "1000 lbf"),
        ],
      },
    ],
  },
  {
    name: "Energy",
    systems: [
      {
        name: "si",
        units: [u("J", "joule", "N·m"), u("kJ", "kilojoule"), u("MJ", "megajoule"), u("Wh", "watt-hour"), u("kWh", "kilowatt-hour")],
      },
      {
        name: "thermal",
        units: [
          u("cal", "calorie", "4.184 J"),
          u("kcal", "kilocalorie"),
          u("BTU", "British thermal unit", "1 055.06 J"),
          u("engTherm", "therm", "105.5 MJ"),
        ],
      },
      {
        name: "other",
        units: [u("eV", "electronvolt"), u("ft lbf", "foot-pound force", "1.35582 J")],
      },
    ],
  },
  {
    name: "Power",
    systems: [
      {
        name: "si",
        units: [u("W", "watt", "J/s"), u("kW", "kilowatt"), u("MW", "megawatt")],
      },
      {
        name: "other",
        units: [
          u("hp", "mechanical horsepower", "745.7 W"),
          u("BTU/h", "BTU per hour", "0.29307 W"),
          u("engTonRef", "ton of refrigeration", "3 516.85 W"),
          u("kcal/h", "kilocalorie per hour", "1.163 W"),
        ],
      },
    ],
  },
  {
    name: "Speed",
    systems: [
      {
        name: "metric",
        units: [u("mm/s", "mm/s"), u("m/s", "m/s"), u("km/h", "km/h"), u("engRpm", "rev per minute")],
      },
      {
        name: "english",
        units: [u("in/s", "in/s"), u("ft/s", "ft/s"), u("ft/min", "ft/min"), u("mph", "mile per hour"), u("knot", "knot")],
      },
    ],
  },
  {
    name: "Temperature",
    units: [
      u("degC", "celsius", "°C"),
      u("degF", "fahrenheit", "°F"),
      u("K", "kelvin", "K"),
      u("degR", "rankine", "°R"),
    ],
  },
  {
    name: "Angle",
    units: [u("rad", "radian"), u("deg", "degree"), u("grad", "gradian"), u("cycle", "revolution")],
  },
  {
    name: "Time",
    systems: [
      {
        name: "si",
        units: [u("ms", "millisecond"), u("s", "second"), u("min", "minute")],
      },
      {
        name: "coarse",
        units: [u("h", "hour"), u("day", "day"), u("week", "week"), u("year", "year")],
      },
    ],
  },
];

export function Converter() {
  const [familyName, setFamilyName] = useState("Pressure");
  const family = FAMILIES.find((item) => item.name === familyName) ?? FAMILIES[0];
  const units = family.systems
    ? family.systems.flatMap((system) => system.units)
    : family.units ?? [];

  const solution = useSolution();
  const [left, setLeft] = useState({ unit: units[0].unit, text: "1" });
  const [right, setRight] = useState({ unit: units[1]?.unit ?? units[0].unit, text: "" });
  /* Which box the reader last typed in. That box keeps exactly what was typed and the
     other is computed from it, the way a search box converts: the value you are
     editing must never be rewritten under your cursor. */
  const [authority, setAuthority] = useState<"left" | "right">("left");

  function pickFamily(name: string) {
    const next = FAMILIES.find((item) => item.name === name) ?? FAMILIES[0];
    const nextUnits = next.systems
      ? next.systems.flatMap((system) => system.units)
      : next.units ?? [];
    setFamilyName(name);
    setLeft({ unit: nextUnits[0].unit, text: "1" });
    setRight({ unit: nextUnits[1]?.unit ?? nextUnits[0].unit, text: "" });
    setAuthority("left");
  }

  const converted = useMemo(() => {
    const from = authority === "left" ? left : right;
    const to = authority === "left" ? right : left;
    const value = Number(from.text);
    if (from.text.trim() === "" || !Number.isFinite(value)) return "";
    try {
      const result = math.unit(value, from.unit).to(to.unit).toNumber();
      return String(Number(result.toPrecision(12)));
    } catch {
      return "—";
    }
  }, [left, right, authority]);

  const leftValue = authority === "left" ? left.text : converted;
  const rightValue = authority === "right" ? right.text : converted;
  const label = (unit: string) => units.find((item) => item.unit === unit)?.label ?? unit;

  return (
    <div className="conv">
      <div className="conv__families">
        {FAMILIES.map((item) => (
          <button
            key={item.name}
            type="button"
            className={`chip${item.name === familyName ? " is-on" : ""}`}
            onClick={() => pickFamily(item.name)}
          >
            {item.name}
          </button>
        ))}
      </div>

      <div className="conv__pair">
        {(
          [
            ["left", left, leftValue],
            ["right", right, rightValue],
          ] as const
        ).map(([side, state, value]) => (
          <div key={side} className="conv__box">
            <input
              value={value}
              inputMode="decimal"
              aria-label={side === "left" ? "First value" : "Second value"}
              onFocus={(event) => event.currentTarget.select()}
              onChange={(event) =>
                side === "left"
                  ? (setLeft({ ...left, text: event.target.value }), setAuthority("left"))
                  : (setRight({ ...right, text: event.target.value }), setAuthority("right"))
              }
            />
            <select
              value={state.unit}
              aria-label={side === "left" ? "First unit" : "Second unit"}
              onChange={(event) =>
                side === "left"
                  ? setLeft({ ...left, unit: event.target.value })
                  : setRight({ ...right, unit: event.target.value })
              }
            >
              {(family.systems ?? [{ name: "", units: family.units ?? [] }]).map((system) => (
                <optgroup key={system.name || "units"} label={system.name}>
                  {system.units.map((option) => (
                    <option key={`${system.name}-${option.unit}-${option.label}`} value={option.unit}>
                      {option.note ? `${option.label} (${option.note})` : option.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
        ))}
      </div>

      <div className="conv__actions">
        <button
          type="button"
          className="btn btn--quiet"
          title="Swap the two units"
          onClick={() => {
            setLeft({ unit: right.unit, text: left.text });
            setRight({ unit: left.unit, text: right.text });
            setAuthority((current) => (current === "left" ? "right" : "left"));
          }}
        >
          ⇄ swap
        </button>
        <span className="muted conv__reading">
          {leftValue && rightValue && (
            <>
              {leftValue} {label(left.unit)} = {rightValue} {label(right.unit)}
            </>
          )}
        </span>
        <button
          type="button"
          className="btn btn--quiet"
          onClick={() =>
            solution.add(
              [
                "**Conversion**",
                "",
                `$$${leftValue}\\ \\text{${escapeTex(label(left.unit))}} = ${rightValue}\\ \\text{${escapeTex(label(right.unit))}}$$`,
              ].join("\n")
            )
          }
        >
          Add to solution
        </button>
      </div>

      {solution.notice && (
        <p className={solution.failed ? "form-error" : "muted"}>{solution.notice}</p>
      )}

      <p className="muted conv__hint">
        Type in either box. The one you are editing is kept exactly as typed and the
        other is worked out from it.
      </p>
    </div>
  );
}

function escapeTex(text: string): string {
  return text.replace(/[\\{}$&#^_%~]/g, (char) => `\\${char}`);
}

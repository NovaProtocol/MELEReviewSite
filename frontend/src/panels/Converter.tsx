import { useMemo, useState } from "react";
import { unit } from "mathjs";

/* Unit conversion through mathjs units: the library already knows the factors and
   the spellings, so there is no table to maintain here. */

const GROUPS: Record<string, string[]> = {
  Length: ["m", "km", "cm", "mm", "in", "ft", "yd", "mi", "nmi"],
  Mass: ["kg", "g", "mg", "t", "lb", "oz", "ton"],
  Time: ["s", "min", "h", "day", "week", "year"],
  Area: ["m^2", "cm^2", "mm^2", "km^2", "ft^2", "in^2", "acre", "hectare"],
  Volume: ["m^3", "L", "mL", "cm^3", "ft^3", "in^3", "gal", "quart"],
  Speed: ["m/s", "km/h", "mph", "knot", "ft/s"],
  Pressure: ["Pa", "kPa", "MPa", "bar", "atm", "psi", "torr", "mmHg"],
  Force: ["N", "kN", "lbf", "kgf", "dyne"],
  Energy: ["J", "kJ", "MJ", "cal", "kcal", "Wh", "kWh", "BTU", "eV"],
  Power: ["W", "kW", "MW", "hp", "BTU/h"],
  Temperature: ["degC", "degF", "K", "degR"],
  Angle: ["rad", "deg", "grad", "cycle"],
};

export function Converter() {
  const [group, setGroup] = useState("Pressure");
  const [amount, setAmount] = useState("1");
  const [from, setFrom] = useState("bar");
  const [to, setTo] = useState("psi");

  const units = GROUPS[group];

  const result = useMemo(() => {
    const value = Number(amount);
    if (!Number.isFinite(value) || !from || !to) return null;
    try {
      const converted = unit(value, from).to(to);
      return converted.toNumber();
    } catch {
      return null;
    }
  }, [amount, from, to]);

  function pickGroup(name: string) {
    setGroup(name);
    setFrom(GROUPS[name][0]);
    setTo(GROUPS[name][1] ?? GROUPS[name][0]);
  }

  return (
    <div className="converter">
      <div className="row">
        <label>
          Quantity
          <select value={group} onChange={(event) => pickGroup(event.target.value)}>
            {Object.keys(GROUPS).map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="converter__grid">
        <label>
          From
          <span className="converter__pair">
            <input
              value={amount}
              inputMode="decimal"
              onChange={(event) => setAmount(event.target.value)}
              aria-label="Value"
            />
            <select value={from} onChange={(event) => setFrom(event.target.value)} aria-label="From unit">
              {units.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </span>
        </label>

        <label>
          To
          <span className="converter__pair">
            <input
              readOnly
              value={result === null ? "" : Number(result.toPrecision(10))}
              aria-label="Result"
            />
            <select value={to} onChange={(event) => setTo(event.target.value)} aria-label="To unit">
              {units.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </span>
        </label>
      </div>

      {result === null ? (
        <p className="form-error">Those units do not convert.</p>
      ) : (
        <p className="muted">
          {amount} {from} = {Number(result.toPrecision(10))} {to}
        </p>
      )}

      <div className="converter__quick">
        {units.map((name) => (
          <button
            key={name}
            className="chip"
            onClick={() => {
              setFrom(to);
              setTo(name);
            }}
            title={`Convert the result into ${name}`}
          >
            → {name}
          </button>
        ))}
      </div>
    </div>
  );
}

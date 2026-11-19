import { useState } from "react";
import { openPanel } from "../workspaceBus";
import { ActivityIcon } from "./ActivityIcon";

/* One rail entry for the whole drawer.

   A calculator, a converter and a formula solver are not three places to be; they
   are three things in one toolbox. Listing them as icons that each look equally
   important made the rail a menu bar. One button, one list, each with its own
   glyph, so the list is scanned rather than read. */

type Entry = { icon: string; label: string; hint: string; open: () => void };

const ENTRIES: Entry[] = [
  {
    icon: "calculator",
    label: "Scientific calculator",
    hint: "Shift-solve, memory, history",
    open: () => openPanel({ kind: "scientific", title: "Scientific calculator" }),
  },
  {
    icon: "converter",
    label: "Unit converter",
    hint: "Engineering units, grouped by system",
    open: () => openPanel({ kind: "converter", title: "Unit converter" }),
  },
  {
    icon: "formula",
    label: "Formula solver",
    hint: "Enter what you know, get the rest",
    open: () => openPanel({ kind: "formula", title: "Formula solver" }),
  },
  {
    icon: "chart",
    label: "Diagrams",
    hint: "Cycle diagrams and plots for a solution",
    open: () => openPanel({ kind: "charts", title: "Diagrams" }),
  },
  {
    icon: "steam",
    label: "Steam and refrigerant tables",
    hint: "Saturated, superheated, dome",
    open: () =>
      openPanel({
        kind: "tool",
        title: "Steam tables",
        params: { slug: "steam", title: "Steam tables" },
      }),
  },
  {
    icon: "psychro",
    label: "Psychrometrics",
    hint: "Air properties, wet bulb, humidity",
    open: () =>
      openPanel({
        kind: "tool",
        title: "Psychrometrics",
        params: { slug: "psychro", title: "Psychrometrics" },
      }),
  },
  {
    icon: "thermo",
    label: "Cycle solver",
    hint: "Carnot, Otto, Diesel, Rankine, Brayton",
    open: () =>
      openPanel({
        kind: "tool",
        title: "Thermo cycle solver",
        params: { slug: "thermo", title: "Thermo cycle solver" },
      }),
  },
  {
    icon: "fluids",
    label: "Pipe flow",
    hint: "Reynolds, friction, head loss",
    open: () =>
      openPanel({
        kind: "tool",
        title: "Pipe flow",
        params: { slug: "fluids", title: "Pipe flow" },
      }),
  },
  {
    icon: "heat",
    label: "Heat transfer",
    hint: "Conduction, convection, exchangers",
    open: () =>
      openPanel({
        kind: "tool",
        title: "Heat transfer",
        params: { slug: "heat", title: "Heat transfer" },
      }),
  },
  {
    icon: "strength",
    label: "Strength of materials",
    hint: "Stress, beams, torsion, shafts",
    open: () =>
      openPanel({
        kind: "tool",
        title: "Strength of materials",
        params: { slug: "strength", title: "Strength of materials" },
      }),
  },
  {
    icon: "machine",
    label: "Machine elements",
    hint: "Belts, gears, bearings, springs",
    open: () =>
      openPanel({
        kind: "tool",
        title: "Machine elements",
        params: { slug: "machine", title: "Machine elements" },
      }),
  },
];

export function ToolsButton({ api }: { api: unknown }) {
  const [open, setOpen] = useState(false);
  void api;

  return (
    <div className="tools-rail">
      <button
        type="button"
        className={`activity__button${open ? " is-active" : ""}`}
        onClick={() => setOpen((value) => !value)}
        title="Tools"
        aria-label="Tools"
        aria-expanded={open}
      >
        <ActivityIcon name="tools" />
        <span>Tools</span>
      </button>

      {open && (
        <>
          <div className="tools-rail__scrim" onClick={() => setOpen(false)} />
          <div className="tools-rail__list" role="menu">
            {ENTRIES.map((entry) => (
              <button
                key={entry.label}
                type="button"
                role="menuitem"
                className="tools-rail__item"
                onClick={() => {
                  setOpen(false);
                  entry.open();
                }}
              >
                <ActivityIcon name={entry.icon} />
                <span className="tools-rail__text">
                  <span className="tools-rail__label">{entry.label}</span>
                  <span className="tools-rail__hint">{entry.hint}</span>
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

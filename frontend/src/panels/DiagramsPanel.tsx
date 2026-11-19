import { useMemo, useState } from "react";
import { useSolution } from "../workspace/useSolution";

/* Diagrams for a solution, produced when asked for.

   Every chart is a URL: /api/charts/<cycle>/<kind>?override_data=<base64>. The image
   is drawn on request and never stored, so the server holds no gallery of pictures
   nobody opened, and a chart pasted into a solution is a link that reproduces itself
   forever rather than a file somebody has to keep.

   The override_data is the whole point of that design: renaming a state, changing a
   title or pinning h2 = h3 travels in the URL, so a reader can reopen a diagram
   somebody else made and edit it, because the link *is* the settings. */

type Cycle = {
  slug: string;
  name: string;
  kinds: { key: string; label: string }[];
  states: string[];
  keywords: string;
};

const CYCLES: Cycle[] = [
  {
    slug: "rankine",
    name: "Rankine cycle",
    kinds: [
      { key: "TS", label: "T-s diagram" },
      { key: "PV", label: "P-v diagram" },
      { key: "schematic", label: "Plant layout" },
    ],
    states: ["1", "2", "3", "4"],
    keywords: "rankine steam turbine boiler condenser pump",
  },
  {
    slug: "brayton",
    name: "Brayton cycle",
    kinds: [
      { key: "TS", label: "T-s diagram" },
      { key: "PV", label: "P-v diagram" },
    ],
    states: ["1", "2", "3", "4"],
    keywords: "brayton gas turbine compressor combustion",
  },
  {
    slug: "otto",
    name: "Otto cycle",
    kinds: [
      { key: "TS", label: "T-s diagram" },
      { key: "PV", label: "P-v diagram" },
    ],
    states: ["1", "2", "3", "4"],
    keywords: "otto spark ignition petrol gasoline",
  },
  {
    slug: "diesel",
    name: "Diesel cycle",
    kinds: [
      { key: "TS", label: "T-s diagram" },
      { key: "PV", label: "P-v diagram" },
    ],
    states: ["1", "2", "3", "4"],
    keywords: "diesel compression ignition",
  },
  {
    slug: "carnot",
    name: "Carnot cycle",
    kinds: [
      { key: "TS", label: "T-s diagram" },
      { key: "PV", label: "P-v diagram" },
    ],
    states: ["1", "2", "3", "4"],
    keywords: "carnot reversible ideal",
  },
  {
    slug: "vapor-compression",
    name: "Vapour compression",
    kinds: [
      { key: "TS", label: "T-s diagram" },
      { key: "PH", label: "P-h diagram" },
    ],
    states: ["1", "2", "3", "4"],
    keywords: "refrigeration vapor compression evaporator condenser",
  },
  {
    slug: "psychrometric",
    name: "Psychrometric chart",
    kinds: [{ key: "chart", label: "Chart" }],
    states: [],
    keywords: "psychrometric humidity air conditioning",
  },
];

type Override = {
  title?: string;
  labels?: Record<string, string>;
  notes?: string[];
};

export function DiagramsPanel() {
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<Cycle | null>(null);
  const [kind, setKind] = useState("TS");
  const [override, setOverride] = useState<Override>({});
  const solution = useSolution();
  const [copied, setCopied] = useState("");

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return CYCLES;
    return CYCLES.filter((cycle) =>
      `${cycle.name} ${cycle.keywords}`.toLowerCase().includes(needle)
    );
  }, [query]);

  function pick(cycle: Cycle) {
    setChosen(cycle);
    setKind(cycle.kinds[0].key);
    setOverride({});
  }

  const encoded = useMemo(() => {
    const clean: Override = {};
    if (override.title) clean.title = override.title;
    if (override.notes?.length) clean.notes = override.notes.filter(Boolean);
    if (override.labels && Object.values(override.labels).some(Boolean)) {
      clean.labels = Object.fromEntries(
        Object.entries(override.labels).filter(([, value]) => value)
      ) as Record<string, string>;
    }
    if (!Object.keys(clean).length) return "";
    return btoa(JSON.stringify(clean));
  }, [override]);

  const src = chosen
    ? `/api/charts/${chosen.slug}/${kind}${encoded ? `?override_data=${encodeURIComponent(encoded)}` : ""}`
    : "";

  return (
    <div className="diagrams">
      <div className="diagrams__list">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="rankine, otto, psychrometric..."
          aria-label="Search diagrams"
        />
        {results.map((cycle) => (
          <button
            key={cycle.slug}
            type="button"
            className={`diagrams__item${chosen?.slug === cycle.slug ? " is-on" : ""}`}
            onClick={() => pick(cycle)}
          >
            {cycle.name}
          </button>
        ))}
        {results.length === 0 && <p className="muted pad">Nothing matches.</p>}
      </div>

      <div className="diagrams__work">
        {!chosen ? (
          <p className="muted pad">Pick a diagram on the left.</p>
        ) : (
          <>
            <div className="diagrams__kinds">
              {chosen.kinds.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  className={`chip${kind === option.key ? " is-on" : ""}`}
                  onClick={() => setKind(option.key)}
                >
                  {option.label}
                </button>
              ))}
            </div>

            <img className="diagrams__preview" src={src} alt={`${chosen.name} ${kind}`} />

            {/* The settings, and the same settings as a link. The link is how a
                diagram is embedded, and how somebody else can pick it up and edit
                it: everything needed to redraw it is in the URL. */}
            <label className="field">
              Title
              <input
                value={override.title ?? ""}
                placeholder={chosen.name}
                onChange={(event) => setOverride({ ...override, title: event.target.value })}
              />
            </label>

            {chosen.states.length > 0 && (
              <div className="diagrams__labels">
                {chosen.states.map((state) => (
                  <label key={state} className="diagrams__label">
                    <span>state {state}</span>
                    <input
                      value={override.labels?.[state] ?? ""}
                      placeholder={state}
                      onChange={(event) =>
                        setOverride({
                          ...override,
                          labels: { ...override.labels, [state]: event.target.value },
                        })
                      }
                    />
                  </label>
                ))}
              </div>
            )}

            <label className="field">
              Notes, one per line
              <textarea
                rows={2}
                value={(override.notes ?? []).join("\n")}
                placeholder="h2 = h3"
                onChange={(event) => setOverride({ ...override, notes: event.target.value.split("\n") })}
              />
            </label>

            <div className="diagrams__actions">
              <button
                type="button"
                className="btn btn--primary"
                onClick={() =>
                  solution.add(
                    [
                      `**${override.title || chosen.name} — ${kind}**`,
                      "",
                      `![${chosen.name} ${kind}](${src})`,
                      ...(override.notes?.filter(Boolean).map((note) => `\n*${note}*`) ?? []),
                    ].join("\n")
                  )
                }
              >
                Add to solution
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => copyText(`${window.location.origin}${src}`, setCopied)}
              >
                {copied || "Copy link"}
              </button>
            </div>

            {solution.notice && (
              <p className={solution.failed ? "form-error" : "muted"}>{solution.notice}</p>
            )}
            <p className="muted diagrams__link">
              The link carries the settings, so reopening it reproduces this exact
              diagram and anyone can rename a state or add a note from it.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

/* Clipboard access needs a secure context, and this app is served over plain http on
   a LAN address, where navigator.clipboard is undefined. So fall back to the old
   selection trick, and if even that is refused, say so — a button that silently does
   nothing is worse than no button. */
function copyText(text: string, report: (message: string) => void) {
  const selectAndCopy = () => {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  };
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(
      () => report("Copied"),
      () => report(selectAndCopy() ? "Copied" : "Copy failed")
    );
    return;
  }
  report(selectAndCopy() ? "Copied" : "Copy failed");
}

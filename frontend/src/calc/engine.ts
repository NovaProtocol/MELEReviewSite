/* The part of a calculator that is not the plastic.

   Every scientific calculator does the same arithmetic; what differs is the legend
   printed on the keys and where the shift button sits. So the brain lives here once
   — one parser, one angle mode, one solver behind SHIFT-SOLVE — and each skin only
   decides how the keys look and what they are called. Two calculators open side by
   side behave identically because they are the same object.

   The solver is the piece that matters for a board exam: you are given an equation
   with one unknown and four printed answers, and the calculator has to find the
   unknown rather than you rearranging by hand. It works numerically, so it does not
   care whether the unknown can be isolated algebraically — which is exactly the case
   that breaks hand rearrangement. */

export type AngleMode = "DEG" | "RAD";

const FUNCTIONS: Record<string, (value: number, degrees: boolean) => number> = {
  sin: (value, degrees) => Math.sin(degrees ? (value * Math.PI) / 180 : value),
  cos: (value, degrees) => Math.cos(degrees ? (value * Math.PI) / 180 : value),
  tan: (value, degrees) => Math.tan(degrees ? (value * Math.PI) / 180 : value),
  asin: (value, degrees) => (degrees ? (Math.asin(value) * 180) / Math.PI : Math.asin(value)),
  acos: (value, degrees) => (degrees ? (Math.acos(value) * 180) / Math.PI : Math.acos(value)),
  atan: (value, degrees) => (degrees ? (Math.atan(value) * 180) / Math.PI : Math.atan(value)),
  sinh: (value) => Math.sinh(value),
  cosh: (value) => Math.cosh(value),
  tanh: (value) => Math.tanh(value),
  sqrt: (value) => Math.sqrt(value),
  cbrt: (value) => Math.cbrt(value),
  ln: (value) => Math.log(value),
  log: (value) => Math.log10(value),
  exp: (value) => Math.exp(value),
  abs: (value) => Math.abs(value),
};

/** Longest first, so `asin` is not read as `a*sin`. */
const NAMES = Object.keys(FUNCTIONS).sort((a, b) => b.length - a.length);

/** What the keys put on the screen, turned into what the parser reads. */
export function normalise(source: string): string {
  return source
    .replace(/×/g, "*")
    .replace(/÷/g, "/")
    .replace(/−/g, "-")
    .replace(/,/g, "");
}

type Resolver = (name: string) => number;

function parse(text: string, degrees: boolean, resolve: Resolver): number {
  let at = 0;

  const skip = () => {
    while (at < text.length && text[at] === " ") at += 1;
  };

  function expression(): number {
    let value = term();
    for (;;) {
      skip();
      const char = text[at];
      if (char !== "+" && char !== "-") return value;
      at += 1;
      const right = term();
      value = char === "+" ? value + right : value - right;
    }
  }

  function term(): number {
    let value = unary();
    for (;;) {
      skip();
      const char = text[at];
      if (char === "*" || char === "/") {
        at += 1;
        const right = unary();
        value = char === "*" ? value * right : value / right;
        continue;
      }
      // Implicit multiplication, the way the screen writes it: 2π, 3(4+1), 2sin30.
      if (char !== undefined && (char === "(" || char === "√" || /[0-9.A-Za-zπ]/.test(char))) {
        value *= unary();
        continue;
      }
      return value;
    }
  }

  function unary(): number {
    skip();
    if (text[at] === "-") {
      at += 1;
      return -unary();
    }
    if (text[at] === "+") {
      at += 1;
      return unary();
    }
    return power();
  }

  function power(): number {
    const base = atom();
    skip();
    if (text[at] !== "^") return base;
    at += 1;
    // Right associative, and the exponent may carry its own sign.
    return Math.pow(base, unary());
  }

  function atom(): number {
    skip();
    const char = text[at];

    if (char === "(") {
      at += 1;
      const value = expression();
      skip();
      if (text[at] === ")") at += 1;
      return value;
    }

    if (char === "√") {
      at += 1;
      return Math.sqrt(unary());
    }

    if (char === "π") {
      at += 1;
      return Math.PI;
    }

    if (char !== undefined && /[0-9.]/.test(char)) {
      const start = at;
      while (at < text.length && /[0-9.]/.test(text[at])) at += 1;
      return Number(text.slice(start, at));
    }

    if (char !== undefined && /[A-Za-z]/.test(char)) {
      for (const name of NAMES) {
        if (text.startsWith(name, at)) {
          at += name.length;
          return FUNCTIONS[name](unary(), degrees);
        }
      }
      if (char === "e") {
        at += 1;
        return Math.E;
      }
      at += 1;
      return resolve(char);
    }

    // Anything else is a keypress the parser does not know. Returning NaN makes the
    // caller report a bad expression rather than a plausible wrong number.
    at += 1;
    return Number.NaN;
  }

  const value = expression();
  skip();
  if (at < text.length) {
    throw new SyntaxError(`Cannot read “${text.slice(at).trim()}”.`);
  }
  return value;
}

export type Compiled = {
  names: string[];
  /** Variables read as NaN while the names are collected, so evaluating without a
   *  value for one of them reports that rather than answering. */
  evaluate: (scope: Record<string, number>) => number;
};

export function compile(source: string, degrees = true): Compiled {
  const text = normalise(source);
  const names = new Set<string>();

  parse(text, degrees, (name) => {
    names.add(name);
    return Number.NaN;
  });

  return {
    names: [...names],
    evaluate(scope) {
      return parse(text, degrees, (name) => {
        const value = scope[name];
        if (value === undefined || !Number.isFinite(value)) {
          throw new Error(`${name} has no value`);
        }
        return value;
      });
    },
  };
}

export type SolveResult =
  | { ok: true; value: number; residual: number; iterations: number }
  | { ok: false; error: string };

/** SHIFT-SOLVE: the value of `unknown` that makes the expression zero.

 *  The same approach the formula solver uses, for the same reason: an exam equation
 *  is often not isolatable — the unknown sits inside a logarithm and outside it too —
 *  and a method that cannot return a wrong branch by accident is worth more here than
 *  speed. It walks outwards from the guess, then bisects the bracket it finds.
 */
export function solve(
  source: string,
  unknown: string,
  degrees: AngleMode,
  guess = 1
): SolveResult {
  const raw = normalise(source);
  // "left = right" becomes "left - right", whose root is the solution.
  const text = raw.includes("=")
    ? raw.replace("=", "-(") + ")"
    : raw;

  let compiled: Compiled;
  try {
    compiled = compile(text);
  } catch (error) {
    return { ok: false, error: (error as Error).message };
  }
  if (!compiled.names.includes(unknown)) {
    return { ok: false, error: `There is no ${unknown} in that expression.` };
  }

  const evaluateAt = (value: number): number => {
    try {
      return parseInMode(text, degrees, value, unknown);
    } catch {
      return Number.NaN;
    }
  };

  /* Walk outwards from the guess, one direction at a time. Two independent walks
     rather than one alternating sweep: an expression with a logarithm or a square
     root has no value on one side, and a single sweep would lose the bracket it had
     already built every time it stepped into that hole. */
  const offsets = [0, 1e-6, 1e-4, 1e-2, 0.1, 1, 2, 5, 10, 20, 50, 100, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8];

  for (const direction of [1, -1]) {
    let previous: { x: number; y: number } | null = null;
    for (const offset of offsets) {
      const x = guess + direction * offset;
      const y = evaluateAt(x);
      if (!Number.isFinite(y)) {
        previous = null;
        continue;
      }
      if (Math.abs(y) < 1e-12) return { ok: true, value: x, residual: y, iterations: 0 };
      if (previous && previous.y * y < 0) {
        let low = previous.x;
        let high = x;
        let lowValue = previous.y;
        for (let iteration = 0; iteration < 200; iteration += 1) {
          const middle = (low + high) / 2;
          const value = evaluateAt(middle);
          if (!Number.isFinite(value)) break;
          const done =
            Math.abs(value) < 1e-12 ||
            Math.abs(high - low) < 1e-14 * Math.max(1, Math.abs(high)) ||
            iteration === 199;
          if (done) return { ok: true, value: middle, residual: value, iterations: iteration };
          if (lowValue * value < 0) {
            high = middle;
          } else {
            low = middle;
            lowValue = value;
          }
        }
      }
      previous = { x, y };
    }
  }

  return {
    ok: false,
    error: `No solution near ${format(guess)}. Try another guess, or check the equation.`,
  };
}

/** Parse with the unknown bound and everything else resolved from the same parse.
 *  Kept separate so the solver never allocates a scope object per trial. */
function parseInMode(text: string, degrees: AngleMode, value: number, unknown: string): number {
  return parse(text, degrees === "DEG", (name) => {
    if (name === unknown) return value;
    throw new Error(`${name} has no value`);
  });
}

/** Ten significant figures, exponent notation when it will not fit on a screen. */
export function format(value: number): string {
  if (!Number.isFinite(value)) return "Math ERROR";
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude < 1e-9 || magnitude >= 1e10) {
    const [mantissa, exponent] = value.toExponential(6).split("e");
    return `${Number(mantissa)}×10^${Number(exponent)}`;
  }
  return String(Number(value.toPrecision(10)));
}

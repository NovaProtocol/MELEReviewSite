import { useCallback, useState } from "react";
import { appendToSolution } from "./solutionBus";

/* One place for "did it land?".

   Before this, a tool reported success whether or not a solution pane was open,
   because the bus kept the text for later. It does not any more: adding with nothing
   open is a no-op, and the tool has to say so. */
export function useSolution() {
  const [notice, setNotice] = useState("");
  const [failed, setFailed] = useState(false);

  const add = useCallback((markdown: string) => {
    const result = appendToSolution(markdown);
    setFailed(!result.ok);
    setNotice(result.ok ? "Added to your solution" : result.reason);
    window.setTimeout(() => setNotice(""), 4500);
    return result.ok;
  }, []);

  return { notice, failed, add };
}

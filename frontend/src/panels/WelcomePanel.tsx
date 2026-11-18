import { openPanel } from "../workspaceBus";
import { bootstrap } from "../tools";

/* What you see when the canvas is empty.

   A blank grey rectangle is a dead end: it says nothing about what the site is or
   how to get back to work. This is the same place, with the three ways in. */
export function WelcomePanel() {
  return (
    <div className="welcome">
      <h2 className="welcome__title">MELE Review</h2>
      <p className="muted">A question bank with worked solutions, and the tools for working them out.</p>

      <div className="welcome__cards">
        <button type="button" className="welcome__card" onClick={() => openPanel({ kind: "resource", title: "Resources", params: { topicId: "1" } })}>
          <strong>Library</strong>
          <span>The notes and reference sheets for every topic.</span>
        </button>
        <button
          type="button"
          className="welcome__card"
          onClick={() => openPanel({ kind: "problems", title: "Problems", params: { topicId: "1" } })}
        >
          <strong>Problem sets</strong>
          <span>Answer a question, then read how other people solved it.</span>
        </button>
        <button
          type="button"
          className="welcome__card"
          onClick={() => openPanel({ kind: "scientific", title: "Scientific calculator" })}
        >
          <strong>Tools</strong>
          <span>A calculator, a converter, steam tables and the formula index.</span>
        </button>
      </div>

      <ul className="welcome__tips muted">
        <li>Drag a tab to move a panel. Drop it on an edge to split the window.</li>
        <li>Panels of one kind stack together; a calculator will not join a question.</li>
        <li>The explorer on the left cannot be closed, but you can move it.</li>
        <li>Your layout is remembered in this browser.</li>
      </ul>

      {bootstrap.viewer.is_admin && (
        <p className="muted">Administrators also have the Admin panel on the left.</p>
      )}
    </div>
  );
}

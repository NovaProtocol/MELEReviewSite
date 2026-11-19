import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/* A menu on a row of the explorer.

   The moves are the ones code-server's file tree offers and the ones this tree can
   honour: open, open to the side, copy the address, and hide the branch. Nothing
   here is a mutation of the bank, because the explorer is a map, not an editor. */

export type RowAction = { label: string; run: () => void; disabled?: boolean };

export function useRowMenu(actions: () => RowAction[]) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!at) return;
    const dismiss = (event: Event) => {
      if (ref.current?.contains(event.target as Node)) return;
      setAt(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAt(null);
    };
    window.addEventListener("pointerdown", dismiss);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", dismiss);
      window.removeEventListener("keydown", escape);
    };
  }, [at]);

  const handlers = {
    onContextMenu: (event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const width = 190;
      const height = 40 + actions().length * 26;
      setAt({
        x: Math.max(4, Math.min(event.clientX, window.innerWidth - width - 8)),
        y: Math.max(4, Math.min(event.clientY, window.innerHeight - height - 8)),
      });
    },
  };

  const menu = at
    ? createPortal(
        <div
          className="tabmenu"
          role="menu"
          style={{ position: "fixed", left: at.x, top: at.y }}
          onPointerDown={(event) => event.stopPropagation()}
          ref={ref}
        >
          {actions().map((action) => (
            <button
              key={action.label}
              type="button"
              role="menuitem"
              className="tabmenu__item"
              disabled={action.disabled}
              onClick={(event) => {
                event.stopPropagation();
                setAt(null);
                action.run();
              }}
            >
              {action.label}
            </button>
          ))}
        </div>,
        document.body
      )
    : null;

  return { handlers, menu };
}

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { DockviewApi, DockviewPanelApi } from "dockview";
import { canClose, typeOf } from "./panelTypes";
import { closePanel } from "./closing";
import { isMinimized, toggle as toggleMinimize } from "./minimize";

/* A tab, and the menu on it.

   The menu is the code-server set, because those are the moves a reader actually
   makes: close this, close the others, split the way they are looking, and float it
   into a window of its own. All of it is layout, never content. */

type MenuItem = { label: string; run: () => void; disabled?: boolean };

export function PanelTab(props: { api: DockviewPanelApi; containerApi: DockviewApi }) {
  const { api, containerApi } = props;
  const kind = api.id.split("|")[0];
  const title = api.title ?? kind;

  // A spacer holds space while a panel is minimised. It is not something to read or
  // click, so it gets no tab at all.
  if (kind === "filler") return null;
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menu) return;
    const dismiss = (event: Event) => {
      if (ref.current?.contains(event.target as Node)) return;
      setMenu(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(null);
    };
    window.addEventListener("pointerdown", dismiss);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", dismiss);
      window.removeEventListener("keydown", escape);
    };
  }, [menu]);

  function items(): MenuItem[] {
    const group = api.group;
    const others = group.panels.filter((panel) => panel.id !== api.id);
    const sameType = others.filter((panel) => typeOf(panel.id.split("|")[0]) === typeOf(kind));
    const params = (api as unknown as { params?: Record<string, string> }).params ?? {};

    return [
      { label: "Close", disabled: !canClose(kind), run: () => closePanel(api) },
      {
        label: "Close others",
        disabled: sameType.length === 0,
        run: () => {
          for (const panel of sameType) panel.api.close();
        },
      },
      {
        label: "Split right",
        run: () =>
          containerApi.addPanel({
            id: `${kind}|copy:${Math.random().toString(36).slice(2, 8)}`,
            component: kind,
            title,
            params,
            position: { referencePanel: api.id, direction: "right" },
          }),
      },
      {
        label: "Split down",
        run: () =>
          containerApi.addPanel({
            id: `${kind}|copy:${Math.random().toString(36).slice(2, 8)}`,
            component: kind,
            title,
            params,
            position: { referencePanel: api.id, direction: "below" },
          }),
      },
      {
        // A strip is a column that has stepped aside; it is not a window, so a
        // floating group keeps the size the reader gave it.
        label: isMinimized(api.group.id) ? "Restore" : "Minimise",
        disabled: api.group.api.location.type === "floating",
        run: () => toggleMinimize(containerApi, api.group),
      },
      {
        label: "Float",
        run: () =>
          containerApi.addFloatingGroup(api.group, { x: 160, y: 120, width: 460, height: 520 }),
      },
    ];
  }

  return (
    <div
      className="panel-tab"
      ref={ref}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
        /* Position from the tab's own rect, not the pointer.

           dockview mounts panels in a transformed layer, so a `fixed` child is
           positioned against that layer rather than the viewport: clientX put the
           menu thousands of pixels away. The tab's rect is in the same coordinate
           space, so anchoring to it is correct regardless of the transform. */
        const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
        const width = 190;
        const height = 170;
        setMenu({
          x: Math.max(4, Math.min(box.left, window.innerWidth - width - 8)),
          y: Math.min(box.bottom + 2, window.innerHeight - height - 8),
        });
      }}
    >
      <span className="panel-tab__title">{title}</span>
      {canClose(kind) && (
        <button
          type="button"
          className="panel-tab__close"
          aria-label={`Close ${title}`}
          title={`Close ${title}`}
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            closePanel(api);
          }}
        >
          ×
        </button>
      )}

      {menu &&
        createPortal(
          <div
            className="tabmenu"
            role="menu"
            style={{ position: "fixed", left: menu.x, top: menu.y }}
            onPointerDown={(event) => event.stopPropagation()}
          >
          {items().map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className="tabmenu__item"
              disabled={item.disabled}
              onClick={(event) => {
                event.stopPropagation();
                setMenu(null);
                item.run();
              }}
            >
              {item.label}
            </button>
            ))}
          </div>,
          document.body
        )}
    </div>
  );
}

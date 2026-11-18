import type { IDockviewPanelHeaderProps } from "dockview";
import { canClose } from "./panelTypes";
import { closePanel } from "./closing";

/* The tab, drawn by us.

   dockview's default tab always carries a close button, and the explorer is not
   closeable: it is the thing that says what there is, so losing it leaves a
   workspace with no map back. A custom tab is the only place to make that true,
   because dockview has no will-remove hook to refuse the close. */
export function PanelTab(props: IDockviewPanelHeaderProps) {
  const kind = props.api.id.split("|")[0];
  const title = props.api.title ?? kind;

  return (
    <span className="panel-tab">
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
            closePanel(props.api);
          }}
        >
          ×
        </button>
      )}
    </span>
  );
}

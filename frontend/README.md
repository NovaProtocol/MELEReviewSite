# Workspace client

The dockable workspace, built with React, TypeScript and Vite. It is one route,
`/app`, served by the FastAPI app; every other page is still Jinja.

```bash
npm install
npm run build     # writes ../app/static/app, which the shell route reads
```

The build is part of the Docker image (`Dockerfile`, stage `client`), so a deploy
does not need Node on the machine.

## Shape

- `src/App.tsx` — header, activity bar, and the spawn requests.
- `src/Workspace.tsx` — dockview setup, layout persistence, and the stacked layout
  used below 900px.
- `src/panels/` — the tools. `Scientific`, `Converter` and `FormulaSearch` are
  native; specialist calculators are frames of their existing pages, so they stay
  isolated and cannot corrupt each other's state.
- `src/tools.ts` — the bootstrap payload the server renders into the page: viewer,
  specialist catalogue, endpoints.

## Adding a tool

Add it to `TOOLS` in `app/routes/tools.py`; it appears in the activity bar with no
client change. A native panel also needs a component entry in `Workspace.tsx` and
a key in `PanelKind`.

## Layouts

dockview serialises the layout; it is stored in `localStorage` under
`mele.workspace.v1`. A parse failure clears it and rebuilds the default rather than
showing a blank workspace, and "reset" on the rail restores the default.

/* The workspace catalogue. The server passes the specialist tools in the
   bootstrap payload, so a tool added on the Python side appears here without a
   second list to keep in step. */

export type SpecialistTool = {
  slug: string;
  name: string;
  group: string;
};

export type Viewer = {
  username: string;
  avatar: string | null;
  is_admin: boolean;
  signed_in?: boolean;
};

export type Bootstrap = {
  viewer: Viewer;
  specialists: SpecialistTool[];
  formulas_url: string;
  library_url: string;
};

export type PanelKind =
  | "library"
  | "problems"
  | "question"
  | "notes"
  | "scientific"
  | "converter"
  | "formula"
  | "tool";

export type PanelSpec = {
  kind: PanelKind;
  slug?: string;
  title: string;
  params?: Record<string, string>;
};

declare global {
  interface Window {
    __MELE__: Bootstrap;
  }
}

export const bootstrap: Bootstrap =
  window.__MELE__ ?? {
    viewer: { username: "guest", avatar: null, is_admin: false },
    specialists: [],
    formulas_url: "/api/formulas",
    library_url: "/library",
  };

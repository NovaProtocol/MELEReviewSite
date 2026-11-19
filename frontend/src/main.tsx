import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Router } from "./Router";
import "./styles.css";
/* Typeset formulas need KaTeX's stylesheet as well as its script; without it the
   output is right but every glyph is unstyled, which reads as broken. */
import "katex/dist/katex.min.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Router />
  </StrictMode>
);

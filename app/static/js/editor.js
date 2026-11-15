/* A Markdown editor with a rich-text view of the same text.

   The stored value is always Markdown. Switching to rich text sends the source to
   the server and shows the HTML the reader will see, so there is one parser and
   no chance of the editor and the page disagreeing. Switching back serialises the
   DOM into Markdown in the browser, because the DOM is already parsed there.

   Media is uploaded, not linked: the insert is `![](/media/<uid>)`, a path on this
   site. A stored question therefore survives a change of domain.
*/
(function () {
"use strict";

const { api, apiJson, escapeHtml } = window.MELE_API;

const TOOLS = [
  { id: "bold", label: "B", title: "Bold", md: ["**", "**"], rich: () => document.execCommand("bold") },
  { id: "italic", label: "I", title: "Italic", md: ["*", "*"], rich: () => document.execCommand("italic") },
  { id: "strike", label: "S", title: "Strikethrough", md: ["~~", "~~"], rich: () => document.execCommand("strikeThrough") },
  { id: "sup", label: "X\u00b2", title: "Superscript", md: ["^", "^"], rich: () => document.execCommand("superscript") },
  { id: "heading", label: "H", title: "Heading", md: ["## ", ""], rich: () => document.execCommand("formatBlock", false, "h2") },
  { id: "quote", label: "\u201c", title: "Quote", md: ["> ", ""], rich: () => document.execCommand("formatBlock", false, "blockquote") },
  { id: "code", label: "</>", title: "Code block", md: ["```\n", "\n```"], rich: () => document.execCommand("formatBlock", false, "pre") },
  { id: "list", label: "\u2022", title: "Bulleted list", md: ["- ", ""], rich: () => document.execCommand("insertUnorderedList") },
  { id: "number", label: "1.", title: "Numbered list", md: ["1. ", ""], rich: () => document.execCommand("insertOrderedList") },
  { id: "spoiler", label: "Spoiler", title: "Spoiler", md: [">!", "!<"], rich: "spoiler" },
  { id: "link", label: "\u2197", title: "Link", md: null, rich: "link" },
  { id: "table", label: "\u25a6", title: "Table", md: null, rich: "table" },
  { id: "media", label: "Image", title: "Image", md: null, rich: "media" },
];

function serialise(node) {
  const out = [];
  for (const child of node.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) {
      out.push(child.nodeValue.replace(/\u00a0/g, " "));
      continue;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    const tag = child.tagName.toLowerCase();
    const inner = () => serialise(child);
    if (tag === "br") out.push("\n");
    else if (tag === "strong" || tag === "b") out.push(`**${inner()}**`);
    else if (tag === "em" || tag === "i") out.push(`*${inner()}*`);
    else if (tag === "del" || tag === "s" || tag === "strike") out.push(`~~${inner()}~~`);
    else if (tag === "sup") out.push(`^${inner()}^`);
    else if (tag === "code") out.push(`\`${inner()}\``);
    else if (tag === "a") out.push(`[${inner()}](${child.getAttribute("href") || ""})`);
    else if (tag === "img") out.push(`![](${child.getAttribute("src") || ""})`);
    else if (child.classList && child.classList.contains("md-spoiler")) out.push(`>!${inner()}!<`);
    else if (tag === "h1" || tag === "h2" || tag === "h3") {
      const marks = tag === "h1" ? "# " : tag === "h2" ? "## " : "### ";
      out.push(`\n${marks}${inner()}\n\n`);
    } else if (tag === "blockquote") out.push(`\n> ${inner().trim()}\n\n`);
    else if (tag === "pre") out.push(`\n\`\`\`\n${child.textContent}\n\`\`\`\n\n`);
    else if (tag === "ul" || tag === "ol") {
      const lines = [];
      let marker = 1;
      for (const item of child.querySelectorAll(":scope > li")) {
        lines.push((tag === "ol" ? `${marker++}. ` : "- ") + serialise(item).trim());
      }
      out.push(`\n${lines.join("\n")}\n\n`);
    } else if (tag === "table") {
      out.push(`\n${table(child)}\n\n`);
    } else if (tag === "div" || tag === "p" || tag === "section") {
      const body = inner();
      out.push(`\n${body.trim()}\n`);
    } else out.push(inner());
  }
  return out.join("");
}

function table(node) {
  const rows = [...node.querySelectorAll("tr")].map((tr) =>
    [...tr.children].map((cell) => serialise(cell).trim() || " ")
  );
  if (!rows.length) return "";
  const width = rows[0].length;
  const line = (cells) => `| ${cells.join(" | ")} |`;
  const out = [line(rows[0]), `|${" --- |".repeat(width)}`];
  for (const row of rows.slice(1)) out.push(line(row));
  return out.join("\n");
}

function tidy(source) {
  return source
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

function create(root) {
  if (!root) return null;
  const source = root.querySelector(".editor__source");
  const rich = root.querySelector(".editor__rich");
  const bar = root.querySelector(".editor__tools");
  const mediaPanel = root.querySelector(".editor__media");
  let mode = "markdown";

  /* ---- Markdown mode helpers ---- */
  function surround(before, after) {
    const start = source.selectionStart;
    const end = source.selectionEnd;
    const chosen = source.value.slice(start, end);
    source.value = source.value.slice(0, start) + before + chosen + after + source.value.slice(end);
    source.focus();
    source.selectionStart = start + before.length;
    source.selectionEnd = start + before.length + chosen.length;
  }

  /* ---- Rich mode helpers ---- */
  function insertHtml(html) {
    rich.focus();
    document.execCommand("insertHTML", false, html);
  }

  function selectedText() {
    return window.getSelection ? window.getSelection().toString() : "";
  }

  async function toRich() {
    if (mode === "rich") return;
    const response = await apiJson("/api/editor/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown: source.value }),
    });
    rich.innerHTML = response.html || "<p><br></p>";
    source.hidden = true;
    rich.hidden = false;
    mode = "rich";
    root.dataset.mode = "rich";
  }

  function toMarkdown() {
    if (mode === "markdown") return;
    source.value = tidy(serialise(rich));
    rich.hidden = true;
    source.hidden = false;
    mode = "markdown";
    root.dataset.mode = "markdown";
  }

  function apply(tool) {
    if (mode === "markdown") {
      if (tool.md) {
        surround(tool.md[0], tool.md[1]);
        return;
      }
      if (tool.rich === "link") {
        const url = window.prompt("Link address", "https://");
        if (!url) return;
        surround("[", `](${url})`);
        return;
      }
      if (tool.rich === "table") {
        surround("| Column | Column |\n| --- | --- |\n| Cell | Cell |\n", "");
        return;
      }
      if (tool.rich === "media") {
        openMedia();
        return;
      }
      return;
    }

    rich.focus();
    if (tool.rich === "spoiler") {
      const chosen = selectedText() || "spoiler";
      insertHtml(`<span class="md-spoiler">${escapeHtml(chosen)}</span>`);
      return;
    }
    if (tool.rich === "link") {
      const url = window.prompt("Link address", "https://");
      if (!url) return;
      if (selectedText()) document.execCommand("createLink", false, url);
      else insertHtml(`<a href="${escapeHtml(url)}">${escapeHtml(url)}</a>`);
      return;
    }
    if (tool.rich === "table") {
      insertHtml(
        '<table class="md-table"><thead><tr><th>Column</th><th>Column</th></tr></thead>' +
          "<tbody><tr><td>Cell</td><td>Cell</td></tr></tbody></table><p><br></p>"
      );
      return;
    }
    if (tool.rich === "media") {
      openMedia();
      return;
    }
    if (typeof tool.rich === "function") tool.rich();
  }

  /* ---- Media ---- */
  async function upload(file) {
    const data = new FormData();
    data.append("file", file);
    const response = await api("/api/media", { method: "POST", body: data });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error((payload.error && payload.error.message) || "Upload failed");
    }
    return payload;
  }

  function insertMedia(url) {
    if (mode === "rich") {
      insertHtml(`<img src="${escapeHtml(url)}" alt="" loading="lazy"><p><br></p>`);
    } else {
      surround(`![](${url})`, "");
    }
  }

  function openMedia() {
    mediaPanel.hidden = false;
    mediaPanel.querySelector("input[type=url]").focus();
  }

  /* ---- Wiring ---- */
  for (const tool of TOOLS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "editor__tool";
    button.title = tool.title;
    button.setAttribute("aria-label", tool.title);
    button.textContent = tool.label;
    button.addEventListener("mousedown", (event) => event.preventDefault());
    button.addEventListener("click", () => apply(tool));
    bar.appendChild(button);
  }

  for (const tab of root.querySelectorAll(".editor__mode")) {
    tab.addEventListener("click", async () => {
      const wanted = tab.dataset.mode;
      if (wanted === mode) return;
      if (wanted === "rich") await toRich();
      else toMarkdown();
      for (const other of root.querySelectorAll(".editor__mode")) {
        other.classList.toggle("is-active", other.dataset.mode === mode);
      }
    });
  }

  const fileInput = mediaPanel.querySelector("input[type=file]");
  const drop = mediaPanel.querySelector(".editor__drop");
  const urlInput = mediaPanel.querySelector("input[type=url]");
  const mediaError = mediaPanel.querySelector(".editor__media-error");

  function report(message) {
    mediaError.textContent = message;
    mediaError.hidden = !message;
  }

  async function send(files) {
    report("");
    for (const file of files) {
      try {
        const result = await upload(file);
        insertMedia(result.url);
      } catch (error) {
        report(error.message);
        return;
      }
    }
    mediaPanel.hidden = true;
  }

  drop.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) send([...fileInput.files]);
  });
  for (const type of ["dragenter", "dragover"]) {
    drop.addEventListener(type, (event) => {
      event.preventDefault();
      drop.classList.add("is-over");
    });
  }
  for (const type of ["dragleave", "drop"]) {
    drop.addEventListener(type, (event) => {
      event.preventDefault();
      drop.classList.remove("is-over");
    });
  }
  drop.addEventListener("drop", (event) => {
    if (event.dataTransfer.files.length) send([...event.dataTransfer.files]);
  });

  mediaPanel.querySelector(".editor__insert-url").addEventListener("click", () => {
    const url = urlInput.value.trim();
    if (!url) {
      report("Paste an image address first.");
      return;
    }
    insertMedia(url);
    urlInput.value = "";
    mediaPanel.hidden = true;
  });
  mediaPanel.querySelector(".editor__media-close").addEventListener("click", () => {
    mediaPanel.hidden = true;
  });

  root.querySelectorAll(".editor__mode").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.mode === mode);
  });
  root.dataset.mode = mode;

  return {
    value: () => {
      if (mode === "rich") toMarkdown();
      return source.value.trim();
    },
    setValue: (text) => {
      source.value = text || "";
    },
  };
}

function wireAll() {
  const editors = {};
  for (const root of document.querySelectorAll(".editor")) {
    const key = root.dataset.editor;
    const instance = create(root);
    if (key && instance) editors[key] = instance;
  }
  window.MELE_EDITOR = editors;
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", wireAll);
} else {
  wireAll();
}
})();

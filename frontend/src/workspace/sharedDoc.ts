/* A shared document, so two views of the same thing cannot disagree.

   Somebody may deliberately open the same question twice, or a resource beside
   itself. Each view is a window onto one value; typing in one must arrive in the
   other, because the value is absolute and the viewport is not. */

import { useEffect, useRef, useState } from "react";

type Listener = (value: string) => void;

class Document {
  value: string;
  private listeners = new Set<Listener>();

  constructor(initial: string) {
    this.value = initial;
  }

  edit(next: string) {
    this.value = next;
    for (const listener of this.listeners) listener(next);
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }
}

const documents = new Map<string, Document>();

export function useSharedText(key: string, initial: string) {
  const doc = useRef<Document | null>(null);
  if (!doc.current) {
    let existing = documents.get(key);
    if (!existing) {
      existing = new Document(initial);
      documents.set(key, existing);
    }
    doc.current = existing;
  }

  const [value, setValue] = useState(doc.current.value);

  useEffect(() => {
    const current = doc.current;
    if (!current) return;
    // A view that mounts after somebody typed shows what is there now.
    setValue(current.value);
    return current.subscribe((next) => setValue(next));
  }, [key]);

  function edit(next: string) {
    doc.current?.edit(next);
  }

  return [value, edit] as const;
}

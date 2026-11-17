/* A specialist calculator keeps its own page. Putting it in a panel as a frame
   means one instance cannot reach into another's state, which is what makes a
   thousand of them merely slow rather than broken. */
export function ToolFrame({ slug, title }: { slug: string; title: string }) {
  return (
    <iframe
      className="tool-frame"
      src={`/tools/${slug}`}
      title={title}
      loading="lazy"
    />
  );
}

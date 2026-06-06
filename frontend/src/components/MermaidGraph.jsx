import { useEffect, useRef, useId } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "neutral",
  securityLevel: "loose",
  flowchart: { curve: "basis", padding: 16 },
});

export default function MermaidGraph({ chart, title }) {
  const ref = useRef(null);
  const uid = useId().replace(/:/g, "");

  useEffect(() => {
    if (!chart || !ref.current) return;
    let cancelled = false;
    (async () => {
      try {
        const { svg } = await mermaid.render(`mmd-${uid}`, chart);
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      } catch (e) {
        if (ref.current)
          ref.current.innerHTML = `<pre class="mermaid-error">${String(e)}</pre>`;
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chart, uid]);

  if (!chart) return <p className="muted">暂无规则图</p>;

  return (
    <div className="mermaid-panel mermaid-panel--full">
      {title ? <h4>{title}</h4> : null}
      <div ref={ref} className="mermaid-wrap" />
    </div>
  );
}

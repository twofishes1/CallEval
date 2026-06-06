import { Fragment, useMemo } from "react";

function colorByNodeId(id) {
  const s = String(id || "");
  if (s === "START") return { bd: "rgba(0,229,160,.55)", tx: "var(--jade)", bg: "rgba(0,229,160,.06)" };
  if (s === "END") return { bd: "rgba(0,229,160,.55)", tx: "var(--jade)", bg: "rgba(0,229,160,.06)" };
  if (s === "CLOSING") return { bd: "rgba(0,229,160,.55)", tx: "var(--jade)", bg: "rgba(0,229,160,.06)" };
  if (s === "OBJECTION" || s === "OBJECTION_FINAL") return { bd: "rgba(255,107,107,.55)", tx: "var(--coral)", bg: "rgba(255,107,107,.06)" };
  if (s === "FAQ_NORMAL" || s === "FAQ_OOB") return { bd: "rgba(56,209,248,.55)", tx: "var(--sky)", bg: "rgba(56,209,248,.06)" };
  if (s === "RETURN_TO_FLOW") return { bd: "rgba(178,140,255,.55)", tx: "var(--violet)", bg: "rgba(178,140,255,.06)" };
  if (s.startsWith("STEP_")) return { bd: "rgba(56,209,248,.55)", tx: "var(--sky)", bg: "rgba(8,24,40,.55)" };
  return { bd: "rgba(148,163,184,.35)", tx: "var(--silver)", bg: "rgba(148,163,184,.05)" };
}

export default function GoalFsmPath({ path }) {
  const nodes = useMemo(() => (Array.isArray(path?.nodes) ? path.nodes : []), [path]);
  const edges = useMemo(() => (Array.isArray(path?.edges) ? path.edges : []), [path]);
  const edgeByPair = useMemo(() => {
    const m = new Map();
    edges.forEach((e) => {
      if (!e?.from || !e?.to) return;
      m.set(`${e.from}__${e.to}`, e.label || "");
    });
    return m;
  }, [edges]);

  if (!nodes.length) return <div className="muted">无 FSM 路径数据</div>;

  return (
    <div style={{ overflowX: "auto", padding: "6px 0" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 0, minWidth: "max-content" }}>
        {nodes.map((n, idx) => {
          const st = colorByNodeId(n.id);
          const label = (n.label || "").toString().trim();
          return (
            <Fragment key={`${n.id}-${idx}`}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <div
                  style={{
                    padding: "8px 14px",
                    borderRadius: 8,
                    border: `1.5px solid ${st.bd}`,
                    color: st.tx,
                    background: st.bg,
                    fontSize: 11,
                    fontWeight: 700,
                    fontFamily: "var(--mono)",
                    minWidth: 96,
                    textAlign: "center",
                    lineHeight: 1.2,
                  }}
                >
                  {String(n.id).replace("_", "\n_")}
                </div>
                {label ? (
                  <div style={{ fontSize: 10, color: "var(--smoke)", marginTop: 6, maxWidth: 110, textAlign: "center", lineHeight: 1.3 }}>
                    {label.length > 36 ? label.slice(0, 36) + "…" : label}
                  </div>
                ) : null}
              </div>

              {idx < nodes.length - 1 ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "0 10px", marginTop: 18, position: "relative", minWidth: 56 }}>
                  <div style={{ height: 2, width: 44, background: "rgba(148,163,184,.45)" }} />
                  <div style={{ color: "rgba(148,163,184,.75)", marginTop: -10, fontSize: 10, whiteSpace: "nowrap" }}>
                    {edgeByPair.get(`${nodes[idx].id}__${nodes[idx + 1].id}`) || ""}
                  </div>
                  <div style={{ color: "rgba(148,163,184,.75)", marginTop: 4, fontSize: 14 }}>▶</div>
                </div>
              ) : null}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}


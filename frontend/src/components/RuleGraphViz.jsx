/** Single horizontal strip: constraints → flow chain (scroll on overflow). */

const EDGE_COLOR = {
  sequence: "#4f6ef7",
  requires: "#d69e2e",
  excludes: "#e53e3e",
  modifies: "#805ad5",
  applies_globally: "#553c9a",
  covers_step: "#2b6cb0",
  on_user_ask: "#0891b2",
};

export default function RuleGraphViz({ graphViz }) {
  if (!graphViz?.nodes?.length) {
    return <p className="muted">构建场景后显示节点关系</p>;
  }

  const nodes = graphViz.nodes;
  const edges = graphViz.edges || [];
  const flowNodes = [...nodes.filter((n) => n.type === "flow_step")].sort(
    (a, b) => (a.meta?.order ?? 0) - (b.meta?.order ?? 0)
  );
  const constraintNodes = nodes.filter((n) => n.type === "constraint");
  const scopeNodes = nodes.filter((n) => n.type === "dialogue_scope");
  const faqNodes = [...nodes.filter((n) => n.type === "faq_item")].sort(
    (a, b) => (a.meta?.index ?? 0) - (b.meta?.index ?? 0)
  );
  const varNodes = nodes.filter((n) => n.type === "variable");

  return (
    <div className="rule-graph-viz rule-graph-viz--horizontal">
      <div className="graph-stats-inline">
        {graphViz.stats &&
          Object.entries(graphViz.stats).map(([k, v]) => (
            <span key={k} className="stat-chip">
              {k}: {v}
            </span>
          ))}
      </div>

      {faqNodes.length > 0 && (
        <div className="hgraph-scroll faq-strip">
          <div className="hgraph-row">
            <span className="hgraph-label">FAQ</span>
            {faqNodes.map((n, i) => {
              const fullQ = (n.meta?.question ?? "").trim() || n.label || "";
              const fullA = (n.meta?.answer ?? "").trim();
              const tip = [fullQ, fullA].filter(Boolean).join("\n\n");
              return (
                <div key={n.id} className="hgraph-chip">
                  <div className="hgraph-node faq" title={tip}>
                    <strong>#{i + 1}</strong>
                    <div className="faq-body">
                      <div className="hgraph-snippet hgraph-snippet--faq-q">
                        {fullQ}
                      </div>
                      {fullA ? (
                        <div className="hgraph-snippet hgraph-snippet--faq-a">
                          {fullA}
                        </div>
                      ) : null}
                    </div>
                  </div>
                  {i < faqNodes.length - 1 && (
                    <span className="hgraph-sep">|</span>
                  )}
                </div>
              );
            })}
            {flowNodes.length > 0 && (
              <span className="hgraph-acts faq-act">插问时可答 → 整通对话域</span>
            )}
          </div>
        </div>
      )}

      <div className="hgraph-scroll">
        <div className="hgraph-row">
          <span className="hgraph-label">约束</span>
          {constraintNodes.map((n, i) => (
            <div key={n.id} className="hgraph-chip">
              <div
                className="hgraph-node constraint"
                title={n.meta?.text || n.label || ""}
              >
                <strong>{n.id}</strong>
                <span className="hgraph-snippet hgraph-snippet--constraint-text">
                  {n.meta?.text || n.label}
                </span>
              </div>
              {i < constraintNodes.length - 1 && (
                <span className="hgraph-sep">→</span>
              )}
            </div>
          ))}
          {scopeNodes.length > 0 && (
            <>
              <span className="hgraph-acts">经</span>
              {scopeNodes.map((n) => (
                <div key={n.id} className="hgraph-chip">
                  <div className="hgraph-node scope" title={n.meta?.scope || ""}>
                    <strong>域</strong>
                    <span className="hgraph-snippet">{n.label}</span>
                  </div>
                </div>
              ))}
            </>
          )}
          {constraintNodes.length > 0 && flowNodes.length > 0 && (
            <span className="hgraph-acts">覆盖</span>
          )}
          <span className="hgraph-label">流程</span>
          {flowNodes.map((n, i) => (
            <div key={n.id} className="hgraph-chip">
              <div className="hgraph-node flow">
                <span className="hgraph-stepno">{(n.meta?.order ?? i) + 1}</span>
                <span className="hgraph-snippet">{n.meta?.text || n.label}</span>
              </div>
              {i < flowNodes.length - 1 && <span className="hgraph-arrow">→</span>}
            </div>
          ))}
          {varNodes.map((n) => (
            <div key={n.id} className="hgraph-chip">
              <div className="hgraph-node var">${n.meta?.name || n.id}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="edge-pills-scroll">
        {edges.map((e, i) => (
          <span
            key={i}
            className="edge-pill"
            style={{ borderColor: EDGE_COLOR[e.edge_type] || "#94a3b8" }}
          >
            <em style={{ color: EDGE_COLOR[e.edge_type] || "#64748b" }}>
              {e.edge_type}
            </em>{" "}
            {e.source} → {e.target}
          </span>
        ))}
      </div>
    </div>
  );
}

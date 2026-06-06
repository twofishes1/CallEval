const PALETTE = {
  dark: {
    start: { bg: "rgba(0,229,160,.12)", bd: "#00e5a0", tx: "#6ee7b7" },
    end: { bg: "rgba(255,107,107,.10)", bd: "#ff6b6b", tx: "#fca5a5" },
    closing: { bg: "rgba(255,184,48,.10)", bd: "#fbbf24", tx: "#fcd34d" },
    objection: { bg: "rgba(255,107,107,.08)", bd: "#f87171", tx: "#fca5a5" },
    faq: { bg: "rgba(56,209,248,.10)", bd: "#38d9f8", tx: "#7dd3fc" },
    retain: { bg: "rgba(178,140,255,.10)", bd: "#a78bfa", tx: "#c4b5fd" },
    flow: { bg: "rgba(0,229,160,.06)", bd: "#10b981", tx: "#6ee7b7" },
    branch: { bg: "rgba(251,146,60,.12)", bd: "#ea580c", tx: "#fdba74" },
    other: { bg: "rgba(148,163,184,.06)", bd: "#94a3b8", tx: "#cbd5e1" },
  },
  studio: {
    start: { bg: "#ecfdf5", bd: "#10b981", tx: "#047857" },
    end: { bg: "#fef2f2", bd: "#ef4444", tx: "#b91c1c" },
    closing: { bg: "#fffbeb", bd: "#f59e0b", tx: "#b45309" },
    objection: { bg: "#fef2f2", bd: "#f87171", tx: "#b91c1c" },
    faq: { bg: "#eff6ff", bd: "#3b82f6", tx: "#1d4ed8" },
    retain: { bg: "#f5f3ff", bd: "#8b5cf6", tx: "#6d28d9" },
    flow: { bg: "#ecfdf5", bd: "#10b981", tx: "#047857" },
    branch: { bg: "#fff7ed", bd: "#ea580c", tx: "#c2410c" },
    other: { bg: "#f8fafc", bd: "#94a3b8", tx: "#475569" },
  },
};

function nodeColor(n, variant) {
  const p = PALETTE[variant] || PALETTE.dark;
  const t = (n?.type || "").toString();
  if (t === "start") return p.start;
  if (t === "end") return p.end;
  if (t === "closing") return p.closing;
  if (t === "objection" || t === "objection_final") return p.objection;
  if (t === "faq_normal" || t === "faq_oob") return p.faq;
  if (t === "scenario_probe") return p.branch;
  if (t === "return_to_flow") return p.retain;
  if (t === "choice_branch" || t === "op_step") return p.branch;
  if (t === "flow_step") return p.flow;
  return p.other;
}

function edgeColor(e, variant) {
  if (e?.virtual) return variant === "studio" ? "#a78bfa" : "rgba(178,140,255,.85)";
  const tt = (e?.trigger_type || "").toString();
  if (tt.includes("reject")) return variant === "studio" ? "#ef4444" : "rgba(255,107,107,.85)";
  if (tt.includes("faq") || tt.includes("oob")) return variant === "studio" ? "#3b82f6" : "rgba(56,209,248,.85)";
  if (tt === "branch" || tt === "goto" || tt === "guides") return variant === "studio" ? "#ea580c" : "rgba(251,146,60,.85)";
  return variant === "studio" ? "#475569" : "rgba(148,163,184,.85)";
}

function FsmNode({ node, variant }) {
  const c = nodeColor(node, variant);
  const isStudio = variant === "studio";
  const title = [
    node.label,
    node.detail,
    node.knowledge_id ? `知识点 ${node.knowledge_id}` : "",
    node.scenario_id ? `约束场景 ${node.scenario_id}` : "",
  ]
    .filter(Boolean)
    .join("\n");
  const accentBorder =
    node.scenario_id && isStudio
      ? "#ea580c"
      : node.knowledge_id
        ? isStudio
          ? "#2563eb"
          : "#38bdf8"
        : c.bd;
  return (
    <div className="path-fsm-node-wrap">
      <div
        className={`path-fsm-node${node.knowledge_id ? " path-fsm-node--k-target" : ""}${node.scenario_id ? " path-fsm-node--d-target" : ""}`}
        style={{
          background: c.bg,
          borderColor: accentBorder,
          color: c.tx,
          fontSize: isStudio ? 15 : 13,
        }}
        title={title}
      >
        <span className="path-fsm-node-label">{node.label}</span>
        {node.detail && node.detail !== node.label ? (
          <span className="path-fsm-node-detail">{node.detail}</span>
        ) : null}
      </div>
    </div>
  );
}

function FsmTransition({ edge, variant }) {
  const color = edgeColor(edge, variant);
  const isStudio = variant === "studio";
  const label = (edge?.label || "路径推进").trim();
  const dashed = edge?.virtual;

  return (
    <div className="path-fsm-trans" aria-label={`触发：${label}`}>
      <div className="path-fsm-trans-rail">
        <div
          className="path-fsm-trigger-chip"
          style={{
            borderColor: isStudio ? "#94a3b8" : "rgba(148,163,184,.5)",
            background: isStudio ? "#ffffff" : "rgba(15,23,42,.85)",
            color: isStudio ? "#1e293b" : "#e2e8f0",
          }}
          title={label}
        >
          <span className="path-fsm-trigger-prefix">触发</span>
          <span className="path-fsm-trigger-text">{label}</span>
        </div>
        <div className="path-fsm-arrow-rail">
          {dashed ? (
            <div
              className="path-fsm-arrow-line path-fsm-arrow-line--dashed"
              style={{ borderLeftColor: color }}
            />
          ) : (
            <div className="path-fsm-arrow-line" style={{ background: color }} />
          )}
          <div className="path-fsm-arrow-head" style={{ borderTopColor: color }} />
        </div>
      </div>
    </div>
  );
}

export default function PathFsmSpine({ nodes, edges, variant = "studio" }) {
  const edgeByPair = new Map(edges.map((e) => [`${e.from}->${e.to}`, e]));

  return (
    <div
      className={`path-fsm-spine ${variant === "studio" ? "path-fsm-spine--studio" : "path-fsm-spine--dark"}`}
      role="list"
      aria-label="路径状态机"
    >
      {nodes.map((node, i) => {
        const next = nodes[i + 1];
        const edge = next ? edgeByPair.get(`${node.id}->${next.id}`) || edges[i] : null;
        return (
          <div key={node.id} className="path-fsm-step" role="listitem">
            <FsmNode node={node} variant={variant} />
            {edge ? <FsmTransition edge={edge} variant={variant} /> : null}
          </div>
        );
      })}
    </div>
  );
}

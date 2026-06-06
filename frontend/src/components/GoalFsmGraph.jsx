import { useEffect, useMemo, useRef, useState } from "react";
import PathFsmSpine from "./PathFsmSpine.jsx";

function inferNodeType(id, rawType) {
  const t = (rawType || "").toString();
  if (t) return t;
  const u = String(id || "").toUpperCase();
  if (u === "START") return "start";
  if (u === "END") return "end";
  if (u === "CLOSING") return "closing";
  if (u === "OBJECTION") return "objection";
  if (u === "OBJECTION_FINAL") return "objection_final";
  if (u === "FAQ_NORMAL") return "faq_normal";
  if (u === "FAQ_OOB") return "faq_oob";
  if (u.startsWith("PROBE_")) return "scenario_probe";
  if (u === "RETURN_TO_FLOW") return "return_to_flow";
  if (u.startsWith("STEP_")) return "flow_step";
  return "other";
}

function normNodesEdges(meta) {
  const nodes = Array.isArray(meta?.nodes) ? meta.nodes : [];
  const edges = Array.isArray(meta?.edges) ? meta.edges : [];
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const safeNodes = nodes
    .filter((n) => n && n.id)
    .map((n) => ({
      id: String(n.id),
      label: (n.label ?? n.id ?? "").toString(),
      type: inferNodeType(n.id, n.type),
      step_index: n.step_index == null ? null : Number(n.step_index),
      knowledge_id: (n.knowledge_id ?? "").toString(),
      scenario_id: (n.scenario_id ?? "").toString(),
      detail: (n.detail ?? "").toString(),
    }));
  const safeEdges = edges
    .filter((e) => e && e.from && e.to)
    .map((e) => ({
      from: String(e.from),
      to: String(e.to),
      label: (e.label ?? "").toString(),
      trigger_type: (e.trigger_type ?? "").toString(),
      virtual: !!e.virtual,
    }))
    .filter((e) => nodeById.has(e.from) && nodeById.has(e.to));
  return { nodes: safeNodes, edges: safeEdges };
}

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
    canvas: "rgba(3,7,18,.35)",
    edgeLabelBg: "rgba(3,7,18,.75)",
    edgeLabelTx: "rgba(148,163,184,.75)",
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
    canvas: "#ffffff",
    edgeLabelBg: "#ffffff",
    edgeLabelTx: "#64748b",
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
  const p = PALETTE[variant] || PALETTE.dark;
  if (e?.virtual) return variant === "studio" ? "#a78bfa" : "rgba(178,140,255,.55)";
  const tt = (e?.trigger_type || "").toString();
  if (tt.includes("reject")) return variant === "studio" ? "#f87171" : "rgba(255,107,107,.65)";
  if (tt.includes("faq") || tt.includes("oob")) return variant === "studio" ? "#3b82f6" : "rgba(56,209,248,.65)";
  if (tt === "branch" || tt === "goto" || tt === "guides") return variant === "studio" ? "#ea580c" : "rgba(251,146,60,.75)";
  return variant === "studio" ? "#64748b" : "rgba(148,163,184,.55)";
}

function metaFingerprint(meta) {
  if (!meta) return "";
  const ns = (meta.nodes || []).map((n) => `${n.id}:${n.label || ""}`).join("|");
  const es = (meta.edges || []).map((e) => `${e.from}->${e.to}`).join("|");
  return `${ns}#${es}`;
}

function presetPathLayout(nodes) {
  const positions = {};
  const colX = 80;
  const rowStep = 104;
  const startY = 64;
  nodes.forEach((n, i) => {
    positions[n.id] = { x: colX, y: startY + i * rowStep };
  });
  return positions;
}

function pathEdgeStyle(isStudio) {
  const rail = isStudio ? 84 : 68;
  return {
    width: isStudio ? 3 : 2.5,
    "line-color": isStudio ? "#475569" : "rgba(148,163,184,.85)",
    "target-arrow-color": isStudio ? "#475569" : "rgba(148,163,184,.85)",
    "target-arrow-shape": "triangle",
    "arrow-scale": isStudio ? 1.5 : 1.25,
    "curve-style": "unbundled-bezier",
    "control-point-distances": [rail],
    "control-point-weights": [0.44],
    "source-endpoint": "outside-to-node",
    "target-endpoint": "outside-to-node",
    "source-distance-from-node": 2,
    "target-distance-from-node": 2,
    label: "data(label)",
    "font-size": isStudio ? 11 : 10,
    "font-weight": 600,
    color: isStudio ? "#1e293b" : "rgba(226,232,240,.95)",
    "text-background-color": isStudio ? "#ffffff" : "rgba(15,23,42,.92)",
    "text-background-opacity": 1,
    "text-background-padding": 5,
    "text-border-color": isStudio ? "#94a3b8" : "rgba(148,163,184,.45)",
    "text-border-width": 1,
    "text-border-opacity": 1,
    "text-rotation": "autorotate",
    "text-margin-x": 8,
    "text-margin-y": 0,
    "min-zoomed-font-size": isStudio ? 9 : 8,
  };
}

function GoalFsmPathView({ nodes, edges, height, variant, compact, fillMode }) {
  const isStudio = variant === "studio";
  const palette = PALETTE[variant] || PALETTE.dark;
  return (
    <div
      className={isStudio ? "goal-fsm-graph goal-fsm-graph--studio" : "goal-fsm-graph"}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: compact ? 6 : 10,
        height: fillMode ? "100%" : undefined,
        minHeight: fillMode ? 0 : undefined,
      }}
    >
      {!compact ? (
        <div className="muted" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontFamily: "var(--mono, monospace)", fontSize: 11 }}>
            节点 {nodes.length} · 转移 {edges.length}
          </span>
        </div>
      ) : null}
      {!compact ? (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 11 }}>
          <span style={{ color: isStudio ? "#047857" : "var(--jade)" }}>■ 流程</span>
          <span style={{ color: isStudio ? "#1d4ed8" : "var(--sky)" }}>■ FAQ</span>
          <span style={{ color: isStudio ? "#6d28d9" : "var(--violet)" }}>■ 挽留</span>
          <span style={{ color: isStudio ? "#b91c1c" : "var(--coral)" }}>■ 终止</span>
        </div>
      ) : null}
      <div
        className="path-fsm-scroll"
        style={{
          height: fillMode ? undefined : typeof height === "number" ? `${height}px` : height,
          flex: fillMode ? 1 : undefined,
          minHeight: fillMode ? 320 : undefined,
          background: palette.canvas,
        }}
      >
        <PathFsmSpine nodes={nodes} edges={edges} variant={variant} />
      </div>
    </div>
  );
}

function GoalFsmCyView({
  nodes,
  edges,
  fp,
  height,
  isPathProjection,
  variant,
  compact,
  fillMode,
}) {
  const hostRef = useRef(null);
  const cyRef = useRef(null);
  const [ready, setReady] = useState(false);
  const isStudio = variant === "studio";

  useEffect(() => {
    let disposed = false;
    let resizeTimer = null;

    async function boot() {
      if (!hostRef.current) return;
      if (!nodes.length) {
        setReady(false);
        return;
      }

      const mod = await import("cytoscape");
      const cytoscape = mod.default || mod;

      if (isPathProjection) {
        const dagreMod = await import("cytoscape-dagre/cytoscape-dagre.js");
        cytoscape.use(dagreMod.default || dagreMod);
      }

      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }

      const pathPositions = isPathProjection ? presetPathLayout(nodes) : null;
      const nodeFontSize = isPathProjection ? (isStudio ? 15 : 13) : isStudio ? 11 : 10;
      const nodeWidth = isPathProjection ? (isStudio ? 108 : 140) : isStudio ? 100 : "label";
      const nodeHeight = isPathProjection ? (isStudio ? 44 : 54) : isStudio ? 40 : "label";
      const palette = PALETTE[variant] || PALETTE.dark;

      const elements = [
        ...nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type, step_index: n.step_index } })),
        ...edges.map((e, i) => ({
          data: {
            id: `${e.from}__${e.to}__${i}`,
            source: e.from,
            target: e.to,
            label: e.label || "",
            trigger_type: e.trigger_type,
            virtual: e.virtual,
            pathEdge: isPathProjection ? 1 : 0,
          },
        })),
      ];

      const cy = cytoscape({
        container: hostRef.current,
        elements,
        pixelRatio: 1,
        motionBlur: false,
        textureOnViewport: true,
        hideEdgesOnViewport: false,
        style: [
          {
            selector: "node",
            style: {
              "background-color": (ele) => nodeColor(ele.data(), variant).bg,
              "border-color": (ele) => nodeColor(ele.data(), variant).bd,
              "border-width": 2,
              color: (ele) => nodeColor(ele.data(), variant).tx,
              label: "data(label)",
              "font-family": "JetBrains Mono, ui-monospace, monospace",
              "font-size": nodeFontSize,
              "font-weight": isStudio ? 600 : 400,
              "text-wrap": "wrap",
              "text-max-width": isPathProjection ? (isStudio ? 100 : 180) : 120,
              "text-valign": "center",
              "text-halign": "center",
              padding: isStudio ? 12 : 8,
              shape: "round-rectangle",
              width: nodeWidth,
              height: nodeHeight,
              "min-zoomed-font-size": isStudio ? 10 : 0,
            },
          },
          {
            selector: "edge",
            style: {
              width: isStudio ? 2.5 : 1.5,
              "line-color": (ele) => edgeColor(ele.data(), variant),
              "target-arrow-color": (ele) => edgeColor(ele.data(), variant),
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              label: "data(label)",
              "font-size": isStudio ? 10 : 8,
              "font-weight": isStudio ? 500 : 400,
              "min-zoomed-font-size": isStudio ? 8 : 0,
              color: palette.edgeLabelTx,
              "text-background-color": palette.edgeLabelBg,
              "text-background-opacity": 1,
              "text-background-padding": 3,
              "text-rotation": "autorotate",
              "arrow-scale": isStudio ? 1.15 : 0.9,
            },
          },
          ...(isPathProjection
            ? [
                {
                  selector: "edge[pathEdge = 1]",
                  style: {
                    ...pathEdgeStyle(isStudio),
                    "line-color": (ele) => edgeColor(ele.data(), variant),
                    "target-arrow-color": (ele) => edgeColor(ele.data(), variant),
                  },
                },
              ]
            : []),
          {
            selector: "edge[virtual = 1]",
            style: {
              "line-style": "dashed",
              width: 1.5,
            },
          },
        ],
        layout: isPathProjection
          ? pathPositions
            ? {
                name: "preset",
                positions: (node) => pathPositions[node.id()] || { x: 0, y: 0 },
                fit: true,
                padding: isStudio ? 56 : 28,
                animate: false,
              }
            : {
                name: "dagre",
                rankDir: "TB",
                nodeSep: 72,
                rankSep: 100,
                animate: false,
              }
          : {
              name: "dagre",
              rankDir: "LR",
              nodeSep: isStudio ? 80 : 68,
              edgeSep: 20,
              rankSep: isStudio ? 140 : 120,
              animate: false,
            },
        minZoom: 0.35,
        maxZoom: 2.5,
        wheelSensitivity: 0.25,
        boxSelectionEnabled: false,
      });

      cyRef.current = cy;
      if (!disposed) setReady(true);
      cy.fit(undefined, isStudio ? (isPathProjection ? 52 : 40) : 24);

      const ro = new ResizeObserver(() => {
        if (!cyRef.current || disposed) return;
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
          if (!cyRef.current || disposed) return;
          cyRef.current.resize();
        }, 180);
      });
      ro.observe(hostRef.current);
      cyRef.current.__ro = ro;
    }

    boot();

    return () => {
      disposed = true;
      clearTimeout(resizeTimer);
      if (cyRef.current) {
        if (cyRef.current.__ro) {
          try {
            cyRef.current.__ro.disconnect();
          } catch {
            /* ignore */
          }
        }
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [fp, isPathProjection, variant, isStudio, nodes.length]);

  const canvasStyle = {
    height: fillMode ? undefined : typeof height === "number" ? `${height}px` : height,
    flex: fillMode ? 1 : undefined,
    minHeight: fillMode ? 320 : undefined,
    width: "100%",
    borderRadius: 12,
    border: isStudio ? "1px solid #e2e8f0" : "1px solid var(--mist, #334155)",
    background: (PALETTE[variant] || PALETTE.dark).canvas,
    overflow: "hidden",
  };

  return (
    <div
      className={isStudio ? "goal-fsm-graph goal-fsm-graph--studio" : "goal-fsm-graph"}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: compact ? 6 : 10,
        height: fillMode ? "100%" : undefined,
        minHeight: fillMode ? 0 : undefined,
      }}
    >
      {!compact ? (
        <div className="muted" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontFamily: "var(--mono, monospace)", fontSize: 11 }}>
            节点 {nodes.length} · 边 {edges.length}
          </span>
        </div>
      ) : null}
      {isPathProjection && !compact ? (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 11 }}>
          <span style={{ color: isStudio ? "#047857" : "var(--jade)" }}>■ 流程</span>
          <span style={{ color: isStudio ? "#1d4ed8" : "var(--sky)" }}>■ FAQ</span>
          <span style={{ color: isStudio ? "#6d28d9" : "var(--violet)" }}>■ 挽留</span>
          <span style={{ color: isStudio ? "#b91c1c" : "var(--coral)" }}>■ 终止</span>
        </div>
      ) : null}
      <div ref={hostRef} style={canvasStyle} />
      {!ready ? (
        <div className="muted" style={{ fontSize: 12 }}>
          状态机加载中…
        </div>
      ) : null}
    </div>
  );
}

export default function GoalFsmGraph({
  meta,
  height = 420,
  isPathProjection = false,
  variant = "dark",
  compact = false,
}) {
  const fillMode = String(height) === "100%";
  const { nodes, edges } = useMemo(() => normNodesEdges(meta), [meta]);
  const fp = useMemo(() => metaFingerprint(meta), [meta]);

  if (isPathProjection && nodes.length) {
    return (
      <GoalFsmPathView
        nodes={nodes}
        edges={edges}
        height={height}
        variant={variant}
        compact={compact}
        fillMode={fillMode}
      />
    );
  }

  return (
    <GoalFsmCyView
      nodes={nodes}
      edges={edges}
      fp={fp}
      height={height}
      isPathProjection={isPathProjection}
      variant={variant}
      compact={compact}
      fillMode={fillMode}
    />
  );
}

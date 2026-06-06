import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import GoalFsmGraph from "../GoalFsmGraph.jsx";
import { fitViewBox, layoutKgNodes } from "./kgLayout.js";

const TONE = {
  flow: { fill: "#ecfdf5", stroke: "#10b981", text: "#047857" },
  branch: { fill: "#fff7ed", stroke: "#ea580c", text: "#c2410c" },
  know: { fill: "#eff6ff", stroke: "#3b82f6", text: "#1d4ed8" },
  boun: { fill: "#fef2f2", stroke: "#ef4444", text: "#b91c1c" },
  role: { fill: "#f5f3ff", stroke: "#8b5cf6", text: "#6d28d9" },
  dial: { fill: "#fffbeb", stroke: "#f59e0b", text: "#b45309" },
};

function tone(type) {
  return TONE[type] || TONE.dial;
}

/** Canvas label: short id only; full text lives in the side panel. */
function nodeDisplayLabel(n) {
  const id = String(n.id || "");
  const branch = id.match(/^branch::(\d+)::(?:.+::)?(\d+)$/);
  if (branch) return `BR${branch[1]}-${branch[2]}`;
  const op = id.match(/^op::(\d+)::(?:.+::)?(\d+)::(\d+)$/);
  if (op) return `OP${op[1]}-${op[3]}`;
  const opLegacy = id.match(/^op::(\d+)::(\d+)$/);
  if (opLegacy) return `OP${opLegacy[1]}-${opLegacy[2]}`;
  if (id === "GLOBAL_DIALOGUE") return "G-DIAL";
  if (id === "GLOBAL_BOUNDARY") return "G-BND";
  if (id.length <= 14) return id;
  return `${id.slice(0, 12)}…`;
}

const ATTACH_EDGE_TYPES = new Set([
  "on_user_ask",
  "applies_globally",
  "global_guard",
  "covers_step",
]);

function edgeStyle(edgeType, active, dimmed, toId = "") {
  if (edgeType === "branch") {
    const isChoice =
      String(toId).startsWith("branch::") || String(toId).startsWith("op::");
    if (!isChoice) {
      return {
        stroke: "#fdba74",
        width: active ? 1.6 : 0.9,
        dash: "4 4",
        opacity: active ? 0.45 : dimmed ? 0.04 : 0.12,
      };
    }
  }
  if (ATTACH_EDGE_TYPES.has(edgeType)) {
    return {
      stroke: "#cbd5e1",
      width: active ? 1.4 : 0.75,
      dash: "2 5",
      opacity: active ? 0.55 : dimmed ? 0.05 : 0.1,
    };
  }
  const base = {
    branch: { stroke: "#ea580c", width: active ? 2.2 : 1.3, dash: "6 4", opacity: dimmed ? 0.3 : 0.75 },
    goto: { stroke: "#059669", width: active ? 2.4 : 1.4, dash: "", opacity: dimmed ? 0.35 : 0.85 },
    guides: { stroke: "#fb923c", width: active ? 1.8 : 1.1, dash: "3 3", opacity: dimmed ? 0.2 : 0.45 },
    retention_jump: { stroke: "#a855f7", width: active ? 1.6 : 1, dash: "4 3", opacity: dimmed ? 0.15 : 0.35 },
    sequence: { stroke: active ? "#0d9488" : "#64748b", width: active ? 2.4 : 1.2, dash: "", opacity: dimmed ? 0.15 : active ? 1 : 0.55 },
  };
  return base[edgeType] || base.sequence;
}

function viewBoxEqual(a, b) {
  if (!a || !b) return false;
  return (
    Math.abs(a.x - b.x) < 0.5 &&
    Math.abs(a.y - b.y) < 0.5 &&
    Math.abs(a.w - b.w) < 0.5 &&
    Math.abs(a.h - b.h) < 0.5
  );
}

const PROBE_TO_CONSTRAINT = {
  PROBE_D9_BUSY: "D9",
  PROBE_D10_DRIVE: "D10",
};

function formatPathSeq(path) {
  if (path?.path_sequence_display) return path.path_sequence_display;
  const nodes = path?.nodes || [];
  const kid = path?.target_knowledge_id || "";
  const did = path?.target_scenario_id || "";
  return nodes
    .map((n) => {
      if (n === "FAQ_NORMAL" && kid) return `FAQ_NORMAL→${kid}`;
      if (Object.prototype.hasOwnProperty.call(PROBE_TO_CONSTRAINT, n)) {
        return `${n}→${did || PROBE_TO_CONSTRAINT[n]}`;
      }
      return n;
    })
    .join(" → ");
}

const EMPTY_NODES = [];
const EMPTY_EDGES = [];
const EMPTY_PATHS = [];

function kgNodesKey(nodes) {
  if (!Array.isArray(nodes) || !nodes.length) return "";
  return nodes.map((n) => `${n.id ?? ""}:${n.type ?? ""}:${n.node_type ?? ""}`).join("\0");
}

export default function Layer1View({ data, loading }) {
  const nodesKey = useMemo(() => kgNodesKey(data?.kg_viz?.nodes), [data?.kg_viz?.nodes]);
  const rawNodes = useMemo(() => {
    const n = data?.kg_viz?.nodes;
    return Array.isArray(n) ? n : EMPTY_NODES;
  }, [nodesKey, data?.kg_viz?.nodes]);
  const edges = useMemo(() => {
    const e = data?.kg_viz?.edges;
    return Array.isArray(e) ? e : EMPTY_EDGES;
  }, [data?.kg_viz?.edges]);
  const paths = useMemo(() => {
    const p = data?.paths;
    return Array.isArray(p) ? p : EMPTY_PATHS;
  }, [data?.paths]);
  const pathIdsKey = useMemo(
    () => paths.map((p) => p.path_id).join(","),
    [paths],
  );
  const parsed = data?.parsed || {};
  const nodeLabelCatalog = data?.node_label_catalog || {};

  const layoutNodes = useMemo(() => layoutKgNodes(rawNodes), [nodesKey, rawNodes]);
  const nodeById = useMemo(
    () => new Map(layoutNodes.map((n) => [n.id, n])),
    [layoutNodes]
  );

  const [selectedPathId, setSelectedPathId] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [viewMode, setViewMode] = useState("kg");
  const [rightTab, setRightTab] = useState("node");
  const svgRef = useRef(null);
  const draggingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, y: 0, viewX: 0, viewY: 0 });
  const [isDragging, setIsDragging] = useState(false);

  const measureAspect = useCallback(() => {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    return rect.width / rect.height;
  }, []);

  const layoutNodesRef = useRef(layoutNodes);
  layoutNodesRef.current = layoutNodes;

  const fitToCanvas = useCallback(() => {
    const nodes = layoutNodesRef.current;
    if (!nodes?.length) return;
    const ar = measureAspect();
    const next = fitViewBox(
      nodes,
      ar
        ? { aspectRatio: ar, preferCompact: true, paddingRatio: 0.03 }
        : { preferCompact: true, paddingRatio: 0.03 },
    );
    setViewBox((prev) => (viewBoxEqual(prev, next) ? prev : next));
  }, [measureAspect]);

  const [viewBox, setViewBox] = useState(() => fitViewBox(layoutNodes));

  useEffect(() => {
    if (!nodesKey || !layoutNodes.length) return;
    const ar = measureAspect();
    const next = fitViewBox(
      layoutNodes,
      ar
        ? { aspectRatio: ar, preferCompact: true, paddingRatio: 0.03 }
        : { preferCompact: true, paddingRatio: 0.03 },
    );
    setViewBox((prev) => (viewBoxEqual(prev, next) ? prev : next));
  }, [nodesKey, layoutNodes, measureAspect]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || typeof ResizeObserver === "undefined") return undefined;
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => fitToCanvas());
    });
    ro.observe(svg);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [fitToCanvas]);

  useEffect(() => {
    if (!pathIdsKey) {
      setSelectedPathId(null);
      return;
    }
    if (selectedPathId && paths.some((p) => p.path_id === selectedPathId)) return;
    setSelectedPathId(paths[0].path_id);
  }, [pathIdsKey, paths, selectedPathId]);

  const selectedPath = useMemo(
    () => paths.find((p) => p.path_id === selectedPathId) || null,
    [paths, selectedPathId]
  );

  const goalFsmMeta = useMemo(() => data?.goal_fsm || null, [data?.goal_fsm]);

  const fsmMeta = useMemo(() => {
    if (selectedPath?.fsm_projection?.nodes?.length) {
      return selectedPath.fsm_projection;
    }
    return goalFsmMeta;
  }, [selectedPath, goalFsmMeta]);

  const pathKnowledgeId = selectedPath?.target_knowledge_id || "";
  const pathScenarioId = selectedPath?.target_scenario_id || "";

  const pathNodeSet = useMemo(
    () => new Set(Array.isArray(selectedPath?.nodes) ? selectedPath.nodes : []),
    [selectedPath]
  );

  const pathEdgeSet = useMemo(() => {
    const set = new Set();
    const ns = Array.isArray(selectedPath?.nodes) ? selectedPath.nodes : [];
    for (let i = 0; i + 1 < ns.length; i += 1) set.add(`${ns[i]}->${ns[i + 1]}`);
    return set;
  }, [selectedPath]);

  const selectedNode = selectedNodeId ? nodeById.get(selectedNodeId) : null;

  const selectedNodeExplain = useMemo(() => {
    if (!selectedNodeId) return "";
    const fromPath = selectedPath?.node_labels?.[selectedNodeId];
    if (fromPath) return fromPath;
    if (nodeLabelCatalog[selectedNodeId]) return nodeLabelCatalog[selectedNodeId];
    if (/^F\d+$/.test(selectedNodeId)) {
      const m = selectedNodeId.match(/^F(\d+)$/);
      const stepIdx = m ? Number(m[1]) - 1 : -1;
      const stepText = stepIdx >= 0 ? parsed?.flow_steps?.[stepIdx] : "";
      return stepText || selectedNode?.text || selectedNode?.label || "流程步骤节点。";
    }
    if (/^branch::/.test(selectedNodeId) || selectedNode?.node_type === "flow_branch") {
      return selectedNode?.text || nodeLabelCatalog[selectedNodeId] || "条件分支：根据用户情况选择不同话术/跳转。";
    }
    if (/^op::/.test(selectedNodeId) || selectedNode?.node_type === "op_step") {
      return selectedNode?.text || "操作引导步骤。";
    }
    if (/^K\d+$/.test(selectedNodeId)) {
      const k = (parsed?.knowledge_nodes || []).find((x) => x?.id === selectedNodeId);
      return k?.text || selectedNode?.text || "知识节点。";
    }
    const c = (parsed?.constraints || []).find((x) => x?.id === selectedNodeId);
    return c?.text || selectedNode?.text || "节点说明暂无。";
  }, [selectedNodeId, selectedPath, nodeLabelCatalog, parsed, selectedNode]);

  const onWheel = (e) => {
    e.preventDefault();
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const mx = (e.clientX - rect.left) / rect.width;
    const my = (e.clientY - rect.top) / rect.height;
    const factor = e.deltaY > 0 ? 1.12 : 0.88;
    setViewBox((vb) => {
      const nextW = Math.max(180, Math.min(4000, vb.w * factor));
      const nextH = Math.max(140, Math.min(3000, vb.h * factor));
      const anchorX = vb.x + vb.w * mx;
      const anchorY = vb.y + vb.h * my;
      return {
        x: anchorX - nextW * mx,
        y: anchorY - nextH * my,
        w: nextW,
        h: nextH,
      };
    });
  };

  const onMouseDown = (e) => {
    draggingRef.current = true;
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX, y: e.clientY, viewX: viewBox.x, viewY: viewBox.y };
  };

  const onMouseMove = (e) => {
    if (!draggingRef.current) return;
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const dx = ((e.clientX - dragStartRef.current.x) / rect.width) * viewBox.w;
    const dy = ((e.clientY - dragStartRef.current.y) / rect.height) * viewBox.h;
    setViewBox((vb) => ({
      ...vb,
      x: dragStartRef.current.viewX - dx,
      y: dragStartRef.current.viewY - dy,
    }));
  };

  const onMouseUp = () => {
    draggingRef.current = false;
    setIsDragging(false);
  };

  if (loading) {
    return <div className="studio-loading">Layer1 分析加载中…</div>;
  }

  if (!data) {
    return <div className="studio-empty">暂无 Layer1 数据</div>;
  }

  return (
    <div className="layer-view layer1-view">
      <div className="layer-view-toolbar">
        <div className="layer1-stats-inline">
          <span>
            节点 <strong>{data?.summary?.node_count ?? layoutNodes.length}</strong>
          </span>
          <span>
            边 <strong>{data?.summary?.edge_count ?? edges.length}</strong>
          </span>
          <span>
            路径 <strong>{data?.summary?.path_count ?? paths.length}</strong>
          </span>
          <span>
            冲突 <strong>{data?.summary?.conflict_count ?? (data?.conflicts?.length || 0)}</strong>
          </span>
        </div>
        <div className="layer1-view-toggle">
          <button
            type="button"
            className={viewMode === "kg" ? "active" : ""}
            onClick={() => setViewMode("kg")}
          >
            图谱
          </button>
          <button
            type="button"
            className={viewMode === "fsm" ? "active" : ""}
            onClick={() => setViewMode("fsm")}
          >
            状态机
          </button>
          <button type="button" onClick={fitToCanvas}>
            适应画布
          </button>
        </div>
      </div>

      <div className="layer1-fill">
        <div className="layer1-graph-wrap">
          <div className="layer1-card-head compact">
            规则知识图谱
            {selectedPath?.path_id ? (
              <span className="path-badge">
                {selectedPath.path_id}
                {selectedPath.category_label ? ` · ${selectedPath.category_label}` : ""}
              </span>
            ) : null}
          </div>
          {viewMode === "kg" ? (
            <svg
              ref={svgRef}
              className={`kg-canvas-fill ${isDragging ? "grabbing" : ""}`}
              viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
              preserveAspectRatio="xMidYMid meet"
              onWheel={onWheel}
              onMouseDown={onMouseDown}
              onMouseMove={onMouseMove}
              onMouseUp={onMouseUp}
              onMouseLeave={onMouseUp}
            >
              <defs>
                <marker
                  id="kg-arrow-goto"
                  markerWidth="8"
                  markerHeight="8"
                  refX="7"
                  refY="4"
                  orient="auto"
                >
                  <path d="M0,0 L8,4 L0,8 z" fill="#059669" />
                </marker>
              </defs>
              <g>
                {edges.map((e, i) => {
                  const a = nodeById.get(e.from);
                  const b = nodeById.get(e.to);
                  if (!a || !b) return null;
                  const active = pathEdgeSet.has(`${e.from}->${e.to}`);
                  const dimmed = Boolean(selectedPath);
                  const est = edgeStyle(e.type, active, dimmed && !active, e.to);
                  const isGoto = e.type === "goto";
                  return (
                    <line
                      key={`e-${i}`}
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      stroke={est.stroke}
                      strokeOpacity={est.opacity}
                      strokeWidth={est.width}
                      strokeDasharray={est.dash || undefined}
                      markerEnd={isGoto ? "url(#kg-arrow-goto)" : undefined}
                    />
                  );
                })}
                {layoutNodes.map((n) => {
                  const s = tone(n.type);
                  const active = pathNodeSet.has(n.id);
                  const kTarget = pathKnowledgeId && n.id === pathKnowledgeId;
                  const dTarget = pathScenarioId && n.id === pathScenarioId;
                  const label = nodeDisplayLabel(n);
                  const w = Math.min(108, Math.max(64, label.length * 7.5 + 16));
                  const h = 40;
                  return (
                    <g
                      key={n.id}
                      onClick={() => {
                        setSelectedNodeId(n.id);
                        setRightTab("node");
                      }}
                      style={{ cursor: "pointer" }}
                    >
                      <rect
                        x={n.x - w / 2}
                        y={n.y - h / 2}
                        width={w}
                        height={h}
                        rx={8}
                        fill={s.fill}
                        stroke={dTarget ? "#ea580c" : kTarget ? "#2563eb" : active ? "#0d9488" : s.stroke}
                        strokeWidth={dTarget || kTarget ? 2.6 : active ? 2.2 : 1.3}
                        opacity={selectedPath ? (active || kTarget || dTarget ? 1 : 0.5) : 1}
                      />
                      <text
                        x={n.x}
                        y={n.y + 1}
                        textAnchor="middle"
                        dominantBaseline="middle"
                        fontSize="11"
                        fill={active ? "#047857" : s.text}
                        style={{ fontFamily: "JetBrains Mono, ui-monospace, monospace" }}
                      >
                        {label}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          ) : (
            <div className="kg-canvas-fill fsm-scroll layer1-fsm-panel">
              <div className="layer1-fsm-head">
                {selectedPath ? (
                  <span>
                    当前路径 <strong>{selectedPath.path_id}</strong>
                    {selectedPath.category_label ? ` · ${selectedPath.category_label}` : ""}
                    {selectedPath.knowledge_target_label ? (
                      <span className="path-k-target"> · {selectedPath.knowledge_target_label}</span>
                    ) : null}
                    {selectedPath.scenario_target_label ? (
                      <span className="path-d-target"> · {selectedPath.scenario_target_label}</span>
                    ) : null}
                  </span>
                ) : (
                  <span className="muted">在右侧「路径」列表选择一条路径，或查看全局状态机</span>
                )}
              </div>
              {fsmMeta?.nodes?.length ? (
                <GoalFsmGraph
                  meta={fsmMeta}
                  height="100%"
                  variant="studio"
                  compact
                  isPathProjection={Boolean(selectedPath?.fsm_projection?.nodes?.length)}
                />
              ) : (
                <p className="muted layer1-fsm-empty">暂无 FSM 数据，请刷新 Layer1 分析</p>
              )}
              {selectedPath?.flow_description || selectedPath?.rules_description ? (
                <details className="layer1-fsm-desc">
                  <summary>路径文字说明</summary>
                  {selectedPath.rules_description ? (
                    <pre className="fsm-pre">{selectedPath.rules_description}</pre>
                  ) : null}
                  {selectedPath.flow_description ? (
                    <pre className="fsm-pre">{selectedPath.flow_description}</pre>
                  ) : null}
                </details>
              ) : null}
            </div>
          )}
        </div>

        <aside className="layer1-side">
          <div className="layer1-side-tabs">
            <button
              type="button"
              className={rightTab === "node" ? "active" : ""}
              onClick={() => setRightTab("node")}
            >
              节点
            </button>
            <button
              type="button"
              className={rightTab === "paths" ? "active" : ""}
              onClick={() => setRightTab("paths")}
            >
              路径 ({paths.length})
            </button>
          </div>
          <div className={`layer1-side-body ${rightTab === "paths" ? "layer1-side-body--paths" : ""}`}>
            {rightTab === "node" ? (
              selectedNode ? (
                <>
                  <div className="node-id">{selectedNode.id}</div>
                  <p className="node-desc">{selectedNodeExplain}</p>
                </>
              ) : (
                <p className="muted">点击图谱中的节点</p>
              )
            ) : (
              <div className="path-panel">
                <div className="path-list-compact" role="listbox" aria-label="路径列表">
                  {paths.map((p) => {
                    const active = selectedPathId === p.path_id;
                    return (
                      <button
                        key={p.path_id}
                        type="button"
                        role="option"
                        aria-selected={active}
                        className={`path-row ${active ? "active" : ""}`}
                        onClick={() => setSelectedPathId(p.path_id)}
                      >
                        <span className="path-row-id">
                          {p.path_id}
                          {p.category_label ? ` · ${p.category_label}` : ""}
                        </span>
                        <span className="path-row-seq">{formatPathSeq(p)}</span>
                        {(p.activated_rules || []).length ? (
                          <span className="path-row-rules" title={(p.activated_rules || []).join(", ")}>
                            规则 {(p.activated_rules || []).length} 条 · {(p.activated_rules || []).join(", ")}
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
                <div className="path-detail-pane" aria-live="polite">
                  <div className="path-detail-label">路径详情</div>
                  {selectedPath ? (
                    <>
                      <div className="path-detail-head">
                        {selectedPath.path_id}
                        {selectedPath.category_label ? ` · ${selectedPath.category_label}` : ""}
                      </div>
                      {selectedPath.knowledge_target_label ? (
                        <div className="path-detail-k-target">{selectedPath.knowledge_target_label}</div>
                      ) : null}
                      {selectedPath.scenario_target_label ? (
                        <div className="path-detail-d-target">{selectedPath.scenario_target_label}</div>
                      ) : null}
                      <div className="path-detail-seq">{formatPathSeq(selectedPath)}</div>
                      {selectedPath.rules_description ? (
                        <>
                          <div className="path-detail-subhead">激活规则</div>
                          <pre className="path-detail-rules">{selectedPath.rules_description}</pre>
                        </>
                      ) : null}
                      {selectedPath.flow_description ? (
                        <>
                          <div className="path-detail-subhead">路径步骤</div>
                          <pre className="path-detail-body">{selectedPath.flow_description}</pre>
                        </>
                      ) : (
                        <p className="muted path-detail-empty">该路径暂无逐步说明。</p>
                      )}
                      {selectedPath.branch_notes ? (
                        <>
                          <div className="path-detail-subhead">动态分支（本路径未单独枚举）</div>
                          <pre className="path-detail-body path-detail-branches">{selectedPath.branch_notes}</pre>
                        </>
                      ) : null}
                    </>
                  ) : (
                    <p className="muted path-detail-empty">在上方选择一条路径，此处显示完整步骤说明。</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

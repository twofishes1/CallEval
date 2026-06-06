import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fitViewBox, layoutKgNodes } from "./studio/kgLayout.js";

function toneByType(t) {
  if (t === "flow") return { fill: "#0a1e16", stroke: "#145c3e", text: "#00e5a0" };
  if (t === "know") return { fill: "#081828", stroke: "#0a5a82", text: "#38d1f8" };
  if (t === "boun") return { fill: "#1e0b0b", stroke: "#852020", text: "#ff6b6b" };
  if (t === "role") return { fill: "#1a1440", stroke: "#5b3fa0", text: "#b28cff" };
  return { fill: "#1a1408", stroke: "#7a4e0a", text: "#ffb830" };
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

const EMPTY_NODES = [];
const EMPTY_EDGES = [];
const EMPTY_PATHS = [];

function kgNodesKey(nodes) {
  if (!Array.isArray(nodes) || !nodes.length) return "";
  return nodes.map((n) => `${n.id ?? ""}:${n.type ?? ""}:${n.node_type ?? ""}`).join("\0");
}

export default function Eval1AnalysisPanel({ data, loading, onRefresh }) {
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
  const layoutNodes = useMemo(() => layoutKgNodes(rawNodes), [nodesKey, rawNodes]);
  const nodeById = useMemo(() => new Map(layoutNodes.map((n) => [n.id, n])), [layoutNodes]);
  const [selectedPathId, setSelectedPathId] = useState(null);
  const [viewMode, setViewMode] = useState("kg"); // kg | fsm
  const [selectedNodeId, setSelectedNodeId] = useState(null);
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
    const next = fitViewBox(nodes, ar ? { aspectRatio: ar } : {});
    setViewBox((prev) => (viewBoxEqual(prev, next) ? prev : next));
  }, [measureAspect]);

  const [viewBox, setViewBox] = useState(() => fitViewBox(layoutNodes));

  useEffect(() => {
    if (!nodesKey || !layoutNodes.length) return;
    const ar = measureAspect();
    const next = fitViewBox(layoutNodes, ar ? { aspectRatio: ar } : {});
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
  useEffect(() => {
    if (!layoutNodes.length) {
      setSelectedNodeId(null);
      return;
    }
    if (selectedNodeId && nodeById.has(selectedNodeId)) return;
    const prefer = Array.isArray(paths?.[0]?.nodes) ? paths[0].nodes[0] : null;
    setSelectedNodeId(prefer && nodeById.has(prefer) ? prefer : layoutNodes[0].id);
  }, [layoutNodes, nodeById, selectedNodeId, paths]);

  const selectedPath = useMemo(
    () => paths.find((p) => p.path_id === selectedPathId) || null,
    [paths, selectedPathId]
  );
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
  const selectedNode = useMemo(
    () => (selectedNodeId ? nodeById.get(selectedNodeId) || null : null),
    [selectedNodeId, nodeById]
  );
  const selectedNodeIn = useMemo(
    () => (selectedNodeId ? edges.filter((e) => e.to === selectedNodeId) : []),
    [selectedNodeId, edges]
  );
  const selectedNodeOut = useMemo(
    () => (selectedNodeId ? edges.filter((e) => e.from === selectedNodeId) : []),
    [selectedNodeId, edges]
  );
  const nodeLabelCatalog = data?.node_label_catalog || {};
  const selectedNodeExplain = useMemo(() => {
    if (!selectedNodeId) return "";
    const fromPath = selectedPath?.node_labels?.[selectedNodeId];
    if (fromPath) return fromPath;
    if (nodeLabelCatalog[selectedNodeId]) return nodeLabelCatalog[selectedNodeId];
    if (/^F\d+$/.test(selectedNodeId)) {
      const c = (parsed?.constraints || []).find((x) => x?.id === selectedNodeId);
      return c?.text || (selectedNode?.text || "流程步骤节点。");
    }
    if (/^K\d+$/.test(selectedNodeId)) {
      const k = (parsed?.knowledge_nodes || []).find((x) => x?.id === selectedNodeId);
      return k?.text || (selectedNode?.text || "知识问答节点。");
    }
    if (/^[DB]\d+$/.test(selectedNodeId)) {
      const c = (parsed?.constraints || []).find((x) => x?.id === selectedNodeId);
      return c?.text || (selectedNode?.text || "全局约束节点。");
    }
    return selectedNode?.text || "节点说明暂无。";
  }, [selectedNodeId, selectedPath, nodeLabelCatalog, parsed, selectedNode]);

  const onWheel = (e) => {
    e.preventDefault();
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const mx = (e.clientX - rect.left) / rect.width;
    const my = (e.clientY - rect.top) / rect.height;
    const factor = e.deltaY > 0 ? 1.1 : 0.9;
    setViewBox((vb) => {
      const nextW = Math.max(220, Math.min(6000, vb.w * factor));
      const nextH = Math.max(180, Math.min(4000, vb.h * factor));
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
    const svg = svgRef.current;
    if (!svg) return;
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
    const dxPx = e.clientX - dragStartRef.current.x;
    const dyPx = e.clientY - dragStartRef.current.y;
    const dx = (dxPx / rect.width) * viewBox.w;
    const dy = (dyPx / rect.height) * viewBox.h;
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

  return (
    <div className="card fade-up">
      <div className="card-head">
        <span className="card-icon">🧠</span>
        <span className="card-title">Eval1 Layer1 分析结果</span>
        <button type="button" className="tn" onClick={onRefresh} style={{ marginLeft: "auto" }}>
          {loading ? "分析中..." : "重新分析"}
        </button>
      </div>
      {!data ? (
        <div className="card-body muted">暂无分析数据。</div>
      ) : (
        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
            <div className="score-card item">
              <strong>{data?.summary?.node_count || 0}</strong>
              节点
            </div>
            <div className="score-card item">
              <strong>{data?.summary?.edge_count || 0}</strong>
              边
            </div>
            <div className="score-card item">
              <strong>{data?.summary?.path_count || 0}</strong>
              路径
            </div>
            <div className="score-card item">
              <strong>{data?.summary?.conflict_count || 0}</strong>
              冲突
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 320px", gap: 10 }}>
            <div style={{ border: "1px solid var(--mist)", borderRadius: 8, overflow: "hidden" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderBottom: "1px solid var(--mist)" }}>
              <button
                type="button"
                className="tn"
                onClick={() => setViewMode("kg")}
                style={{
                  borderColor: viewMode === "kg" ? "rgba(0,229,160,.45)" : "var(--mist)",
                  background: viewMode === "kg" ? "rgba(0,229,160,.1)" : "var(--ink3)",
                  color: viewMode === "kg" ? "var(--jade)" : "var(--silver)",
                }}
              >
                图谱高亮
              </button>
              <button
                type="button"
                className="tn"
                onClick={() => setViewMode("fsm")}
                style={{
                  borderColor: viewMode === "fsm" ? "rgba(178,140,255,.45)" : "var(--mist)",
                  background: viewMode === "fsm" ? "rgba(178,140,255,.1)" : "var(--ink3)",
                  color: viewMode === "fsm" ? "var(--violet)" : "var(--silver)",
                }}
              >
                FSM
              </button>
              <span className="muted" style={{ marginLeft: "auto", fontSize: 11 }}>
                当前路径：{selectedPath?.path_id || "-"}
                {selectedPath?.category_label ? ` · ${selectedPath.category_label}` : ""}
              </span>
            </div>

            {viewMode === "kg" ? (
              <svg
                ref={svgRef}
                viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
                preserveAspectRatio="xMidYMid meet"
                onWheel={onWheel}
                onMouseDown={onMouseDown}
                onMouseMove={onMouseMove}
                onMouseUp={onMouseUp}
                onMouseLeave={onMouseUp}
                style={{
                  width: "100%",
                  height: 480,
                  background: "rgba(2,6,23,.55)",
                  cursor: isDragging ? "grabbing" : "grab",
                  userSelect: "none",
                }}
              >
                <g>
                  {edges.map((e, i) => {
                    const a = nodeById.get(e.from);
                    const b = nodeById.get(e.to);
                    if (!a || !b) return null;
                    const active = pathEdgeSet.has(`${e.from}->${e.to}`);
                    return (
                      <g key={`e-${i}`}>
                        <line
                          x1={a.x}
                          y1={a.y}
                          x2={b.x}
                          y2={b.y}
                          stroke={active ? "#00e5a0" : "rgba(148,163,184,.45)"}
                          strokeOpacity={selectedPath ? (active ? 0.95 : 0.14) : 0.45}
                          strokeWidth={active ? 2.6 : 1.2}
                          strokeDasharray={active ? "7 3" : "none"}
                        />
                      </g>
                    );
                  })}
                  {layoutNodes.map((n) => {
                    const s = toneByType(n.type);
                    const active = pathNodeSet.has(n.id);
                    return (
                    <g key={n.id} onClick={() => setSelectedNodeId(n.id)} style={{ cursor: "pointer" }}>
                        <rect
                          x={n.x - 44}
                          y={n.y - 18}
                          width={88}
                          height={36}
                          rx={8}
                          fill={s.fill}
                          stroke={active ? "#00e5a0" : s.stroke}
                          strokeOpacity={selectedPath ? (active ? 1 : 0.25) : 1}
                          opacity={selectedPath ? (active ? 1 : 0.68) : 1}
                          strokeWidth={active ? 2.4 : 1.5}
                        />
                        <text
                          x={n.x}
                          y={n.y + 4}
                          textAnchor="middle"
                          fontSize="10"
                          fill={active ? "#00e5a0" : s.text}
                          style={{ fontFamily: "JetBrains Mono, monospace" }}
                        >
                          {n.id}
                        </text>
                      {selectedNodeId === n.id && (
                        <rect
                          x={n.x - 48}
                          y={n.y - 22}
                          width={96}
                          height={44}
                          rx={9}
                          fill="none"
                          stroke="#b28cff"
                          strokeWidth={1.6}
                        />
                      )}
                      </g>
                    );
                  })}
                </g>
              </svg>
            ) : (
              <div style={{ width: "100%", height: 480, overflowY: "auto", background: "rgba(2,6,23,.55)", padding: 12 }}>
                {selectedPath?.flow_description ? (
                  <pre
                    style={{
                      margin: 0,
                      whiteSpace: "pre-wrap",
                      fontSize: 11,
                      lineHeight: 1.55,
                      color: "var(--silver)",
                      fontFamily: "inherit",
                    }}
                  >
                    {selectedPath.flow_description}
                  </pre>
                ) : (
                  <svg style={{ width: "100%", height: 460 }}>
                    {Array.isArray(selectedPath?.nodes) &&
                      selectedPath.nodes.map((nid, idx) => {
                        const x = 90 + idx * 130;
                        const y = 240;
                        const isEnd = idx === selectedPath.nodes.length - 1;
                        const tip = selectedPath?.node_labels?.[nid] || nodeLabelCatalog[nid] || nid;
                        return (
                          <g key={`fsm-${nid}-${idx}`} onClick={() => setSelectedNodeId(nid)} style={{ cursor: "pointer" }}>
                            {!isEnd && (
                              <line
                                x1={x + 42}
                                y1={y}
                                x2={x + 88}
                                y2={y}
                                stroke="#b28cff"
                                strokeWidth={2}
                                strokeDasharray="5 3"
                              />
                            )}
                            <title>{tip}</title>
                            <rect
                              x={x - 42}
                              y={y - 20}
                              width={84}
                              height={40}
                              rx={8}
                              fill="rgba(17,24,39,.85)"
                              stroke={nid.startsWith("F") ? "#00e5a0" : "#b28cff"}
                              strokeWidth={selectedNodeId === nid ? 2.8 : 2}
                            />
                            <text
                              x={x}
                              y={y + 4}
                              textAnchor="middle"
                              fontSize="10"
                              fill={nid.startsWith("F") ? "#00e5a0" : "#d7c7ff"}
                              style={{ fontFamily: "JetBrains Mono, monospace" }}
                            >
                              {nid}
                            </text>
                          </g>
                        );
                      })}
                  </svg>
                )}
              </div>
            )}
            </div>
            <div
              style={{
                border: "1px solid var(--mist)",
                borderRadius: 8,
                padding: 10,
                background: "rgba(3,7,18,.45)",
                display: "flex",
                flexDirection: "column",
                gap: 8,
                minHeight: 480,
              }}
            >
              <div style={{ fontSize: 12, color: "var(--silver)" }}>
                <strong style={{ color: "var(--violet)" }}>节点说明</strong>
              </div>
              {selectedNode ? (
                <>
                  <div style={{ fontSize: 12, color: "var(--jade)" }}>
                    {selectedNode.id} · {String(selectedNode.node_type || selectedNode.type || "node")}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--silver)", lineHeight: 1.55 }}>
                    {selectedNodeExplain}
                  </div>
                  <div style={{ marginTop: 6, fontSize: 11, color: "var(--smoke)" }}>
                    入边 {selectedNodeIn.length} · 出边 {selectedNodeOut.length}
                  </div>
                  <div style={{ maxHeight: 164, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
                    {selectedNodeIn.slice(0, 8).map((e, i) => (
                      <div key={`in-${i}`} style={{ fontSize: 11, color: "var(--silver)" }}>
                        ← {e.from} ({e.type})
                      </div>
                    ))}
                    {selectedNodeOut.slice(0, 8).map((e, i) => (
                      <div key={`out-${i}`} style={{ fontSize: 11, color: "var(--silver)" }}>
                        → {e.to} ({e.type})
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="muted" style={{ fontSize: 12 }}>
                  点击图中的节点查看详细解释。
                </div>
              )}
            </div>
          </div>
          <div className="muted" style={{ fontSize: 11 }}>
            交互：先在下方点击路径；图谱视图支持拖拽与缩放，并高亮该路径；FSM 视图展示对应状态序列。
          </div>

          <div className="eval1-path-section">
            <h4 style={{ margin: "4px 0 8px 0" }}>路径明细</h4>
            <div className="eval1-path-panel">
              <div className="eval1-path-list" role="listbox" aria-label="路径列表">
                {(data?.paths || []).map((p) => {
                  const active = selectedPathId === p.path_id;
                  return (
                    <button
                      key={p.path_id}
                      type="button"
                      role="option"
                      aria-selected={active}
                      className={`eval1-path-row ${active ? "active" : ""}`}
                      onClick={() => setSelectedPathId(p.path_id)}
                    >
                      <span className="eval1-path-row-title">
                        {p.path_id}
                        {p.category_label ? ` · ${p.category_label}` : ""}
                        {p.base_max_turns != null ? ` · turns=${p.base_max_turns}` : ""}
                      </span>
                      <span className="eval1-path-row-seq">{(p.nodes || []).join(" → ")}</span>
                    </button>
                  );
                })}
              </div>
              <div className="eval1-path-detail">
                {selectedPath ? (
                  <>
                    <div style={{ fontSize: 12, color: "var(--jade)", marginBottom: 6 }}>
                      {selectedPath.path_id}
                      {selectedPath.category_label ? ` · ${selectedPath.category_label}` : ""}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--silver)", marginBottom: 8, lineHeight: 1.45 }}>
                      {(selectedPath.nodes || []).join(" → ")}
                    </div>
                    {selectedPath.flow_description ? (
                      <pre className="eval1-path-detail-body">{selectedPath.flow_description}</pre>
                    ) : (
                      <p className="muted" style={{ fontSize: 12, margin: 0 }}>
                        该路径暂无逐步说明。
                      </p>
                    )}
                    <div style={{ fontSize: 11, color: "var(--smoke)", marginTop: 10 }}>
                      激活规则: {(selectedPath.activated_rules || []).join(", ") || "-"}
                    </div>
                  </>
                ) : (
                  <p className="muted" style={{ fontSize: 12, margin: 0 }}>
                    选择上方路径查看完整步骤说明。
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

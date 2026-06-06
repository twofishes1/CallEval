import { useCallback, useEffect, useRef, useState } from "react";

const TYPE_STYLE = {
  role: { fill: "#f5f3ff", stroke: "#7c3aed", text: "#6d28d9", rx: 10 },
  flow: { fill: "#ecfdf5", stroke: "#059669", text: "#047857", rx: 8 },
  know: { fill: "#eff6ff", stroke: "#0284c7", text: "#0369a1", rx: 12 },
  dial: { fill: "#fffbeb", stroke: "#d97706", text: "#b45309", rx: 8 },
  boun: { fill: "#fef2f2", stroke: "#dc2626", text: "#b91c1c", rx: 8 },
  var: { fill: "#faf5ff", stroke: "#9333ea", text: "#7e22ce", rx: 16 },
};

const EDGE_STYLE = {
  sequence: { stroke: "#34d399", dash: "none", arrow: true },
  requires: { stroke: "#a78bfa", dash: "4 3", arrow: true },
  triggers: { stroke: "#38bdf8", dash: "2 3", arrow: true },
  cond: { stroke: "#f87171", dash: "3 3", arrow: true },
  branch: { stroke: "#10b981", dash: "2 2", arrow: true },
  goto: { stroke: "#22c55e", dash: "6 2", arrow: true },
  guides: { stroke: "#16a34a", dash: "1 3", arrow: true },
  modifies: { stroke: "#fbbf24", dash: "5 2", arrow: true },
  uses: { stroke: "#c084fc", dash: "2 4", arrow: true },
  excludes: { stroke: "#fb923c", dash: "4 2", arrow: false },
  tension: { stroke: "#fb923c", dash: "6 3", arrow: false },
  overrides_with_condition: { stroke: "#a78bfa", dash: "3 2", arrow: true },
  applies_globally: { stroke: "#a78bfa", dash: "4 3", arrow: true },
  on_user_ask: { stroke: "#38bdf8", dash: "2 3", arrow: true },
};

const TYPE_NAMES = {
  role: "角色约束 Role",
  flow: "流程约束 Flow",
  know: "知识约束 Knowledge",
  dial: "话术约束 Dialogue",
  boun: "边界约束 Boundary",
  var: "变量节点 Variable",
};

function nodeById(nodes, id) {
  return nodes.find((n) => n.id === id);
}

export default function RuleKGCanvas({ kgViz }) {
  const svgRef = useRef(null);
  const transformRef = useRef({ x: 0, y: 0, scale: 1 });
  const [view, setView] = useState("all");
  const [selected, setSelected] = useState(null);
  const [sidebar, setSidebar] = useState(null);
  const dragging = useRef(false);
  const lastMouse = useRef(null);

  const nodes = kgViz?.nodes || [];
  const edges = kgViz?.edges || [];
  const conflicts = kgViz?.conflicts || [];
  const repairs = kgViz?.repairs || [];

  const conflictIds = new Set(conflicts.flatMap((c) => c.ids || []));

  const shouldShowNode = useCallback(
    (node) => {
      if (view === "all") return true;
      if (view === "flow")
        return ["role", "flow", "boun"].includes(node.type) || node.id.startsWith("VAR");
      if (view === "conflict") return conflictIds.has(node.id);
      return true;
    },
    [view, conflictIds]
  );

  const shouldShowEdge = useCallback(
    (edge) => {
      if (view === "all") return true;
      if (view === "flow") return ["sequence", "requires", "cond"].includes(edge.type);
      if (view === "conflict") return ["excludes", "tension"].includes(edge.type);
      return true;
    },
    [view]
  );

  const buildSidebar = useCallback(
    (node) => {
      const s = TYPE_STYLE[node.type] || TYPE_STYLE.dial;
      const outEdges = edges.filter((e) => e.from === node.id);
      const inEdges = edges.filter((e) => e.to === node.id);
      const myConflicts = conflicts.filter((c) => (c.ids || []).includes(node.id));

      return { node, s, outEdges, inEdges, myConflicts };
    },
    [edges, conflicts]
  );

  const draw = useCallback(() => {
    const svg = svgRef.current;
    if (!svg || !nodes.length) return;

    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    svg.appendChild(defs);
    Object.keys(EDGE_STYLE).forEach((t) => {
      const es = EDGE_STYLE[t];
      if (!es.arrow) return;
      const mk = document.createElementNS("http://www.w3.org/2000/svg", "marker");
      mk.setAttribute("id", `arr-${t}`);
      mk.setAttribute("viewBox", "0 0 10 10");
      mk.setAttribute("refX", "8");
      mk.setAttribute("refY", "5");
      mk.setAttribute("markerWidth", "5");
      mk.setAttribute("markerHeight", "5");
      mk.setAttribute("orient", "auto");
      const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("d", "M1 1L8 5L1 9");
      p.setAttribute("fill", "none");
      p.setAttribute("stroke", es.stroke);
      p.setAttribute("stroke-width", "1.5");
      mk.appendChild(p);
      defs.appendChild(mk);
    });

    const root = document.createElementNS("http://www.w3.org/2000/svg", "g");
    root.setAttribute("id", "root");
    const t = transformRef.current;
    root.setAttribute(
      "transform",
      `translate(${t.x},${t.y}) scale(${t.scale})`
    );
    svg.appendChild(root);

    const edgeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    root.appendChild(edgeG);

    edges.forEach((edge) => {
      const src = nodeById(nodes, edge.from);
      const dst = nodeById(nodes, edge.to);
      if (!src || !dst) return;
      const vis = shouldShowEdge(edge);
      const es = EDGE_STYLE[edge.type] || EDGE_STYLE.requires;
      const dx = dst.x - src.x;
      const dy = dst.y - src.y;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const ux = dx / len;
      const uy = dy / len;
      const x1 = src.x + ux * 38;
      const y1 = src.y + uy * 22;
      const x2 = dst.x - ux * 38;
      const y2 = dst.y - uy * 22;
      const mid = { x: (x1 + x2) / 2, y: (y1 + y2) / 2 };
      const off = 18;
      const cx = mid.x - uy * off;
      const cy = mid.y + ux * off;

      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", `M${x1},${y1} Q${cx},${cy} ${x2},${y2}`);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", es.stroke);
      path.setAttribute(
        "stroke-width",
        edge.type === "excludes" || edge.type === "tension" ? "1.5" : "1"
      );
      path.setAttribute("stroke-dasharray", es.dash);
      path.setAttribute(
        "stroke-opacity",
        vis ? (edge.type === "excludes" || edge.type === "tension" ? "0.9" : "0.55") : "0.08"
      );
      if (es.arrow) path.setAttribute("marker-end", `url(#arr-${edge.type})`);
      edgeG.appendChild(path);

      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", cx);
      label.setAttribute("y", cy - 4);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("font-size", "8");
      label.setAttribute("font-family", "JetBrains Mono, monospace");
      label.setAttribute("fill", es.stroke);
      label.setAttribute("opacity", vis ? "0.7" : "0.1");
      label.textContent = edge.label || edge.type;
      edgeG.appendChild(label);
    });

    const nodeG = document.createElementNS("http://www.w3.org/2000/svg", "g");
    root.appendChild(nodeG);

    nodes.forEach((node) => {
      const style = TYPE_STYLE[node.type] || TYPE_STYLE.dial;
      const vis = shouldShowNode(node);
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("opacity", vis ? "1" : "0.15");
      g.style.cursor = "pointer";

      const W = 80;
      const H = 44;
      const sh = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      sh.setAttribute("x", node.x - W / 2 + 2);
      sh.setAttribute("y", node.y - H / 2 + 2);
      sh.setAttribute("width", W);
      sh.setAttribute("height", H);
      sh.setAttribute("rx", style.rx);
      sh.setAttribute("fill", "#000");
      sh.setAttribute("opacity", "0.12");
      g.appendChild(sh);

      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", node.x - W / 2);
      rect.setAttribute("y", node.y - H / 2);
      rect.setAttribute("width", W);
      rect.setAttribute("height", H);
      rect.setAttribute("rx", style.rx);
      rect.setAttribute("fill", style.fill);
      rect.setAttribute("stroke", style.stroke);
      rect.setAttribute("stroke-width", selected?.id === node.id ? "2.5" : "1.5");
      g.appendChild(rect);

      if (view === "conflict" && conflictIds.has(node.id)) {
        const ring = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        ring.setAttribute("x", node.x - W / 2 - 3);
        ring.setAttribute("y", node.y - H / 2 - 3);
        ring.setAttribute("width", W + 6);
        ring.setAttribute("height", H + 6);
        ring.setAttribute("rx", style.rx + 2);
        ring.setAttribute("fill", "none");
        ring.setAttribute("stroke", "#f97316");
        ring.setAttribute("stroke-width", "2");
        ring.setAttribute("stroke-dasharray", "4 2");
        g.insertBefore(ring, sh);
      }

      const lines = (node.label || node.id).split("\n");
      lines.forEach((line, i) => {
        const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
        t.setAttribute("x", node.x);
        t.setAttribute("y", node.y + (i - (lines.length - 1) / 2) * 13);
        t.setAttribute("text-anchor", "middle");
        t.setAttribute("dominant-baseline", "central");
        t.setAttribute("font-size", i === 0 ? "10" : "9");
        t.setAttribute("font-family", "JetBrains Mono, monospace");
        t.setAttribute("font-weight", i === 0 ? "600" : "400");
        t.setAttribute("fill", i === 0 ? style.text : "#94a3b8");
        t.textContent = line;
        g.appendChild(t);
      });

      g.addEventListener("click", (e) => {
        e.stopPropagation();
        setSelected(node);
        setSidebar(buildSidebar(node));
      });

      nodeG.appendChild(g);
    });
  }, [nodes, edges, view, selected, shouldShowNode, shouldShowEdge, conflictIds, buildSidebar]);

  useEffect(() => {
    draw();
  }, [draw]);

  useEffect(() => {
    if (nodes.length && !selected) {
      const r1 = nodes.find((n) => n.id === "R1") || nodes[0];
      setSelected(r1);
      setSidebar(buildSidebar(r1));
    }
  }, [nodes, selected, buildSidebar]);

  if (!kgViz?.nodes?.length) {
    return (
      <div className="kg-canvas-empty">
        构建规则图谱后显示交互式节点图（参考设计稿）
      </div>
    );
  }

  const panHandlers = {
    onMouseDown: (e) => {
      if (e.target === svgRef.current) {
        dragging.current = true;
        lastMouse.current = { x: e.clientX, y: e.clientY };
      }
    },
    onMouseMove: (e) => {
      if (!dragging.current || !lastMouse.current) return;
      transformRef.current.x += e.clientX - lastMouse.current.x;
      transformRef.current.y += e.clientY - lastMouse.current.y;
      lastMouse.current = { x: e.clientX, y: e.clientY };
      draw();
    },
    onMouseUp: () => {
      dragging.current = false;
      lastMouse.current = null;
    },
    onWheel: (e) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.92 : 1.09;
      transformRef.current.scale = Math.max(
        0.3,
        Math.min(3, transformRef.current.scale * factor)
      );
      draw();
    },
  };

  const sb = sidebar;

  return (
    <div className="kg-canvas-wrap">
      <div className="kg-topbar">
        <div>
          <div className="kg-title">
            规则知识图谱 · {kgViz.title || "Layer1"}
          </div>
          <div className="kg-sub">
            节点 = 约束实体 · 边 = 依赖/互斥/顺序/触发 · 点击节点查看详情
          </div>
        </div>
        <div className="kg-mode-btns">
          {[
            ["all", "全部节点"],
            ["flow", "流程路径"],
            ["conflict", "冲突高亮"],
          ].map(([v, label]) => (
            <button
              key={v}
              type="button"
              className={`kg-mbtn ${view === v ? "active" : ""}`}
              onClick={() => setView(v)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="kg-body">
        <div className="kg-graph-panel" {...panHandlers}>
          <svg
            ref={svgRef}
            id="kg-svg"
            viewBox="0 0 1000 700"
            preserveAspectRatio="xMidYMid meet"
          />
        </div>
        <div className="kg-sidebar">
          {sb ? (
            <>
              <div className="kg-detail-header">
                <div>
                  <div className="kg-detail-id" style={{ color: sb.s.text }}>
                    {sb.node.id}
                  </div>
                  <div className="kg-detail-type">
                    {TYPE_NAMES[sb.node.type]}
                  </div>
                </div>
                <span
                  className="kg-detail-badge"
                  style={{
                    background: sb.s.fill,
                    borderColor: sb.s.stroke,
                    color: sb.s.text,
                  }}
                >
                  {sb.node.type.toUpperCase()}
                </span>
              </div>
              <div className="kg-detail-body">
                <div className="kg-detail-row">
                  <label>约束/内容</label>
                  <div>{sb.node.text}</div>
                </div>
                {sb.node.fsm && (
                  <div className="kg-detail-row">
                    <label>FSM</label>
                    <div className="mono">{sb.node.fsm}</div>
                  </div>
                )}
                {sb.node.detection && (
                  <div className="kg-detail-row">
                    <label>检测规则</label>
                    <div className="code">{sb.node.detection}</div>
                  </div>
                )}
                {sb.node.note && (
                  <div className="kg-detail-row">
                    <label>备注</label>
                    <div className="muted">{sb.node.note}</div>
                  </div>
                )}
                {(sb.inEdges.length > 0 || sb.outEdges.length > 0) && (
                  <div className="kg-detail-row">
                    <label>关联边</label>
                    <div className="kg-edge-list">
                      {sb.inEdges.map((e, i) => (
                        <div key={`in-${i}`} className="kg-edge-item">
                          ← {e.from} <span>({e.label})</span>
                        </div>
                      ))}
                      {sb.outEdges.map((e, i) => (
                        <div key={`out-${i}`} className="kg-edge-item">
                          → {e.to} <span>({e.label})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {sb.myConflicts.map((c, i) => (
                  <div key={i} className="kg-conflict-warn">
                    <strong>{c.type}</strong>
                    <p>{c.desc}</p>
                    {c.fix && <div className="fix">修复: {c.fix}</div>}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="kg-sidebar-empty">点击节点查看详情</div>
          )}
          <div className="kg-legend-bar">
            {Object.entries(TYPE_NAMES).map(([k, label]) => (
              <span key={k} className="kg-leg">
                <span className={`kg-leg-dot type-${k}`} />
                {label.split(" ")[0]}
              </span>
            ))}
          </div>
        </div>
      </div>

      <details className="kg-conflicts-panel" open>
        <summary>
          冲突分析与修复建议（{conflicts.length} 项冲突 · {repairs.length} 条修复）
        </summary>
        {conflicts.length === 0 ? (
          <div className="kg-conf-empty">当前未检测到冲突。</div>
        ) : (
          <div className="kg-conf-list">
            {conflicts.map((c, i) => (
              <div key={i} className={`kg-conf-item sev-${c.severity || "info"}`}>
                <div className="kg-conf-ids">
                  {(c.ids || []).map((x) => (
                    <code key={x}>{x}</code>
                  ))}
                </div>
                <div className="kg-conf-type">
                  <strong>{c.type}</strong>
                  {c.severity ? <span className="kg-conf-sev">{c.severity}</span> : null}
                </div>
                <div className="kg-conf-desc">{c.desc}</div>
                {c.fix ? <div className="kg-conf-fix">修复建议：{c.fix}</div> : null}
              </div>
            ))}
          </div>
        )}
      </details>
    </div>
  );
}

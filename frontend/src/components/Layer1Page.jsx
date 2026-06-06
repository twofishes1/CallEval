import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import "../styles-layer1.css";
import { layoutKgNodes } from "./studio/kgLayout.js";
import GoalFsmGraph from "./GoalFsmGraph.jsx";
import GoalFsmPath from "./GoalFsmPath.jsx";

// This page intentionally mirrors the provided HTML structure + classnames,
// while binding runtime data from backend (parsed + kg_viz).

// NOTE: Do not use CSS var(...) directly inside SVG presentation attributes like stroke.
// Some browsers won't resolve them. We resolve CSS variables to concrete colors at runtime.
const EDGE_STYLE_KEYS = {
  sequence: { css: "--jade", dash: "none", w: 1.5, arrow: true },
  requires: { css: "--violet", dash: "4 3", w: 1, arrow: true },
  triggers: { css: "--sky", dash: "2 3", w: 1, arrow: true },
  cond: { css: "--coral", dash: "3 3", w: 1, arrow: true },
  modifies: { css: "--amber", dash: "5 2", w: 1, arrow: true },
  uses: { css: "--violet", dash: "2 4", w: 1, arrow: true },
  excludes: { css: "--coral", dash: "4 2", w: 2, arrow: false },
  tension: { css: "--amber", dash: "6 3", w: 1.5, arrow: false },
  applies_globally: { css: "--violet", dash: "4 3", w: 1, arrow: true },
  global_guard: { css: "--violet", dash: "5 2", w: 1.5, arrow: true },
  covers_step: { css: "--jade", dash: "3 2", w: 1, arrow: true },
  on_user_ask: { css: "--sky", dash: "2 3", w: 1, arrow: true },
  branch: { css: "--jade", dash: "2 2", w: 1, arrow: true },
  goto: { css: "--jade", dash: "6 2", w: 1, arrow: true },
  guides: { css: "--jade2", dash: "1 3", w: 1, arrow: true },
  retention_jump: { css: "--amber", dash: "6 2", w: 1.5, arrow: true },
};

const NODE_STYLES = {
  role: { fill: "#1a1440", stroke: "#5b3fa0", text: "var(--violet)" },
  flow: { fill: "#0a1e16", stroke: "#145c3e", text: "var(--jade)" },
  know: { fill: "#081828", stroke: "#0a5a82", text: "var(--sky)" },
  dial: { fill: "#1a1408", stroke: "#7a4e0a", text: "var(--amber)" },
  boun: { fill: "#1e0b0b", stroke: "#852020", text: "var(--coral)" },
  var: { fill: "#180f2e", stroke: "#5b3fa0", text: "var(--violet)" },
};

function safeText(s, n = 140) {
  const t = (s || "").toString().trim();
  if (!t) return "—";
  return t.length > n ? t.slice(0, n) + "…" : t;
}

function normNodeType(t) {
  if (!t) return "dial";
  if (["role", "flow", "know", "dial", "boun", "var"].includes(t)) return t;
  return "dial";
}

function computeConstraintMeta(node) {
  // kg_viz nodes already include these fields when they originate from constraints
  const hard = node?.hard;
  const measurable = node?.measurable;
  return {
    hard,
    measurable,
    priority: node?.priority,
    detection: node?.detection || "",
  };
}

export default function Layer1Page({
  datasetId,
  datasetName,
  rawInstruction,
  variableValues,
  parsed,
  kgViz,
  layer2Meta,
  semanticEdgesAdded,
  ruleKgTestPlan,
  dialogueReports,
  onRecomputePaths,
  recomputingPaths,
  onRefreshParse,
  onBuildScene,
  building,
  parseSource,
  parseLoading,
}) {
  const [currentView, setCurrentView] = useState("parse"); // parse | kg | conflict | pipeline_layer2 | cases
  const [pipeIdx, setPipeIdx] = useState(0);
  const [selectedNode, setSelectedNode] = useState(null);
  const [p2Tab, setP2Tab] = useState("matrix"); // matrix | layer2
  const [matrixFocus, setMatrixFocus] = useState({ personaId: null, ruleId: null });
  const [fsmPersonaId, setFsmPersonaId] = useState(null);
  const [layer2PersonaFocus, setLayer2PersonaFocus] = useState(null);
  const [layer2PathFocus, setLayer2PathFocus] = useState(null);
  const [showAllPersonas, setShowAllPersonas] = useState(true);
  const [selectedPathId, setSelectedPathId] = useState(null);
  const [kgViewMode, setKgViewMode] = useState("kg"); // kg | fsm
  const [kgSimplifyMode, setKgSimplifyMode] = useState("simple"); // simple | full
  const [edgeEditMode, setEdgeEditMode] = useState(false);
  const [removedEdgeKeys, setRemovedEdgeKeys] = useState({});
  const [recomputeNote, setRecomputeNote] = useState("");

  const tooltipRef = useRef(null);
  const svgRef = useRef(null);
  const kgTransform = useRef({ x: 0, y: 0, scale: 0.85 });
  const kgDragging = useRef(false);
  const kgLastMouse = useRef(null);

  const rawNodes = useMemo(() => (kgViz?.nodes || []).map((n) => ({ ...n, type: normNodeType(n.type) })), [kgViz]);
  const rawEdges = useMemo(() => kgViz?.edges || [], [kgViz]);
  const edgeKey = useCallback((e) => `${e?.from || ""}|${e?.to || ""}|${e?.type || ""}`, []);
  const conflicts = useMemo(() => kgViz?.conflicts || [], [kgViz]);
  const repairs = useMemo(() => kgViz?.repairs || [], [kgViz]);
  const effectiveRulePaths = useMemo(
    () => (Array.isArray(ruleKgTestPlan?.paths) ? ruleKgTestPlan.paths : []),
    [ruleKgTestPlan]
  );
  const selectedRulePath = useMemo(
    () => effectiveRulePaths.find((p) => p.path_id === selectedPathId) || null,
    [effectiveRulePaths, selectedPathId]
  );
  const pathNodeSet = useMemo(
    () => new Set(Array.isArray(selectedRulePath?.nodes) ? selectedRulePath.nodes : []),
    [selectedRulePath]
  );
  const pathEdgeSet = useMemo(() => {
    const set = new Set();
    const ns = Array.isArray(selectedRulePath?.nodes) ? selectedRulePath.nodes : [];
    for (let i = 0; i + 1 < ns.length; i += 1) set.add(`${ns[i]}->${ns[i + 1]}`);
    return set;
  }, [selectedRulePath]);
  // Keep full parsed graph for non-KG views (parse/conflict/details).
  const nodes = rawNodes;
  const edges = rawEdges;
  // Only simplify the KG canvas rendering.
  const kgEdges = useMemo(() => {
    if (kgSimplifyMode !== "simple") return rawEdges;
    const nodeTypeById = new Map((rawNodes || []).map((n) => [n.id, n.type]));
    const rank = {
      global_guard: 0,
      applies_globally: 1,
      requires: 2,
      triggers: 3,
      sequence: 4,
      branch: 5,
      goto: 6,
      guides: 7,
      uses: 8,
      modifies: 9,
      on_user_ask: 10,
      covers_step: 11,
      excludes: 99,
      tension: 100,
    };
    // For D/B global constraints, keep only one representative outgoing edge.
    const bestOutByFrom = new Map();
    for (const e of rawEdges || []) {
      const t = String(e?.type || "");
      if (t === "excludes" || t === "tension") continue;
      const fromType = nodeTypeById.get(e?.from);
      if (fromType !== "dial" && fromType !== "boun") continue;
      const old = bestOutByFrom.get(e.from);
      const oldRank = old ? rank[String(old.type || "")] ?? 50 : Infinity;
      const newRank = rank[t] ?? 50;
      if (!old || newRank < oldRank) bestOutByFrom.set(e.from, e);
    }
    const picked = new Set((rawEdges || []).map((e) => {
      const k = `${e?.from || ""}|${e?.to || ""}|${e?.type || ""}`;
      return k;
    }));
    const out = [];
    for (const e of rawEdges || []) {
      const t = String(e?.type || "");
      const fromType = nodeTypeById.get(e?.from);
      if ((fromType === "dial" || fromType === "boun") && t !== "excludes" && t !== "tension") {
        const keepOne = bestOutByFrom.get(e.from);
        if (keepOne !== e) continue;
      }
      const k = `${e?.from || ""}|${e?.to || ""}|${e?.type || ""}`;
      if (!picked.has(k)) continue;
      out.push(e);
    }
    return out;
  }, [rawEdges, rawNodes, kgSimplifyMode]);
  const kgNodes = rawNodes;
  const effectiveEdges = useMemo(
    () => (kgEdges || []).filter((e) => !removedEdgeKeys[edgeKey(e)]),
    [kgEdges, removedEdgeKeys, edgeKey]
  );

  // Pipeline + Layer2 visualization (deterministic mapping; mirrors backend pipeline selection).
  const pipelinePersonas = useMemo(() => {
    const txt = (s) => (s || "").toString();
    const cs = parsed?.constraints || [];
    const hasBoundary = cs.some((c) => c?.type === "BOUNDARY");
    const hasKnowledge = (parsed?.faq_items || []).length > 0 || cs.some((c) => c?.type === "KNOWLEDGE");
    const hasFlow = (parsed?.flow_steps || []).length > 0 || cs.some((c) => c?.type === "FLOW");
    const hasRetention = (parsed?.flow_steps || []).some((s) =>
      ["挽留", "不想", "拒绝", "无法配送", "坚持", "劝", "鼓励"].some((k) => txt(s).includes(k))
    );
    const hasLen = cs.some(
      (c) =>
        c?.type === "DIALOGUE" &&
        ["30个字", "30 个字", "字以内", "字内", "字数", "≤", "不超过"].some((k) => txt(c?.text).includes(k))
    );
    const blob = [parsed?.task_description, parsed?.opening_line, ...(parsed?.flow_steps || [])]
      .filter(Boolean)
      .join("\n");
    const hasQuestioning = ["排名", "公平", "为什么", "凭什么", "后果", "影响", "依据", "规则"].some((k) => blob.includes(k));

    const set = new Set();
    if (hasFlow) set.add("cooperative");
    if (hasRetention) set.add("resistant");
    if (hasKnowledge) set.add("ignorant");
    if (hasBoundary) set.add("off_topic");
    if (hasLen) set.add("impatient");
    if (hasQuestioning) set.add("questioning");
    const order = ["cooperative", "resistant", "ignorant", "impatient", "off_topic", "questioning"];
    return order.filter((x) => set.has(x));
  }, [parsed]);

  const personaMeta = useMemo(() => {
    // If docs artifacts include persona configs, prefer them; else fallback to UI defaults.
    // Prefer dedicated Layer2 meta over kg_viz.meta to avoid stale docs artifacts.
    const cfg = layer2Meta?.personas || kgViz?.meta?.personas;
    const base = [
      {
        id: "cooperative",
        persona_type: "cooperative",
        icon: "😊",
        name: "配合型",
        emotion_state: "好奇且友善",
        background: "你是一名飞毛腿骑手，态度友好，愿意配合完成配送要求，并会主动确认关键细节。",
        cooperation_level: 0.9,
        goal_completion_tendency: 0.9,
        interruption_probability: 0.08,
        off_topic_probability: 0.05,
        system_prompt_fragment: "配合型骑手，倾向于按要求执行，偶尔追问一个细节。",
        utterance_patterns: ["简短确认", "偶尔追问一个细节", "接受建议"],
        suggested_runs: 3,
        coverage: {},
      },
      {
        id: "resistant",
        persona_type: "resistant",
        icon: "😤",
        name: "抵触型",
        emotion_state: "烦躁且抵触",
        background: "你是一名飞毛腿骑手，最近接单少，对规则有抵触，容易质疑和拒绝。",
        cooperation_level: 0.2,
        goal_completion_tendency: 0.4,
        interruption_probability: 0.3,
        off_topic_probability: 0.15,
        system_prompt_fragment: "抵触型骑手，先表达不满并多次拒绝，可能被说服也可能坚持拒绝。",
        utterance_patterns: ["表达不满", "质疑规则合理性", "多次拒绝", "最终可能被说服或坚持拒绝"],
        suggested_runs: 5,
        coverage: {},
      },
      {
        id: "ignorant",
        persona_type: "ignorant",
        icon: "🤔",
        name: "无知型",
        emotion_state: "困惑但愿意学习",
        background: "你是新骑手，对飞毛腿规则不了解，需要反复解释基础概念。",
        cooperation_level: 0.8,
        goal_completion_tendency: 0.8,
        interruption_probability: 0.1,
        off_topic_probability: 0.1,
        system_prompt_fragment: "无知型骑手，会频繁追问基础概念，不理解专业术语。",
        utterance_patterns: ["频繁追问基础概念", "需要反复解释", "不理解专业术语"],
        suggested_runs: 5,
        coverage: {},
      },
      {
        id: "impatient",
        persona_type: "impatient",
        icon: "⚡",
        name: "急躁型",
        emotion_state: "急躁且赶时间",
        background: "你正在配送途中，时间紧张，希望对方快速说重点。",
        cooperation_level: 0.6,
        goal_completion_tendency: 0.7,
        interruption_probability: 0.4,
        off_topic_probability: 0.12,
        system_prompt_fragment: "急躁型骑手，会打断并要求说重点，快速确认后可能挂断。",
        utterance_patterns: ["打断对话", "要求说重点", "快速确认后挂断"],
        suggested_runs: 3,
        coverage: {},
      },
      {
        id: "off_topic",
        persona_type: "off_topic",
        icon: "🌀",
        name: "偏题型",
        emotion_state: "跳脱且联想多",
        background: "你容易聊到工资、天气等无关话题，需要Bot拉回主题。",
        cooperation_level: 0.5,
        goal_completion_tendency: 0.6,
        interruption_probability: 0.2,
        off_topic_probability: 0.5,
        system_prompt_fragment: "话题偏移型骑手，频繁引入无关话题，被拉回后可能再次偏移。",
        utterance_patterns: ["频繁引入无关话题", "需要Bot拉回主题", "被拉回后又偏移"],
        suggested_runs: 3,
        coverage: {},
      },
      {
        id: "questioning",
        persona_type: "questioning",
        icon: "❓",
        name: "质疑型",
        emotion_state: "谨慎且较真",
        background: "你对规则细节反复确认，质疑公平性，要求证据或后果说明。",
        cooperation_level: 0.7,
        goal_completion_tendency: 0.7,
        interruption_probability: 0.18,
        off_topic_probability: 0.08,
        system_prompt_fragment: "质疑型骑手，追问细节并确认后果，要求提供依据。",
        utterance_patterns: ["质疑规则公平性", "要求提供证据", "追问如果不遵守的后果"],
        suggested_runs: 2,
        coverage: {},
      },
    ];
    const iconById = {
      cooperative: "😊",
      resistant: "😤",
      ignorant: "🤔",
      impatient: "⚡",
      off_topic: "🌀",
      questioning: "❓",
    };
    if (cfg && typeof cfg === "object") {
      const arr = Object.values(cfg).map((p) => {
        const id = p?.id || p?.persona_type || "";
        const fallback = base.find((b) => b.id === id);
        return {
          ...(fallback || {}),
          ...(p || {}),
          id,
          persona_type: p?.persona_type || id,
          icon: p?.icon || iconById[id] || fallback?.icon || "👤",
          // compat with older UI fields
          inj:
            p?.inj ||
            p?.prompt_injection_preview ||
            p?.system_prompt_fragment ||
            fallback?.system_prompt_fragment ||
            "",
        };
      });
      return arr.length ? arr : base;
    }
    return base;
  }, [kgViz, layer2Meta]);

  const goalFsmMeta = useMemo(() => kgViz?.meta?.goal_fsm || layer2Meta?.goal_fsm, [kgViz, layer2Meta]);

  const maxTurns = 20;

  const fsmStates = useMemo(
    () => [
      { id: "START", label: "START" },
      { id: "STEP_CONTRACT_NOTIFY", label: "合同通知" },
      { id: "STEP_EXPLAIN_RULE", label: "规则说明" },
      { id: "OBJECTION", label: "异议" },
      { id: "STEP_RETAIN_RIDER", label: "挽留" },
      { id: "FAQ_INCREMENTAL", label: "FAQ分轮" },
      { id: "FAQ_DIVERSION_OOB", label: "越权问答" },
      { id: "STEP_EXPLAIN_RANKING", label: "排名解释" },
      { id: "CLOSING", label: "收尾" },
      { id: "OBJECTION_FINAL", label: "拒绝终止" },
      { id: "END", label: "END" },
    ],
    []
  );

  const personaFsmPath = useCallback((personaId) => {
    // Deterministic “likely path” for visualization (until runtime streaming is wired).
    if (personaId === "cooperative")
      return ["START", "STEP_CONTRACT_NOTIFY", "STEP_EXPLAIN_RULE", "STEP_EXPLAIN_RANKING", "CLOSING", "END"];
    if (personaId === "resistant")
      return ["START", "STEP_CONTRACT_NOTIFY", "STEP_EXPLAIN_RULE", "OBJECTION", "STEP_RETAIN_RIDER", "OBJECTION_FINAL", "END"];
    if (personaId === "ignorant")
      return ["START", "STEP_CONTRACT_NOTIFY", "STEP_EXPLAIN_RULE", "FAQ_INCREMENTAL", "STEP_EXPLAIN_RANKING", "CLOSING", "END"];
    if (personaId === "impatient")
      return ["START", "STEP_CONTRACT_NOTIFY", "STEP_EXPLAIN_RULE", "CLOSING", "END"];
    if (personaId === "off_topic")
      return ["START", "STEP_CONTRACT_NOTIFY", "FAQ_DIVERSION_OOB", "STEP_EXPLAIN_RULE", "STEP_EXPLAIN_RANKING", "CLOSING", "END"];
    if (personaId === "questioning")
      return ["START", "STEP_CONTRACT_NOTIFY", "STEP_EXPLAIN_RULE", "FAQ_INCREMENTAL", "STEP_EXPLAIN_RANKING", "CLOSING", "END"];
    return ["START", "END"];
  }, []);

  const matrixRows = useMemo(() => {
    const cs = parsed?.constraints || [];
    const pick = (t) =>
      cs
        .filter((c) => c?.type === t)
        .map((c) => ({
          id: c.id,
          label: c.id,
          desc: safeText(c.text, 56),
          type: c.type,
          is_hard: !!c.is_hard,
          measurable: !!c.measurable,
        }));
    const rows = [...pick("FLOW"), ...pick("KNOWLEDGE"), ...pick("BOUNDARY"), ...pick("DIALOGUE")];
    return rows.slice(0, 18);
  }, [parsed]);

  const cellHint = useCallback((personaId, rowId) => {
    // Prefer backend PersonaCard.coverage (status: complete | partial | extra | none)
    const p = personaMeta.find((x) => x.id === personaId);
    const cov = p?.coverage && typeof p.coverage === "object" ? p.coverage : {};
    const s = cov?.[rowId];
    const det =
      (p?.final_coverage_details && typeof p.final_coverage_details === "object" ? p.final_coverage_details?.[rowId] : null) ||
      (p?.coverage_details && typeof p.coverage_details === "object" ? p.coverage_details?.[rowId] : null) ||
      (p?.baseline_coverage_details && typeof p.baseline_coverage_details === "object" ? p.baseline_coverage_details?.[rowId] : null);
    const mode = det?.mode || (((rowId || "")[0] || "") === "D" ? "always" : s ? "triggered" : "never");
    const reason = det?.reason || "";
    if (s === "complete") return { status: "complete", text: "完整✓", mode, reason };
    if (s === "partial") return { status: "partial", text: "部分", mode, reason };
    if (s === "extra") return { status: "extra", text: "意外触发", mode, reason };
    if (s === "none") return { status: "none", text: "不触发", mode, reason };

    // fallback when persona coverage doesn't specify this rule id
    const kind = rowId?.[0] || "";
    if (kind === "D") return { status: "complete", text: "✓\n全局检测", mode: "always", reason: "全局话术约束：每轮检测。" };
    return { status: "none", text: "不触发", mode: "never", reason: "" };
  }, [personaMeta]);

  const stats = useMemo(() => {
    const nodeCount = kgViz?.summary?.node_count ?? nodes.length;
    const edgeCount = kgViz?.summary?.edge_count ?? edges.length;
    const conflictCount = kgViz?.summary?.conflict_count ?? conflicts.length;
    const repairCount = kgViz?.summary?.repair_count ?? repairs.length;
    return { nodeCount, edgeCount, conflictCount, repairCount };
  }, [kgViz, nodes.length, edges.length, conflicts.length, repairs.length]);

  const fitKgTransform = useCallback((targetNodes, svgEl) => {
    const svg = svgEl || svgRef.current;
    if (!svg || !targetNodes?.length) return;
    const W = svg.clientWidth || 1000;
    const H = svg.clientHeight || 600;
    const pad = 56;
    const minX = Math.min(...targetNodes.map((n) => Number(n.x || 0))) - pad;
    const maxX = Math.max(...targetNodes.map((n) => Number(n.x || 0))) + pad;
    const minY = Math.min(...targetNodes.map((n) => Number(n.y || 0))) - pad;
    const maxY = Math.max(...targetNodes.map((n) => Number(n.y || 0))) + pad;
    let bw = Math.max(180, maxX - minX);
    let bh = Math.max(140, maxY - minY);
    const viewAspect = W / Math.max(H, 1);
    const contentAspect = bw / Math.max(bh, 1);
    if (contentAspect > Math.max(viewAspect, 1.35)) {
      bh = bw / Math.max(viewAspect, 1.1);
    } else if (contentAspect > viewAspect) {
      bh = bw / viewAspect;
    } else if (contentAspect < viewAspect) {
      bw = bh * viewAspect;
    }
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const fitScale = Math.min((W * 0.9) / bw, (H * 0.9) / bh);
    const scale = Math.max(0.88, Math.min(2.6, fitScale));
    const targetCx = W * 0.5;
    const targetCy = H * 0.5;
    kgTransform.current = {
      scale,
      x: targetCx - W * 0.2 - scale * cx,
      y: targetCy - scale * cy,
    };
  }, []);

  const positionedNodes = useMemo(() => layoutKgNodes(kgNodes), [kgNodes]);

  const semanticEdgeCount = useMemo(() => (Array.isArray(semanticEdgesAdded) ? semanticEdgesAdded.length : 0), [semanticEdgesAdded]);

  const selectNode = useCallback((node) => {
    setSelectedNode(node);
  }, []);

  const showTip = useCallback((ev, text) => {
    const el = tooltipRef.current;
    if (!el) return;
    el.style.display = "block";
    el.textContent = text || "";
    el.style.left = `${ev.clientX + 14}px`;
    el.style.top = `${ev.clientY - 8}px`;
  }, []);

  const moveTip = useCallback((ev) => {
    const el = tooltipRef.current;
    if (!el || el.style.display === "none") return;
    el.style.left = `${ev.clientX + 14}px`;
    el.style.top = `${ev.clientY - 8}px`;
  }, []);

  const hideTip = useCallback(() => {
    const el = tooltipRef.current;
    if (!el) return;
    el.style.display = "none";
  }, []);

  const toggleRemovedEdge = useCallback(
    (edge) => {
      const k = edgeKey(edge);
      setRemovedEdgeKeys((prev) => {
        const next = { ...prev };
        if (next[k]) delete next[k];
        else next[k] = true;
        return next;
      });
    },
    [edgeKey]
  );

  const resetEdgeEdits = useCallback(() => {
    setRemovedEdgeKeys({});
    setRecomputeNote("");
  }, []);

  const submitEdgeEdits = useCallback(async () => {
    if (!onRecomputePaths) return;
    const removeEdges = Object.keys(removedEdgeKeys)
      .map((k) => {
        const [from, to, type] = k.split("|");
        return { from, to, type };
      })
      .filter((x) => x.from && x.to);
    if (!removeEdges.length) {
      setRecomputeNote("未选择需要去除的关系边。");
      return;
    }
    try {
      const ret = await onRecomputePaths({ remove_edges: removeEdges, add_edges: [] });
      const removedCount = Number(ret?.applied_remove_count || 0);
      const pathCount = Number(ret?.rule_kg_test_plan?.path_count || 0);
      setRecomputeNote(`已重算：移除 ${removedCount} 条关系边，当前路径 ${pathCount} 条。`);
      setRemovedEdgeKeys({});
      setSelectedPathId(null);
      setEdgeEditMode(false);
    } catch (e) {
      setRecomputeNote(`重算失败：${String(e?.message || e || "unknown error")}`);
    }
  }, [onRecomputePaths, removedEdgeKeys]);

  const drawKG = useCallback(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const css = getComputedStyle(document.documentElement);
    const color = (name, fallback) =>
      (css.getPropertyValue(name) || fallback || "").trim() || fallback || "#94a3b8";
    const EDGE_STYLES = Object.fromEntries(
      Object.entries(EDGE_STYLE_KEYS).map(([k, v]) => [
        k,
        { stroke: color(v.css, "#94a3b8"), dash: v.dash, w: v.w, arrow: v.arrow },
      ])
    );

    const W = svg.clientWidth || 1000;
    const H = svg.clientHeight || 600;
    const NS = "http://www.w3.org/2000/svg";
    const el = (t, a = {}) => {
      const e = document.createElementNS(NS, t);
      Object.entries(a).forEach(([k, v]) => {
        if (v === "" || v == null) return;
        e.setAttribute(k, String(v));
      });
      return e;
    };

    svg.innerHTML = "";
    const defs = el("defs");
    svg.appendChild(defs);
    Object.entries(EDGE_STYLES).forEach(([k, v]) => {
      if (!v.arrow) return;
      const mk = el("marker", {
        id: `mk-${k}`,
        viewBox: "0 0 10 10",
        refX: "8",
        refY: "5",
        markerWidth: "5",
        markerHeight: "5",
        orient: "auto",
      });
      const p = el("path", {
        d: "M1 1L8 5L1 9",
        fill: "none",
        stroke: v.stroke,
        "stroke-width": "1.5",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
      });
      mk.appendChild(p);
      defs.appendChild(mk);
    });

    const t = kgTransform.current;
    const root = el("g", {
      id: "kg-root",
      transform: `translate(${W * 0.2 + t.x},${t.y}) scale(${t.scale})`,
    });
    svg.appendChild(root);

    const nodeById = new Map(positionedNodes.map((n) => [n.id, n]));

    // edges
    const eg = el("g");
    root.appendChild(eg);
    const pairSeen = new Map();
    effectiveEdges.forEach((edge) => {
      const s = nodeById.get(edge.from);
      const d = nodeById.get(edge.to);
      if (!s || !d) return;
      const es = EDGE_STYLES[edge.type] || EDGE_STYLES.requires;
      const keyPair = `${edge.from}->${edge.to}`;
      const dupIdx = pairSeen.get(keyPair) || 0;
      pairSeen.set(keyPair, dupIdx + 1);
      const dx = d.x - s.x;
      const dy = d.y - s.y;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const ux = dx / len;
      const uy = dy / len;
      const x1 = s.x + ux * 42;
      const y1 = s.y + uy * 24;
      const x2 = d.x - ux * 42;
      const y2 = d.y - uy * 24;
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2;
      const off = 14 + dupIdx * 8 + (Math.abs(dy) > 180 ? 10 : 0);
      const cx = mx - uy * off;
      const cy = my + ux * off;
      const inSelectedPath = pathEdgeSet.has(`${edge.from}->${edge.to}`);
      const hasPathSelection = !!selectedRulePath;
      const path = el("path", {
        d: `M${x1},${y1} Q${cx},${cy} ${x2},${y2}`,
        fill: "none",
        stroke: es.stroke,
        "stroke-width": inSelectedPath ? Math.max(2.4, es.w + 0.8) : es.w,
        "stroke-dasharray": es.dash,
        "stroke-opacity": hasPathSelection ? (inSelectedPath ? "0.95" : "0.12") : "0.78",
        "marker-end": es.arrow ? `url(#mk-${edge.type})` : "",
      });
      if (edgeEditMode) {
        path.style.cursor = "pointer";
        path.addEventListener("click", (e) => {
          e.stopPropagation();
          toggleRemovedEdge(edge);
        });
      }
      eg.appendChild(path);

      const lbl = el("text", {
        x: cx,
        y: cy - 5,
        "text-anchor": "middle",
        "font-size": "8",
        "font-family": "JetBrains Mono, monospace",
        fill: es.stroke,
        opacity: hasPathSelection ? (inSelectedPath ? "0.85" : "0.08") : "0.72",
      });
      lbl.textContent = edge.label || edge.type;
      if (edgeEditMode) {
        lbl.style.cursor = "pointer";
        lbl.addEventListener("click", (e) => {
          e.stopPropagation();
          toggleRemovedEdge(edge);
        });
      }
      eg.appendChild(lbl);
    });

    // selected path overlay (independent from KG native edges)
    if (selectedRulePath && Array.isArray(selectedRulePath?.nodes)) {
      const og = el("g");
      root.appendChild(og);
      const seq = selectedRulePath.nodes
        .map((nid) => nodeById.get(nid))
        .filter(Boolean);
      for (let i = 0; i + 1 < seq.length; i += 1) {
        const a = seq[i];
        const b = seq[i + 1];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const len = Math.sqrt(dx * dx + dy * dy) || 1;
        const ux = dx / len;
        const uy = dy / len;
        const x1 = a.x + ux * 42;
        const y1 = a.y + uy * 24;
        const x2 = b.x - ux * 42;
        const y2 = b.y - uy * 24;
        const cx = (x1 + x2) / 2 - uy * 22;
        const cy = (y1 + y2) / 2 + ux * 22;

        const glow = el("path", {
          d: `M${x1},${y1} Q${cx},${cy} ${x2},${y2}`,
          fill: "none",
          stroke: "#00e5a0",
          "stroke-width": "6",
          "stroke-opacity": "0.18",
        });
        og.appendChild(glow);
        const main = el("path", {
          d: `M${x1},${y1} Q${cx},${cy} ${x2},${y2}`,
          fill: "none",
          stroke: "#00e5a0",
          "stroke-width": "2.8",
          "stroke-dasharray": "8 4",
          "stroke-opacity": "0.95",
        });
        og.appendChild(main);
      }
    }

    // nodes
    const conflictIds = new Set((conflicts || []).flatMap((c) => c.ids || []));
    const ng = el("g");
    root.appendChild(ng);

    positionedNodes.forEach((node) => {
      const s = NODE_STYLES[node.type] || NODE_STYLES.dial;
      const g = el("g", { "data-id": node.id, cursor: "pointer" });
      const Wn = 96;
      const Hn = 50;
      const rx = node.type === "var" ? 22 : 8;
      const sh = el("rect", {
        x: node.x - Wn / 2 + 2,
        y: node.y - Hn / 2 + 2,
        width: Wn,
        height: Hn,
        rx,
        fill: "#000",
        opacity: "0.4",
      });
      const rect = el("rect", {
        x: node.x - Wn / 2,
        y: node.y - Hn / 2,
        width: Wn,
        height: Hn,
        rx,
        fill: s.fill,
        stroke: s.stroke,
        "stroke-width": pathNodeSet.has(node.id) ? "2.6" : "1.5",
        "stroke-opacity": selectedRulePath ? (pathNodeSet.has(node.id) ? "1" : "0.25") : "1",
        opacity: selectedRulePath ? (pathNodeSet.has(node.id) ? "1" : "0.65") : "1",
      });
      g.appendChild(sh);
      if (conflictIds.has(node.id)) {
        const ring = el("rect", {
          x: node.x - Wn / 2 - 3,
          y: node.y - Hn / 2 - 3,
          width: Wn + 6,
          height: Hn + 6,
          rx: rx + 2,
          fill: "none",
          stroke: EDGE_STYLES.tension?.stroke || "#ffb830",
          "stroke-width": "1.5",
          "stroke-dasharray": "4 2",
          opacity: "0.7",
        });
        g.appendChild(ring);
      }
      g.appendChild(rect);

      const lines = (node.label || node.id).split("\n");
      lines.forEach((ln, i) => {
        const t = el("text", {
          x: node.x,
          y: node.y + (i - (lines.length - 1) / 2) * 13,
          "text-anchor": "middle",
          "dominant-baseline": "central",
          "font-size": i === 0 ? "11" : "10",
          "font-family": "JetBrains Mono, monospace",
          "font-weight": i === 0 ? "600" : "400",
          fill: i === 0 ? s.text : "#94a3b8",
        });
        t.textContent = ln;
        g.appendChild(t);
      });

      g.addEventListener("click", (e) => {
        e.stopPropagation();
        selectNode(node);
      });
      g.addEventListener("mouseenter", (e) => showTip(e, node.text || node.id));
      g.addEventListener("mousemove", moveTip);
      g.addEventListener("mouseleave", hideTip);
      ng.appendChild(g);
    });

    // pan / zoom handlers (attached each draw)
    svg.onmousedown = (e) => {
      kgDragging.current = true;
      kgLastMouse.current = { x: e.clientX, y: e.clientY };
    };
    window.onmouseup = () => {
      kgDragging.current = false;
      kgLastMouse.current = null;
    };
    window.onmousemove = (e) => {
      if (!kgDragging.current || !kgLastMouse.current) return;
      kgTransform.current.x += e.clientX - kgLastMouse.current.x;
      kgTransform.current.y += e.clientY - kgLastMouse.current.y;
      kgLastMouse.current = { x: e.clientX, y: e.clientY };
      const r = svg.querySelector("#kg-root");
      if (r) {
        const tt = kgTransform.current;
        r.setAttribute(
          "transform",
          `translate(${W * 0.2 + tt.x},${tt.y}) scale(${tt.scale})`
        );
      }
    };
    svg.onwheel = (e) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.92 : 1.09;
      const tt = kgTransform.current;
      tt.scale = Math.max(0.3, Math.min(2.5, tt.scale * factor));
      const r = svg.querySelector("#kg-root");
      if (r) {
        r.setAttribute(
          "transform",
          `translate(${W * 0.2 + tt.x},${tt.y}) scale(${tt.scale})`
        );
      }
    };
  }, [positionedNodes, effectiveEdges, conflicts, selectNode, showTip, moveTip, hideTip, pathEdgeSet, pathNodeSet, selectedRulePath, edgeEditMode, toggleRemovedEdge]);

  const resetKG = useCallback(() => {
    fitKgTransform(positionedNodes);
    requestAnimationFrame(() => drawKG());
  }, [fitKgTransform, positionedNodes, drawKG]);

  useEffect(() => {
    if (currentView === "kg") {
      requestAnimationFrame(() => {
        if (!selectedRulePath && positionedNodes.length) {
          fitKgTransform(positionedNodes);
        }
        drawKG();
      });
    }
  }, [currentView, drawKG, positionedNodes, selectedRulePath, fitKgTransform]);

  useEffect(() => {
    if (currentView !== "kg" || !selectedRulePath || !positionedNodes.length) return;
    const svg = svgRef.current;
    if (!svg) return;
    const pathNodes = positionedNodes.filter((n) => pathNodeSet.has(n.id));
    if (!pathNodes.length) return;

    const W = svg.clientWidth || 1000;
    const H = svg.clientHeight || 600;
    const pad = 80;
    const minX = Math.min(...pathNodes.map((n) => Number(n.x || 0))) - pad;
    const maxX = Math.max(...pathNodes.map((n) => Number(n.x || 0))) + pad;
    const minY = Math.min(...pathNodes.map((n) => Number(n.y || 0))) - pad;
    const maxY = Math.max(...pathNodes.map((n) => Number(n.y || 0))) + pad;
    const bw = Math.max(180, maxX - minX);
    const bh = Math.max(140, maxY - minY);
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;

    let fitBw = bw;
    let fitBh = bh;
    const viewAspect = W / Math.max(H, 1);
    const contentAspect = bw / Math.max(bh, 1);
    if (contentAspect > viewAspect) fitBh = bw / viewAspect;
    else if (contentAspect < viewAspect) fitBw = bh * viewAspect;
    const fitScale = Math.min((W * 0.9) / fitBw, (H * 0.9) / fitBh);
    const scale = Math.max(0.88, Math.min(2.6, fitScale));
    const targetCx = W * 0.5;
    const targetCy = H * 0.5;
    kgTransform.current = {
      scale,
      x: targetCx - W * 0.2 - scale * cx,
      y: targetCy - scale * cy,
    };
    requestAnimationFrame(() => drawKG());
  }, [selectedRulePath, pathNodeSet, positionedNodes, currentView, drawKG]);

  useEffect(() => {
    if (!effectiveRulePaths.length) {
      setSelectedPathId(null);
      return;
    }
    if (selectedPathId && !effectiveRulePaths.some((p) => p.path_id === selectedPathId)) {
      setSelectedPathId(null);
    }
  }, [effectiveRulePaths, selectedPathId]);

  // Dataset switch: default to "full graph" mode (no selected path).
  useEffect(() => {
    setSelectedPathId(null);
    setKgViewMode("kg");
    setKgSimplifyMode("simple");
    setEdgeEditMode(false);
    setRemovedEdgeKeys({});
    setRecomputeNote("");
  }, [datasetId]);

  useEffect(() => {
    if (currentView !== "kg" || !positionedNodes.length) return;
    requestAnimationFrame(() => {
      fitKgTransform(positionedNodes);
      drawKG();
    });
  }, [datasetId, positionedNodes, currentView, fitKgTransform, drawKG]);

  // Pipeline click -> view mapping (matches provided HTML goPipe)
  const goPipe = useCallback((i) => {
    setPipeIdx(i);
    // 0..2 layer1, 3 pipeline matrix, 4 layer2 view, 5..6 conflict/repair, 7 cases
    const views = ["parse", "parse", "kg", "pipeline_layer2", "pipeline_layer2", "conflict", "conflict", "cases"];
    const v = views[i] || "parse";
    setCurrentView(v);
    if (v === "pipeline_layer2") {
      setP2Tab(i === 4 ? "layer2" : "matrix");
    }
  }, []);

  const showView = useCallback((v) => {
    setCurrentView(v);
  }, []);

  const renderParseView = () => {
    // Build node list from kgViz nodes (already positioned & typed)
    const nodeCards = nodes;
    const vars = nodes.filter((n) => n.type === "var");

    const typeCounts = {
      role: nodeCards.filter((n) => n.type === "role").length,
      flow: nodeCards.filter((n) => n.type === "flow").length,
      know: nodeCards.filter((n) => n.type === "know").length,
      dial: nodeCards.filter((n) => n.type === "dial").length,
      boun: nodeCards.filter((n) => n.type === "boun").length,
      var: nodeCards.filter((n) => n.type === "var").length,
    };

    const types = [
      { key: "role", color: "var(--violet)", bg: "var(--violet-bg)", label: "角色约束", icon: "👤", count: typeCounts.role },
      { key: "flow", color: "var(--jade)", bg: "var(--jade-bg)", label: "流程约束", icon: "🔀", count: typeCounts.flow },
      { key: "know", color: "var(--sky)", bg: "var(--sky-bg)", label: "知识约束", icon: "📚", count: typeCounts.know },
      { key: "dial", color: "var(--amber)", bg: "var(--amber-bg)", label: "话术约束", icon: "💬", count: typeCounts.dial },
      { key: "boun", color: "var(--coral)", bg: "var(--coral-bg)", label: "边界约束", icon: "🚧", count: typeCounts.boun },
      { key: "var", color: "var(--violet)", bg: "var(--violet-bg)", label: "变量节点", icon: "📦", count: typeCounts.var },
    ];

    return (
      <>
        <div className="card fade-up">
          <div className="card-head">
            <span className="card-icon">📄</span>
            <span className="card-title">原始指令（{datasetName || datasetId || "custom"}）</span>
            <span className="card-badge" style={{ border: "1px solid rgba(255,184,48,.25)", color: "var(--amber)", background: "rgba(255,184,48,.04)" }}>
              预处理结果：段落/变量/流程/FAQ 来自真实指令
            </span>
          </div>
          <div className="card-body">
            <div className="raw-input">{safeText(rawInstruction, 2200)}</div>
          </div>
        </div>

        <div className="fade-up fd1">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10 }}>
            {types.map((t) => (
              <div
                key={t.key}
                style={{
                  background: t.bg,
                  border: "1px solid",
                  borderColor: `${t.color}33`,
                  borderRadius: 10,
                  padding: "12px 10px",
                  textAlign: "center",
                }}
              >
                <div style={{ fontSize: 20, marginBottom: 5 }}>{t.icon}</div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 18, fontWeight: 700, color: t.color }}>
                  {t.count}
                </div>
                <div style={{ fontSize: 10, color: "var(--smoke)", marginTop: 2 }}>{t.label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card fade-up fd2">
          <div className="card-head">
            <span className="card-icon">🔩</span>
            <span className="card-title">解析节点（点击查看详情）</span>
          </div>
          <div className="card-body">
            <div className="node-grid" id="node-grid">
              {nodeCards.map((n) => {
                const s = NODE_STYLES[n.type] || NODE_STYLES.dial;
                const meta = computeConstraintMeta(n);
                const hasCode = !!meta.detection;
                return (
                  <div
                    key={n.id}
                    className={`node-card ${selectedNode?.id === n.id ? "selected" : ""}`}
                    style={{ background: s.fill, borderColor: s.stroke, outlineColor: s.stroke }}
                    onClick={() => selectNode(n)}
                    onMouseEnter={(e) => showTip(e, `${n.id}: ${safeText(n.text, 60)}`)}
                    onMouseMove={moveTip}
                    onMouseLeave={hideTip}
                  >
                    <div className="nc-id" style={{ color: s.text }}>
                      {n.id} · {n.type.toUpperCase()}
                    </div>
                    <div className="nc-text">{safeText(n.text, 220)}</div>
                    <div className="nc-pills">
                      {meta.hard !== undefined ? (
                        <span className={`pill ${meta.hard ? "hard" : "soft"}`}>{meta.hard ? "硬约束" : "软约束"}</span>
                      ) : null}
                      {meta.measurable !== undefined ? (
                        <span className={`pill ${meta.measurable ? "auto" : "llm"}`}>{meta.measurable ? "自动检测" : "LLM Judge"}</span>
                      ) : null}
                      {n.type === "var" ? <span className="pill over">变量</span> : null}
                    </div>
                    {hasCode ? <div className="nc-code">{safeText(meta.detection, 160)}</div> : null}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="card fade-up fd3">
          <div className="card-head">
            <span className="card-icon">📦</span>
            <span className="card-title">变量节点（占位符解析结果）</span>
          </div>
          <div className="card-body">
            <table className="var-tbl">
              <thead>
                <tr>
                  <th>占位符</th>
                  <th>测试值</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(variableValues || {}).map(([k, v]) => (
                  <tr key={k}>
                    <td>
                      <span className="vn">${`{${k}}`}</span>
                    </td>
                    <td>
                      <span className="vv">{String(v)}</span>
                    </td>
                  </tr>
                ))}
                {Object.keys(variableValues || {}).length === 0 ? (
                  <tr>
                    <td colSpan={2} className="vl">
                      无变量
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </>
    );
  };

  const renderPipelineLayer2View = () => {
    const reports = Array.isArray(dialogueReports) ? dialogueReports : [];
    const personasToShow = (showAllPersonas ? personaMeta : personaMeta.filter((p) => (pipelinePersonas.length ? pipelinePersonas : ["cooperative"]).includes(p.id)))
      .filter(Boolean);

    const pathIdOf = (rep) => {
      const tag = String(rep?.metadata?.scenario_tag || "");
      const m = tag.match(/path_([^_]+)__persona_/);
      if (m?.[1]) return m[1];
      return "UNKNOWN_PATH";
    };

    const selectedPersona = layer2PersonaFocus || personasToShow?.[0]?.id || "";
    const personaReports = reports.filter(
      (r) => String(r?.persona_type || "").toLowerCase() === String(selectedPersona || "").toLowerCase()
    );
    const grouped = {};
    for (const rep of personaReports) {
      const pid = pathIdOf(rep);
      if (!grouped[pid]) grouped[pid] = [];
      grouped[pid].push(rep);
    }
    const pathKeys = Object.keys(grouped).sort();
    const selectedPath = layer2PathFocus && grouped[layer2PathFocus] ? layer2PathFocus : (pathKeys[0] || "");
    const selectedRuns = selectedPath ? grouped[selectedPath] || [] : [];

    return (
      <div className="card fade-up">
        <div className="card-head">
          <span className="card-icon">🎭</span>
          <span className="card-title">Layer2 对话查看器（用户 × 路径）</span>
          <span
            className="card-badge"
            style={{ background: "rgba(178,140,255,.10)", border: "1px solid rgba(178,140,255,.25)", color: "var(--violet)" }}
          >
            仅展示对话与终止原因
          </span>
        </div>
        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: 12 }}>用户：</span>
            {personasToShow.map((pp) => {
              const pid = pp?.id || "";
              const active = pid === selectedPersona;
              return (
                <button
                  key={`persona-pill-${pid}`}
                  type="button"
                  className="tn"
                  onClick={() => {
                    setLayer2PersonaFocus(pid);
                    setLayer2PathFocus(null);
                  }}
                  style={{
                    borderColor: active ? "rgba(178,140,255,.45)" : "var(--mist)",
                    background: active ? "rgba(178,140,255,.12)" : "var(--ink3)",
                    color: active ? "var(--violet)" : "var(--silver)",
                  }}
                >
                  {(pp?.persona_type || pid || "").toString().toUpperCase()}
                </button>
              );
            })}
            <button
              type="button"
              className="tn"
              onClick={() => setShowAllPersonas((v) => !v)}
              style={{ marginLeft: 8 }}
            >
              {showAllPersonas ? "仅显示pipeline用户" : "显示全部用户"}
            </button>
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: 12 }}>路径：</span>
            {pathKeys.length ? (
              pathKeys.map((pk) => {
                const active = pk === selectedPath;
                return (
                  <button
                    key={`path-pill-${pk}`}
                    type="button"
                    className="tn"
                    onClick={() => setLayer2PathFocus(pk)}
                    style={{
                      borderColor: active ? "rgba(0,229,160,.45)" : "var(--mist)",
                      background: active ? "rgba(0,229,160,.10)" : "var(--ink3)",
                      color: active ? "var(--jade)" : "var(--silver)",
                    }}
                  >
                    {pk} ({(grouped[pk] || []).length})
                  </button>
                );
              })
            ) : (
              <span className="muted" style={{ fontSize: 12 }}>该用户暂无路径对话记录。</span>
            )}
          </div>

          <div style={{ border: "1px solid var(--mist)", borderRadius: 10, padding: 10, background: "rgba(2,6,23,.45)" }}>
            {!selectedRuns.length ? (
              <div className="muted" style={{ fontSize: 12 }}>暂无对话记录。请先运行评测任务。</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 520, overflowY: "auto", paddingRight: 4 }}>
                {selectedRuns.map((rep, ridx) => (
                  <details key={rep?.report_id || `run-${selectedPath}-${ridx}`} open={ridx === 0} style={{ border: "1px solid var(--mist)", borderRadius: 8, padding: "6px 8px", background: "rgba(3,7,18,.35)" }}>
                    <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--silver)" }}>
                      run#{Number(rep?.metadata?.run_index ?? 0) + 1} · 终止={rep?.termination_reason || "unknown"} · {rep?.dialogue_turns?.length || 0} turns
                    </summary>
                    <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
                      {(rep?.dialogue_turns || []).map((t, idx) => (
                        <div
                          key={`${rep?.report_id || "r"}-${idx}`}
                          style={{
                            fontSize: 12,
                            lineHeight: 1.45,
                            color: t?.role === "bot" ? "var(--jade)" : "var(--silver)",
                            fontFamily: "var(--mono)",
                          }}
                        >
                          {t?.role === "bot" ? "BOT" : "USER"}: {String(t?.content || "")}
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderKGView = () => {
    const totalPaths = Number(ruleKgTestPlan?.path_count || effectiveRulePaths.length || 0);
    return (
      <div className="card fade-up" style={{ height: "calc(100vh - 140px)" }}>
        <div className="card-head">
          <span className="card-icon">🕸️</span>
          <span className="card-title">规则知识图谱 (Rule KG)</span>
          <div style={{ display: "flex", gap: 8, marginLeft: "auto", fontSize: 11, alignItems: "center" }}>
            <button
              type="button"
              onClick={() => setKgViewMode("kg")}
              style={{
                padding: "4px 10px",
                borderRadius: 5,
                border: `1px solid ${kgViewMode === "kg" ? "rgba(0,229,160,.45)" : "var(--mist)"}`,
                background: kgViewMode === "kg" ? "rgba(0,229,160,.1)" : "var(--ink3)",
                color: kgViewMode === "kg" ? "var(--jade)" : "var(--silver)",
                fontSize: 11,
                cursor: "pointer",
              }}
            >
              图谱
            </button>
            <button
              type="button"
              onClick={() => setKgViewMode("fsm")}
              style={{
                padding: "4px 10px",
                borderRadius: 5,
                border: `1px solid ${kgViewMode === "fsm" ? "rgba(178,140,255,.45)" : "var(--mist)"}`,
                background: kgViewMode === "fsm" ? "rgba(178,140,255,.12)" : "var(--ink3)",
                color: kgViewMode === "fsm" ? "var(--violet)" : "var(--silver)",
                fontSize: 11,
                cursor: "pointer",
              }}
            >
              FSM
            </button>
            <span style={{ color: "var(--smoke)" }}>拖动平移 · 滚轮缩放 · 点击节点查看详情</span>
            <button
              type="button"
              onClick={resetKG}
              disabled={kgViewMode !== "kg"}
              style={{
                padding: "4px 10px",
                borderRadius: 5,
                border: "1px solid var(--mist)",
                background: "var(--ink3)",
                color: "var(--silver)",
                fontSize: 11,
                cursor: kgViewMode === "kg" ? "pointer" : "not-allowed",
                opacity: kgViewMode === "kg" ? 1 : 0.5,
              }}
            >
              重置视图
            </button>
            <button
              type="button"
              onClick={() => setKgSimplifyMode("simple")}
              disabled={kgViewMode !== "kg"}
              style={{
                padding: "4px 10px",
                borderRadius: 5,
                border: `1px solid ${kgSimplifyMode === "simple" ? "rgba(0,229,160,.45)" : "var(--mist)"}`,
                background: kgSimplifyMode === "simple" ? "rgba(0,229,160,.1)" : "var(--ink3)",
                color: kgSimplifyMode === "simple" ? "var(--jade)" : "var(--silver)",
                fontSize: 11,
                cursor: kgViewMode === "kg" ? "pointer" : "not-allowed",
                opacity: kgViewMode === "kg" ? 1 : 0.5,
              }}
            >
              简洁图
            </button>
            <button
              type="button"
              onClick={() => setKgSimplifyMode("full")}
              disabled={kgViewMode !== "kg"}
              style={{
                padding: "4px 10px",
                borderRadius: 5,
                border: `1px solid ${kgSimplifyMode === "full" ? "rgba(178,140,255,.45)" : "var(--mist)"}`,
                background: kgSimplifyMode === "full" ? "rgba(178,140,255,.12)" : "var(--ink3)",
                color: kgSimplifyMode === "full" ? "var(--violet)" : "var(--silver)",
                fontSize: 11,
                cursor: kgViewMode === "kg" ? "pointer" : "not-allowed",
                opacity: kgViewMode === "kg" ? 1 : 0.5,
              }}
            >
              完整图
            </button>
            <button
              type="button"
              onClick={() => setEdgeEditMode((v) => !v)}
              disabled={kgViewMode !== "kg"}
              style={{
                padding: "4px 10px",
                borderRadius: 5,
                border: `1px solid ${edgeEditMode ? "rgba(255,184,48,.45)" : "var(--mist)"}`,
                background: edgeEditMode ? "rgba(255,184,48,.12)" : "var(--ink3)",
                color: edgeEditMode ? "var(--amber)" : "var(--silver)",
                fontSize: 11,
                cursor: kgViewMode === "kg" ? "pointer" : "not-allowed",
                opacity: kgViewMode === "kg" ? 1 : 0.5,
              }}
            >
              {edgeEditMode ? "退出关系编辑" : "关系编辑"}
            </button>
            <button
              type="button"
              onClick={submitEdgeEdits}
              disabled={kgViewMode !== "kg" || !edgeEditMode || recomputingPaths}
              style={{
                padding: "4px 10px",
                borderRadius: 5,
                border: "1px solid rgba(0,229,160,.45)",
                background: "rgba(0,229,160,.1)",
                color: "var(--jade)",
                fontSize: 11,
                cursor: kgViewMode === "kg" && edgeEditMode && !recomputingPaths ? "pointer" : "not-allowed",
                opacity: kgViewMode === "kg" && edgeEditMode ? 1 : 0.5,
              }}
            >
              {recomputingPaths ? "重算中…" : "提交后端重算路径"}
            </button>
            <button
              type="button"
              onClick={resetEdgeEdits}
              disabled={kgViewMode !== "kg" || !edgeEditMode}
              style={{
                padding: "4px 10px",
                borderRadius: 5,
                border: "1px solid var(--mist)",
                background: "var(--ink3)",
                color: "var(--silver)",
                fontSize: 11,
                cursor: kgViewMode === "kg" && edgeEditMode ? "pointer" : "not-allowed",
                opacity: kgViewMode === "kg" && edgeEditMode ? 1 : 0.5,
              }}
            >
              清空改动
            </button>
          </div>
        </div>
        {kgViewMode === "kg" && edgeEditMode ? (
          <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>
            关系编辑模式：点击任意连线可标记删除，再点击“提交后端重算路径”。
            当前待删 {Object.keys(removedEdgeKeys).length} 条。
          </div>
        ) : null}
        {kgViewMode === "kg" ? (
          <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>
            当前{kgSimplifyMode === "simple" ? "简洁图" : "完整图"}：节点 {kgNodes.length}，连线 {effectiveEdges.length}
          </div>
        ) : null}
        {recomputeNote ? (
          <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>
            {recomputeNote}
          </div>
        ) : null}
        <div className="kg-view-wrap">
          <div className="kg-path-panel">
            <div className="kg-path-head">
              <strong>START → END 路径</strong>
              <span className="muted">{totalPaths} 条</span>
            </div>
            <div style={{ marginBottom: 8 }}>
              <button
                type="button"
                className={`kg-path-item ${!selectedPathId ? "active" : ""}`}
                onClick={() => setSelectedPathId(null)}
                style={{ width: "100%" }}
              >
                <div className="kg-path-id">FULL_GRAPH</div>
                <div className="kg-path-seq">不选择路径，显示完整知识图谱连线</div>
              </button>
            </div>
            <div className="kg-path-list">
              {effectiveRulePaths.length ? (
                effectiveRulePaths.map((p) => (
                  <button
                    key={p.path_id}
                    type="button"
                    className={`kg-path-item ${selectedPathId === p.path_id ? "active" : ""}`}
                    onClick={() => setSelectedPathId((old) => (old === p.path_id ? null : p.path_id))}
                  >
                    <div className="kg-path-id">{p.path_id}</div>
                    <div className="kg-path-seq">{(p.nodes || []).join(" → ")}</div>
                    <div className="kg-path-meta">
                      {(p.path_kind || "flow_path") === "probe_non_flow" ? "非流程探测路径" : "流程路径"} · 激活规则{" "}
                      {(p.activated_rule_ids || []).length} 条
                    </div>
                  </button>
                ))
              ) : (
                <div className="muted">当前数据未返回路径计划。</div>
              )}
            </div>
            {selectedRulePath ? (
              <div
                style={{
                  marginTop: 10,
                  borderTop: "1px solid var(--mist)",
                  paddingTop: 10,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ fontSize: 11, color: "var(--silver)" }}>
                  <strong style={{ color: "var(--jade)" }}>{selectedRulePath.path_id}</strong>{" "}
                  · {(selectedRulePath.path_kind || "flow_path") === "probe_non_flow" ? "非流程探测路径" : "流程路径"} ·{" "}
                  {selectedRulePath.reachable === false ? "不可达" : "可达"}
                </div>
                <div style={{ fontSize: 10, color: "var(--smoke)", lineHeight: 1.45 }}>
                  {(Array.isArray(selectedRulePath.justifications) ? selectedRulePath.justifications : [])
                    .slice(0, 3)
                    .map((x, i) => (
                      <div key={`why-${i}`}>- {x}</div>
                    ))}
                </div>
                {(Array.isArray(selectedRulePath.guards) ? selectedRulePath.guards : []).length ? (
                  <div style={{ fontSize: 10, color: "var(--silver)" }}>
                    <div style={{ marginBottom: 4, color: "var(--violet)" }}>guards</div>
                    {(selectedRulePath.guards || []).slice(0, 4).map((g, i) => (
                      <div key={`gd-${i}`} style={{ marginBottom: 2 }}>
                        {String(g.node || "")}: {String(g.type || "")} {Array.isArray(g.value) ? `[${g.value.join(", ")}]` : ""}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <div style={{ marginTop: 10, borderTop: "1px solid var(--mist)", paddingTop: 10, fontSize: 11, color: "var(--smoke)" }}>
                当前为 FULL_GRAPH 模式：显示完整图谱。点击任一路径可同时查看 KG 与 FSM 对应。
              </div>
            )}
          </div>
          <div style={{ position: "relative", flex: 1, overflow: "hidden", height: "100%" }}>
            {kgViewMode === "kg" ? (
              <>
                <svg ref={svgRef} id="kg-canvas" style={{ width: "100%", height: "100%" }} />
                <div style={{ position: "absolute", bottom: 12, left: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
                  {selectedRulePath ? (
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 5,
                        fontSize: 10,
                        color: "#00e5a0",
                      }}
                    >
                      <svg width="24" height="10">
                        <line x1="2" y1="5" x2="22" y2="5" stroke="currentColor" strokeWidth="2.8" strokeDasharray="8 4" />
                      </svg>
                      selected_path
                    </div>
                  ) : null}
                  {Object.entries(EDGE_STYLE_KEYS).map(([k, v]) => (
                    <div
                      key={k}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 5,
                        fontSize: 10,
                        color: `var(${v.css})`,
                      }}
                    >
                      <svg width="24" height="10">
                        <line x1="2" y1="5" x2="22" y2="5" stroke="currentColor" strokeWidth={v.w} strokeDasharray={v.dash} />
                      </svg>
                      {k}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div style={{ height: "100%", overflow: "hidden", padding: 14, display: "flex", flexDirection: "column" }}>
                <div style={{ fontSize: 12, color: "var(--silver)", marginBottom: 10 }}>
                  FSM 视图（{selectedRulePath ? "当前路径投影" : "全局状态机"}）
                </div>
                <div style={{ flex: 1, minHeight: 0 }}>
                  <GoalFsmGraph
                    meta={selectedRulePath?.fsm_projection || goalFsmMeta}
                    height="100%"
                    isPathProjection={!!selectedRulePath}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderConflictView = () => {
    return (
      <>
        <div className="fade-up">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 20 }}>
            <div style={{ background: "var(--coral-bg)", border: "1px solid rgba(255,107,107,.25)", borderRadius: 10, padding: 14, textAlign: "center" }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 26, fontWeight: 700, color: "var(--coral)" }}>{conflicts.length}</div>
              <div style={{ fontSize: 10, color: "var(--smoke)", marginTop: 2 }}>冲突检出</div>
            </div>
            <div style={{ background: "var(--amber-bg)", border: "1px solid rgba(255,184,48,.25)", borderRadius: 10, padding: 14, textAlign: "center" }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 26, fontWeight: 700, color: "var(--amber)" }}>
                {conflicts.filter((c) => c.severity === "critical").length}
              </div>
              <div style={{ fontSize: 10, color: "var(--smoke)", marginTop: 2 }}>严重冲突</div>
            </div>
            <div style={{ background: "var(--jade-bg)", border: "1px solid rgba(0,229,160,.25)", borderRadius: 10, padding: 14, textAlign: "center" }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 26, fontWeight: 700, color: "var(--jade)" }}>{repairs.length}</div>
              <div style={{ fontSize: 10, color: "var(--smoke)", marginTop: 2 }}>修复建议</div>
            </div>
            <div style={{ background: "var(--jade-bg)", border: "1px solid rgba(0,229,160,.25)", borderRadius: 10, padding: 14, textAlign: "center" }}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 26, fontWeight: 700, color: "var(--jade)" }}>✓</div>
              <div style={{ fontSize: 10, color: "var(--smoke)", marginTop: 2 }}>可继续迭代</div>
            </div>
          </div>
        </div>

        {(conflicts || []).map((c, idx) => {
          const sev = (c.severity || "warning").toLowerCase();
          const isInfo = sev === "info";
          const isWarn = sev === "warning";
          const bColor = isInfo
            ? "rgba(91,63,160,.35)"
            : isWarn
              ? "rgba(255,184,48,.3)"
              : "rgba(255,107,107,.3)";
          const tColor = isInfo ? "var(--violet)" : isWarn ? "var(--amber)" : "var(--coral)";
          return (
            <div
              key={idx}
              className="conf-item fade-up"
              style={{
                borderColor: bColor,
                background: isInfo
                  ? "rgba(91,63,160,.06)"
                  : isWarn
                    ? "rgba(255,184,48,.04)"
                    : "rgba(255,107,107,.04)",
                animationDelay: `${idx * 0.1}s`,
              }}
              onClick={() => {
                const nid = (c.ids || [])[0];
                const n = nodes.find((x) => x.id === nid);
                if (n) selectNode(n);
              }}
            >
              <div className="ci-head">
                <span
                  className="ci-badge"
                  style={{
                    background: isInfo
                      ? "rgba(91,63,160,.12)"
                      : isWarn
                        ? "rgba(255,184,48,.12)"
                        : "rgba(255,107,107,.12)",
                    border: `1px solid ${bColor}`,
                    color: tColor,
                  }}
                >
                  {isInfo ? "INFO" : isWarn ? "WARNING" : "CRITICAL"}
                </span>
                <span className="ci-ids" style={{ color: tColor }}>
                  [{(c.ids || []).join("] × [")}]
                </span>
              </div>
              <div className="ci-type" style={{ color: tColor, marginBottom: 7 }}>
                {c.type}
              </div>
              <div className="ci-desc">{c.desc}</div>
              {c.fix ? <div className="ci-fix">🔧 修复方案: {c.fix}</div> : null}
            </div>
          );
        })}
      </>
    );
  };

  const renderCasesView = () => {
    // Per requirement: do not expose test cases in this phase.
    return (
      <div className="card fade-up">
        <div className="card-head">
          <span className="card-icon">🧪</span>
          <span className="card-title">测试用例</span>
        </div>
        <div className="card-body">
          <div className="detail-empty">
            <div className="de-icon">◈</div>
            <div className="de-text">当前阶段已禁用用例生成（Layer1 先聚焦解析与图谱）。</div>
          </div>
        </div>
      </div>
    );
  };

  const detailPanel = () => {
    if (!selectedNode) {
      return (
        <div className="detail-empty">
          <div className="de-icon">◈</div>
          <div className="de-text">
            点击任意节点或冲突
            <br />
            查看完整解析详情
          </div>
        </div>
      );
    }

    const s = NODE_STYLES[selectedNode.type] || NODE_STYLES.dial;
    const meta = computeConstraintMeta(selectedNode);
    const outEdges = edges.filter((e) => e.from === selectedNode.id);
    const inEdges = edges.filter((e) => e.to === selectedNode.id);
    const myConflicts = conflicts.filter((cc) => (cc.ids || []).includes(selectedNode.id));

    return (
      <>
        <div className="detail-header">
          <div className="dh-icon" style={{ color: s.text }}>
            {selectedNode.type === "role"
              ? "👤"
              : selectedNode.type === "flow"
                ? "🔀"
                : selectedNode.type === "know"
                  ? "📚"
                  : selectedNode.type === "boun"
                    ? "🚧"
                    : selectedNode.type === "var"
                      ? "📦"
                      : "💬"}
          </div>
          <div>
            <div className="dh-title" style={{ color: s.text }}>
              {selectedNode.id}
            </div>
            <div className="dh-sub" style={{ color: "var(--smoke)" }}>
              {selectedNode.type.toUpperCase()}
            </div>
          </div>
        </div>
        <div className="detail-body">
          <div className="di-row">
            <div className="di-label">节点内容</div>
            <div className="di-val">{selectedNode.text}</div>
          </div>
          {meta.detection ? (
            <div className="di-row">
              <div className="di-label">检测规则</div>
              <div className="di-code">{meta.detection}</div>
            </div>
          ) : null}
          {(inEdges.length || outEdges.length) ? (
            <div className="di-row">
              <div className="di-label">关联边</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11 }}>
                {inEdges.map((e, i) => (
                  <div key={`in-${i}`} style={{ padding: "6px 8px", background: "var(--ink3)", border: "1px solid var(--mist)", borderRadius: 6 }}>
                    ← {e.from} <span style={{ color: "var(--smoke)" }}>({e.label || e.type})</span>
                  </div>
                ))}
                {outEdges.map((e, i) => (
                  <div key={`out-${i}`} style={{ padding: "6px 8px", background: "var(--ink3)", border: "1px solid var(--mist)", borderRadius: 6 }}>
                    → {e.to} <span style={{ color: "var(--smoke)" }}>({e.label || e.type})</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {myConflicts.map((c, i) => (
            <div key={i} className="kg-conflict-warn">
              <strong>{c.type}</strong>
              <p>{c.desc}</p>
              {c.fix ? <div className="fix">修复: {c.fix}</div> : null}
            </div>
          ))}
        </div>
      </>
    );
  };

  const pipelineStatus = useMemo(() => {
    const haveParsed = !!parsed;
    const haveKg = nodes.length > 0;
    const haveWarn = conflicts.length > 0;
    const haveRep = repairs.length > 0;
    return {
      doneParsed: haveParsed,
      doneKg: haveKg,
      warn: haveWarn,
      doneRep: haveRep,
    };
  }, [parsed, nodes.length, conflicts.length, repairs.length]);

  return (
    <>
      <div className="topbar">
        <div className="tb-badge">
          <span>{currentView === "pipeline_layer2" ? "Pipeline + Layer 2" : "Layer 1"}</span>
        </div>
        <div>
          <div className="tb-title">
            {currentView === "pipeline_layer2" ? "Pipeline 与对话模拟层" : "场景构建层"}
          </div>
          <div className="tb-sub">
            {currentView === "pipeline_layer2"
              ? "Persona 选择 · 规则矩阵 · Layer2 可视化"
              : "指令解析 · 规则图谱 · 冲突检测 · 用例生成"}
          </div>
        </div>
        <div className="tb-nav">
          <button className={`tn ${currentView === "parse" ? "act" : ""}`} onClick={() => showView("parse")}>
            指令解析
          </button>
          <button className={`tn ${currentView === "kg" ? "act" : ""}`} onClick={() => showView("kg")}>
            规则图谱
          </button>
          <button className={`tn ${currentView === "pipeline_layer2" ? "act" : ""}`} onClick={() => showView("pipeline_layer2")}>
            Pipeline+Layer2
          </button>
          <button className={`tn ${currentView === "conflict" ? "act" : ""}`} onClick={() => showView("conflict")}>
            冲突检测
          </button>
          <button className={`tn ${currentView === "cases" ? "act" : ""}`} onClick={() => showView("cases")}>
            测试用例
          </button>
        </div>
      </div>

      <div className="main">
        <div className="pipeline">
          <div className="pipe-section-label">构建流程</div>

          <div className={`pipe-step ${pipeIdx === 0 ? "act" : ""}`} onClick={() => goPipe(0)}>
            <div className="pipe-icon" style={{ background: "var(--jade-bg)", borderColor: "rgba(0,229,160,.3)" }}>
              📄
            </div>
            <div className="pipe-step-text">
              <div className="ps-name">预处理</div>
              <div className="ps-sub">段落识别 · 变量提取</div>
            </div>
            <div className={`pipe-status ${pipelineStatus.doneParsed ? "s-done" : "s-wait"}`} />
          </div>
          <div className="pipe-connector" />

          <div className={`pipe-step ${pipeIdx === 1 ? "act" : ""}`} onClick={() => goPipe(1)}>
            <div className="pipe-icon" style={{ background: "var(--sky-bg)", borderColor: "rgba(56,209,248,.3)" }}>
              🤖
            </div>
            <div className="pipe-step-text">
              <div className="ps-name">指令解析 Agent</div>
              <div className="ps-sub">qwen · structured_output</div>
            </div>
            <div className={`pipe-status ${pipelineStatus.doneParsed ? "s-done" : "s-wait"}`} />
          </div>
          <div className="pipe-connector" />

          <div className={`pipe-step ${pipeIdx === 2 ? "act" : ""}`} onClick={() => goPipe(2)}>
            <div className="pipe-icon" style={{ background: "var(--violet-bg)", borderColor: "rgba(178,140,255,.3)" }}>
              🕸️
            </div>
            <div className="pipe-step-text">
              <div className="ps-name">规则图谱构建</div>
              <div className="ps-sub">networkx + 语义边（本轮新增 {semanticEdgeCount}）</div>
            </div>
            <div className={`pipe-status ${pipelineStatus.doneKg ? "s-done" : "s-wait"}`} />
          </div>
          <div className="pipe-connector" />

          <div className={`pipe-step ${pipeIdx === 3 ? "act" : ""}`} onClick={() => goPipe(3)}>
            <div className="pipe-icon" style={{ background: "var(--violet-bg)", borderColor: "rgba(178,140,255,.3)" }}>
              🧩
            </div>
            <div className="pipe-step-text">
              <div className="ps-name">Pipeline 选 Persona</div>
              <div className="ps-sub">规则查表 · 可复现</div>
            </div>
            <div className={`pipe-status ${pipelineStatus.doneParsed ? "s-done" : "s-wait"}`} />
          </div>
          <div className="pipe-connector" />

          <div className={`pipe-step ${pipeIdx === 4 ? "act" : ""}`} onClick={() => goPipe(4)}>
            <div className="pipe-icon" style={{ background: "rgba(0,229,160,.08)", borderColor: "rgba(0,229,160,.3)" }}>
              🎭
            </div>
            <div className="pipe-step-text">
              <div className="ps-name">Layer 2 对话模拟</div>
              <div className="ps-sub">LangGraph · DST 实时检测</div>
            </div>
            <div className={`pipe-status ${pipelineStatus.doneKg ? "s-done" : "s-wait"}`} />
          </div>
          <div className="pipe-connector" />

          <div className={`pipe-step ${pipeIdx === 5 ? "act" : ""}`} onClick={() => goPipe(5)}>
            <div className="pipe-icon" style={{ background: "var(--amber-bg)", borderColor: "rgba(255,184,48,.3)" }}>
              ⚠️
            </div>
            <div className="pipe-step-text">
              <div className="ps-name">冲突检测</div>
              <div className="ps-sub">图算法 + SAT(可选)</div>
            </div>
            <div className={`pipe-status ${pipelineStatus.warn ? "s-warn" : pipelineStatus.doneKg ? "s-done" : "s-wait"}`} />
          </div>

          <div className="pipe-connector" />

          <div className={`pipe-step ${pipeIdx === 6 ? "act" : ""}`} onClick={() => goPipe(6)}>
            <div className="pipe-icon" style={{ background: "var(--coral-bg)", borderColor: "rgba(255,107,107,.3)" }}>
              🔧
            </div>
            <div className="pipe-step-text">
              <div className="ps-name">修复 Agent</div>
              <div className="ps-sub">LLM · 修复建议</div>
            </div>
            <div className={`pipe-status ${pipelineStatus.doneRep ? "s-done" : "s-wait"}`} />
          </div>

          <div className="pipe-connector" />

          <div className={`pipe-step ${pipeIdx === 7 ? "act" : ""}`} onClick={() => goPipe(7)}>
            <div className="pipe-icon" style={{ background: "var(--jade-bg)", borderColor: "rgba(0,229,160,.3)" }}>
              🧪
            </div>
            <div className="pipe-step-text">
              <div className="ps-name">用例生成</div>
              <div className="ps-sub">当前阶段停用</div>
            </div>
            <div className="pipe-status s-wait" />
          </div>

          <div style={{ marginTop: 20, padding: "0 20px" }}>
            <div style={{ background: "var(--ink3)", borderRadius: 8, padding: 12, border: "1px solid var(--mist)" }}>
              <div style={{ fontSize: 9, color: "var(--smoke)", fontFamily: "var(--mono)", marginBottom: 8 }}>产出统计</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 11 }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--silver)" }}>节点</span>
                  <span style={{ color: "var(--jade)", fontFamily: "var(--mono)" }}>{stats.nodeCount}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--silver)" }}>图谱边</span>
                  <span style={{ color: "var(--sky)", fontFamily: "var(--mono)" }}>{stats.edgeCount}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--silver)" }}>冲突检出</span>
                  <span style={{ color: "var(--amber)", fontFamily: "var(--mono)" }}>{stats.conflictCount}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--silver)" }}>已修复</span>
                  <span style={{ color: "var(--jade)", fontFamily: "var(--mono)" }}>{stats.repairCount}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--silver)" }}>测试用例</span>
                  <span style={{ color: "var(--violet)", fontFamily: "var(--mono)" }}>0</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="content" id="content-area">
          <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
            <button type="button" className="tn act" onClick={onRefreshParse}>
              刷新解析
            </button>
            <button type="button" className="tn" onClick={onBuildScene} disabled={building}>
              {building ? "构建中…" : "构建图谱"}
            </button>
            <div style={{ marginLeft: "auto", fontSize: 11, color: "var(--smoke)", display: "flex", gap: 10, alignItems: "center" }}>
              {parseLoading ? (
                <span style={{ color: "var(--amber)" }}>读取中…</span>
              ) : null}
              {parseSource ? <span>{parseSource}</span> : null}
              <span>
                {datasetName || datasetId || "custom"}{" "}
                {datasetId ? <code style={{ marginLeft: 8 }}>{datasetId}</code> : null}
              </span>
            </div>
          </div>

          {currentView === "parse" ? renderParseView() : null}
          {currentView === "kg" ? renderKGView() : null}
          {currentView === "conflict" ? renderConflictView() : null}
          {currentView === "pipeline_layer2" ? renderPipelineLayer2View() : null}
          {currentView === "cases" ? renderCasesView() : null}
        </div>

        <div className="detail" id="detail-panel">
          {detailPanel()}
        </div>
      </div>

      <div id="tooltip" ref={tooltipRef} onMouseMove={moveTip} />
    </>
  );
}


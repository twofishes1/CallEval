import { useMemo, useState } from "react";
import RuleKGCanvas from "./RuleKGCanvas";
import ParsePreview from "./ParsePreview";
import "../styles-layer1.css";

const VIEWS = [
  { id: "parse", label: "指令解析" },
  { id: "kg", label: "规则图谱" },
  { id: "conflict", label: "冲突检测" },
];

function countByType(constraints) {
  const out = {};
  (constraints || []).forEach((c) => {
    out[c.type] = (out[c.type] || 0) + 1;
  });
  return out;
}

function safeText(s, n = 240) {
  const t = (s || "").trim();
  if (!t) return "—";
  return t.length > n ? t.slice(0, n) + "…" : t;
}

export default function Layer1Studio({
  datasetId,
  datasetName,
  rawInstruction,
  variableValues,
  parsed,
  kgViz,
  semanticEdgesAdded,
  onRefreshParse,
  onBuildScene,
  building,
}) {
  const [view, setView] = useState("parse");
  const [pipeStep, setPipeStep] = useState(0);
  const [selectedId, setSelectedId] = useState(null);

  const counts = useMemo(() => countByType(parsed?.constraints), [parsed]);
  const stats = useMemo(() => {
    const nodeCount = kgViz?.summary?.node_count ?? (kgViz?.nodes || []).length;
    const edgeCount = kgViz?.summary?.edge_count ?? (kgViz?.edges || []).length;
    const conflictCount = kgViz?.summary?.conflict_count ?? (kgViz?.conflicts || []).length;
    const repairCount = kgViz?.summary?.repair_count ?? (kgViz?.repairs || []).length;
    return { nodeCount, edgeCount, conflictCount, repairCount };
  }, [kgViz]);

  const nodeMap = useMemo(() => {
    const m = new Map();
    (kgViz?.nodes || []).forEach((n) => m.set(n.id, n));
    return m;
  }, [kgViz]);

  const selected = useMemo(() => {
    if (!selectedId) return null;
    return nodeMap.get(selectedId) || null;
  }, [selectedId, nodeMap]);

  const pipeline = useMemo(() => {
    const haveParsed = !!parsed;
    const haveKg = !!kgViz?.nodes?.length;
    const haveConf = (kgViz?.conflicts || []).length > 0;
    const haveRep = (kgViz?.repairs || []).length > 0;

    return [
      {
        name: "预处理",
        sub: "段落识别 · 变量提取",
        badge: "Python",
        status: haveParsed ? "done" : "wait",
        icon: "📄",
        onClick: () => {
          setPipeStep(0);
          setView("parse");
        },
      },
      {
        name: "指令解析 Agent",
        sub: "Qwen · structured_output",
        badge: "LLM",
        status: haveParsed ? "done" : "wait",
        icon: "🤖",
        onClick: () => {
          setPipeStep(1);
          setView("parse");
        },
      },
      {
        name: "图谱构建 Step 1",
        sub: "networkx · 确定性建图",
        badge: "Python",
        status: haveKg ? "done" : "wait",
        icon: "🕸️",
        onClick: () => {
          setPipeStep(2);
          setView("kg");
        },
      },
      {
        name: "图谱构建 Step 2",
        sub: "Qwen · 语义边推断",
        badge: "LLM",
        status:
          haveKg && (semanticEdgesAdded?.length || 0) > 0
            ? "done"
            : haveKg
              ? "wait"
              : "wait",
        icon: "🔗",
        onClick: () => {
          setPipeStep(3);
          setView("kg");
        },
      },
      {
        name: "冲突检测",
        sub: "networkx · 算法检测",
        badge: "Python",
        status: haveKg ? (haveConf ? "warn" : "done") : "wait",
        icon: "⚠️",
        onClick: () => {
          setPipeStep(4);
          setView("conflict");
        },
      },
      {
        name: "修复 Agent",
        sub: "Qwen · 修复建议",
        badge: "LLM",
        status: haveKg ? (haveRep ? "done" : haveConf ? "wait" : "done") : "wait",
        icon: "🔧",
        onClick: () => {
          setPipeStep(5);
          setView("conflict");
        },
      },
    ];
  }, [parsed, kgViz, semanticEdgesAdded]);

  return (
    <div className="l1">
      <div className="l1-topbar">
        <div className="l1-badge">
          <span>Layer 1</span>
        </div>
        <div className="l1-toptext">
          <div className="l1-title">场景构建层</div>
          <div className="l1-sub">
            指令解析 · 规则图谱 · 冲突检测 · 修复建议（用例生成暂不启用）
          </div>
        </div>
        <div className="l1-tabs">
          {VIEWS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`l1-tab ${view === t.id ? "act" : ""}`}
              onClick={() => setView(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="l1-main">
        <aside className="l1-pipeline">
          <div className="l1-pipe-label">构建流程</div>
          <div className="l1-pipe-list">
            {pipeline.map((p, idx) => (
              <div key={p.name}>
                <button
                  type="button"
                  className={`l1-pipe-step ${pipeStep === idx ? "act" : ""}`}
                  onClick={p.onClick}
                >
                  <div className={`l1-pipe-ico k-${p.badge?.toLowerCase() || "py"}`}>
                    {p.icon}
                  </div>
                  <div className="l1-pipe-text">
                    <div className="l1-ps-name">{p.name}</div>
                    <div className="l1-ps-sub">{p.sub}</div>
                  </div>
                  <span className={`l1-status s-${p.status}`} />
                </button>
                {idx < pipeline.length - 1 ? <div className="l1-pipe-conn" /> : null}
              </div>
            ))}
          </div>

          <div className="l1-summary">
            <div className="l1-sum-title">产出统计</div>
            <div className="l1-sum-rows">
              <div className="l1-sum-row">
                <span>节点</span>
                <strong>{stats.nodeCount}</strong>
              </div>
              <div className="l1-sum-row">
                <span>图谱边</span>
                <strong>{stats.edgeCount}</strong>
              </div>
              <div className="l1-sum-row">
                <span>冲突检出</span>
                <strong>{stats.conflictCount}</strong>
              </div>
              <div className="l1-sum-row">
                <span>修复建议</span>
                <strong>{stats.repairCount}</strong>
              </div>
            </div>
          </div>
        </aside>

        <section className="l1-content">
          <div className="l1-actions">
            <div className="l1-ds">
              <div className="l1-ds-title">
                {datasetName || datasetId || "自定义指令"}
              </div>
              <div className="l1-ds-sub">
                {datasetId ? <code>{datasetId}</code> : null}
                {semanticEdgesAdded != null ? (
                  <span className="l1-dot">
                    语义边新增 <strong>{semanticEdgesAdded.length}</strong>
                  </span>
                ) : null}
              </div>
            </div>

            <div className="l1-action-btns">
              <button
                type="button"
                className="l1-btn"
                onClick={onRefreshParse}
                disabled={!onRefreshParse}
                title="重新调用 /api/instructions/parse"
              >
                刷新解析
              </button>
              <button
                type="button"
                className="l1-btn primary"
                onClick={onBuildScene}
                disabled={building}
                title="调用 /api/datasets/{id}/build-scene 或 /api/instructions/build-scene"
              >
                {building ? "构建中…" : "构建图谱"}
              </button>
            </div>
          </div>

          {view === "parse" ? (
            <div className="l1-pane">
              <div className="l1-card">
                <div className="l1-card-h">
                  <span>原始指令</span>
                  <span className="l1-chip">
                    变量 {Object.keys(variableValues || {}).length} · Flow{" "}
                    {parsed?.flow_steps?.length || 0} · FAQ{" "}
                    {parsed?.faq_items?.length || 0}
                  </span>
                </div>
                <pre className="l1-raw">{safeText(rawInstruction, 1800)}</pre>
              </div>

              <div className="l1-card">
                <div className="l1-card-h">
                  <span>结构化产物：ParsedInstruction</span>
                  <span className="l1-chip mono">
                    R {counts.ROLE || 0} · F {counts.FLOW || 0} · K{" "}
                    {counts.KNOWLEDGE || 0} · D {counts.DIALOGUE || 0} · B{" "}
                    {counts.BOUNDARY || 0}
                  </span>
                </div>
                <div className="l1-parse-embed">
                  <ParsePreview
                    parsed={parsed}
                    loading={false}
                    onRefresh={onRefreshParse}
                    checklist={null}
                  />
                </div>
              </div>
            </div>
          ) : null}

          {view === "kg" ? (
            <div className="l1-pane">
              <div className="l1-card">
                <div className="l1-card-h">
                  <span>Rule KG（交互式）</span>
                  <span className="l1-chip">
                    点击节点可在右侧查看“Layer1 架构分区”详情
                  </span>
                </div>
                <div
                  className="l1-kg"
                  onClickCapture={(e) => {
                    const t = e?.target;
                    const gid = t?.closest?.("g")?.getAttribute?.("data-id");
                    if (gid) setSelectedId(gid);
                  }}
                >
                  <RuleKGCanvas kgViz={kgViz} />
                </div>
              </div>
            </div>
          ) : null}

          {view === "conflict" ? (
            <div className="l1-pane">
              <div className="l1-card">
                <div className="l1-card-h">
                  <span>冲突检测与修复建议</span>
                  <span className="l1-chip">
                    冲突 {(kgViz?.conflicts || []).length} · 修复{" "}
                    {(kgViz?.repairs || []).length}
                  </span>
                </div>
                <div className="l1-conf-wrap">
                  {(kgViz?.conflicts || []).length === 0 ? (
                    <div className="l1-empty">当前未检测到冲突。</div>
                  ) : (
                    <div className="l1-conf-list">
                      {(kgViz?.conflicts || []).map((c, i) => (
                        <button
                          key={i}
                          type="button"
                          className={`l1-conf-item sev-${c.severity || "info"}`}
                          onClick={() => setSelectedId((c.ids || [])[0] || null)}
                        >
                          <div className="l1-conf-ids">
                            {(c.ids || []).map((x) => (
                              <code key={x}>{x}</code>
                            ))}
                          </div>
                          <div className="l1-conf-desc">{c.desc}</div>
                          {c.fix ? <div className="l1-conf-fix">{c.fix}</div> : null}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </section>

        <aside className="l1-detail">
          <div className="l1-detail-h">
            <div>
              <div className="l1-detail-title">架构详情（Layer 1）</div>
              <div className="l1-detail-sub">
                右侧按产物分区：ParsedInstruction / Rule KG / Conflicts / Repairs
              </div>
            </div>
            <div className="l1-detail-mini">
              <span className="pill">R {counts.ROLE || 0}</span>
              <span className="pill">F {counts.FLOW || 0}</span>
              <span className="pill">K {counts.KNOWLEDGE || 0}</span>
            </div>
          </div>

          <div className="l1-detail-body">
            <div className="l1-detail-sec">
              <div className="l1-sec-t">输入</div>
              <div className="l1-kv">
                <div className="k">dataset</div>
                <div className="v">{datasetId || "custom"}</div>
              </div>
              <div className="l1-kv">
                <div className="k">variables</div>
                <div className="v mono">{Object.keys(variableValues || {}).join(", ") || "—"}</div>
              </div>
            </div>

            <div className="l1-detail-sec">
              <div className="l1-sec-t">产物一：ParsedInstruction</div>
              <div className="l1-kv">
                <div className="k">role</div>
                <div className="v">{safeText(parsed?.role_description, 90)}</div>
              </div>
              <div className="l1-kv">
                <div className="k">task</div>
                <div className="v">{safeText(parsed?.task_description, 110)}</div>
              </div>
              <div className="l1-kv">
                <div className="k">flow</div>
                <div className="v">{parsed?.flow_steps?.length || 0} steps</div>
              </div>
              <div className="l1-kv">
                <div className="k">faq</div>
                <div className="v">{parsed?.faq_items?.length || 0} items</div>
              </div>
            </div>

            <div className="l1-detail-sec">
              <div className="l1-sec-t">产物二：Rule KG</div>
              <div className="l1-kv">
                <div className="k">nodes</div>
                <div className="v">{stats.nodeCount}</div>
              </div>
              <div className="l1-kv">
                <div className="k">edges</div>
                <div className="v">{stats.edgeCount}</div>
              </div>
              <div className="l1-kv">
                <div className="k">semantic</div>
                <div className="v">{semanticEdgesAdded?.length ?? 0} added</div>
              </div>
            </div>

            <div className="l1-detail-sec">
              <div className="l1-sec-t">选中节点</div>
              {!selected ? (
                <div className="l1-empty">
                  点击图谱节点或冲突条目，在此查看详情。
                </div>
              ) : (
                <>
                  <div className="l1-node-h">
                    <code>{selected.id}</code>
                    <span className="pill">{selected.type}</span>
                  </div>
                  <div className="l1-node-t">{safeText(selected.text, 520)}</div>
                  {selected.detection ? (
                    <pre className="l1-code">{safeText(selected.detection, 300)}</pre>
                  ) : null}
                  {selected.note ? (
                    <div className="l1-note">{safeText(selected.note, 260)}</div>
                  ) : null}
                </>
              )}
            </div>

            <div className="l1-detail-sec">
              <div className="l1-sec-t">产物三：Conflicts / Repairs</div>
              <div className="l1-kv">
                <div className="k">conflicts</div>
                <div className="v">{stats.conflictCount}</div>
              </div>
              <div className="l1-kv">
                <div className="k">repairs</div>
                <div className="v">{stats.repairCount}</div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}


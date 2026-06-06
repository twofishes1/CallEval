import { useEffect, useMemo, useState } from "react";
import {
  formatViolationDisplay,
  personaBrief,
  personaIcon,
  isPotentialSemanticContradiction,
  personaLabel,
  planGroupDisplayLabel,
  terminationLabel,
  violationsByTurnMap,
} from "../../utils/scoringAnalytics.js";

function PersonaIconMark({ type, className = "" }) {
  return (
    <span className={`persona-icon ${className}`.trim()} aria-hidden="true">
      {personaIcon(type)}
    </span>
  );
}

function PersonaDefinitionBar({ personaType, personaCard }) {
  const brief = personaBrief(personaCard);
  if (!brief) return null;

  return (
    <div className="layer2-persona-def" title={brief.fragment || brief.emotion}>
      <div className="layer2-persona-def-head">
        <span className="layer2-persona-def-label">模拟用户 Persona</span>
        <PersonaIconMark type={brief.type} className="layer2-persona-def-icon" />
        <span className="layer2-persona-def-name">{brief.label}</span>
        {brief.emotion ? <span className="layer2-persona-def-emotion">{brief.emotion}</span> : null}
      </div>
      {brief.patterns.length ? (
        <div className="layer2-persona-def-patterns">
          {brief.patterns.map((p) => (
            <span className="layer2-persona-pattern" key={p}>
              {p}
            </span>
          ))}
        </div>
      ) : null}
      {brief.fragment ? <p className="layer2-persona-def-body">{brief.fragment}</p> : null}
    </div>
  );
}

function PersonaLegend({ personas }) {
  const entries = Object.entries(personas || {});
  if (!entries.length) return null;

  return (
    <details className="layer2-persona-legend">
      <summary>六种模拟用户 Persona 定义</summary>
      <div className="layer2-persona-legend-grid">
        {entries.map(([key, card]) => {
          const brief = personaBrief(card);
          if (!brief) return null;
          return (
            <div className="layer2-persona-legend-item" key={key}>
              <div className="layer2-persona-legend-title">
                <PersonaIconMark type={key} className="layer2-persona-legend-icon" />
                {brief.label}
              </div>
              {brief.emotion ? <div className="layer2-persona-legend-emotion">{brief.emotion}</div> : null}
              {brief.patterns.length ? (
                <div className="layer2-persona-def-patterns compact">
                  {brief.patterns.map((p) => (
                    <span className="layer2-persona-pattern" key={p}>
                      {p}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </details>
  );
}

function PathContextPanel({ pathMeta, record }) {
  const nodes =
    record?.path_nodes ||
    pathMeta?.nodes ||
    [];
  const category =
    record?.path_category_label || pathMeta?.category_label || "";
  const desc = record?.path_description || pathMeta?.description || "";
  const flowDesc = record?.path_flow_description || pathMeta?.flow_description || "";

  if (!nodes.length && !desc && !flowDesc) {
    return (
      <div className="layer2-path-context muted">
        <span className="layer2-path-context-label">测试路径</span>
        <span>{record?.path_id || "—"}（暂无路径节点明细，请重新跑 Layer2 或刷新 Layer1 分析）</span>
      </div>
    );
  }

  return (
    <div className="layer2-path-context">
      <div className="layer2-path-context-head">
        <span className="layer2-path-context-label">测试路径</span>
        {category ? <span className="layer2-path-category">{category}</span> : null}
      </div>
      <div className="layer2-path-seq">{(nodes || []).join(" → ")}</div>
      {desc ? <p className="layer2-path-desc">{desc}</p> : null}
      {flowDesc ? (
        <details className="layer2-path-steps">
          <summary>逐步说明（路径设计）</summary>
          <pre>{flowDesc}</pre>
        </details>
      ) : null}
    </div>
  );
}

function TurnViolationMarks({ violations, pathMeta, flowAdherenceRate }) {
  const list = Array.isArray(violations) ? violations : [];
  if (!list.length) return null;

  const ctx = { pathMeta, flowAdherenceRate };

  return (
    <div className="studio-turn-violations" role="list">
      {list.map((v, i) => {
        const card = formatViolationDisplay(v, ctx);
        return (
          <div className="studio-turn-violation" key={`${v.constraint_id}-${i}`} role="listitem">
            <div className="studio-turn-violation-head">
              <span className="studio-violation-badge">{card.badge}</span>
              <span className="studio-violation-deduction">−{Number(v.deduction || 0).toFixed(1)} 分</span>
            </div>
            <div className="studio-violation-title">{card.title}</div>
            {card.typeLabel ? (
              <div className="studio-violation-type-line">违规类型：{card.typeLabel}</div>
            ) : null}
            {card.idNote ? <div className="studio-violation-id-note">{card.idNote}</div> : null}
            <div className="studio-violation-rule">{card.body}</div>
            {card.expectedPath ? (
              <div className="studio-violation-expected">应对路径：{card.expectedPath}</div>
            ) : null}
            {v.bot_utterance ? (
              <div className="studio-violation-bot">相关 Bot 话术：「{v.bot_utterance}」</div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function DialogueTurn({ m, turnViolations, pathMeta, flowAdherenceRate, personaCard }) {
  const isBot = String(m?.role || "").toLowerCase() === "bot";
  const hasViolation = (turnViolations || []).length > 0;
  const brief = !isBot ? personaBrief(personaCard) : null;

  return (
    <div
      className={`studio-turn ${isBot ? "bot" : "user"}${hasViolation ? " has-violation" : ""}`}
    >
      <div className="studio-turn-line">
        <span className="studio-turn-tag">T{m?.turn}</span>
        <span className="studio-turn-role">{String(m?.role || "").toUpperCase()}</span>
        {!isBot && brief ? (
          <span className="studio-turn-persona" title={brief.fragment || brief.emotion}>
            <PersonaIconMark type={brief.type} className="studio-turn-persona-icon" />
            {brief.label}
          </span>
        ) : null}
        {hasViolation ? <span className="studio-turn-flag">规则违规</span> : null}
        <span className="studio-turn-text">{String(m?.content || "")}</span>
      </div>
      {!isBot && brief?.emotion ? (
        <div className="studio-turn-persona-note">{brief.emotion}</div>
      ) : null}
      <TurnViolationMarks
        violations={turnViolations}
        pathMeta={pathMeta}
        flowAdherenceRate={flowAdherenceRate}
      />
    </div>
  );
}

const BOT_PROVIDER_LABELS = {
  qwen: "Qwen Bot",
  deepseek: "DeepSeek Bot",
};

export default function Layer2View({ data, loading, onRefresh, pathCatalog, botProvider = "qwen", loadError = "" }) {
  const activeBot = data?.bot_provider || botProvider || "qwen";
  const botLabel = BOT_PROVIDER_LABELS[activeBot] || activeBot;
  const reportFile = data?.report_file || "";
  const botModel = data?.summary?.meta?.bot_model || data?.meta?.bot_model || "";
  const layer2 = data?.layer2 || {};
  const personas = layer2?.persona_registry || {};
  const dialogues = Array.isArray(layer2?.dialogues) ? layer2.dialogues : [];
  const reports = data?.reports || [];

  const pathsById = useMemo(() => {
    const m = { ...(layer2?.paths_by_id || {}) };
    (pathCatalog || []).forEach((p) => {
      if (p?.path_id) m[p.path_id] = { ...m[p.path_id], ...p };
    });
    return m;
  }, [layer2?.paths_by_id, pathCatalog]);

  const personaKeys = useMemo(() => Object.keys(personas), [personas]);
  const [personaFocus, setPersonaFocus] = useState("");
  const [pathFocus, setPathFocus] = useState("");
  const [selectedReportId, setSelectedReportId] = useState("");

  const selectedPersona = personaFocus || personaKeys[0] || "";
  const personaDialogues = useMemo(
    () =>
      dialogues.filter(
        (d) => String(d?.persona_type || "").toLowerCase() === selectedPersona.toLowerCase()
      ),
    [dialogues, selectedPersona]
  );
  const pathKeys = useMemo(
    () => [...new Set(personaDialogues.map((d) => d?.path_id).filter(Boolean))].sort(),
    [personaDialogues]
  );
  const selectedPath = pathFocus || pathKeys[0] || "";
  const records = useMemo(() => {
    return personaDialogues.filter(
      (d) => String(d?.path_id || "") === String(selectedPath)
    );
  }, [personaDialogues, selectedPath]);

  const selected =
    records.find((r) => r.report_id === selectedReportId) || records[0] || null;

  const pathMeta = selected?.path_id ? pathsById[selected.path_id] : null;

  const turnViolationMap = useMemo(
    () => violationsByTurnMap(selected?.violations, selected?.messages),
    [selected?.violations, selected?.messages]
  );

  const activePersonaCard = personas[selected?.persona_type] || personas[selectedPersona] || null;

  useEffect(() => {
    setSelectedReportId("");
    setPathFocus("");
  }, [personaFocus]);

  useEffect(() => {
    if (records[0]?.report_id && !selectedReportId) {
      setSelectedReportId(records[0].report_id);
    }
  }, [records, selectedReportId]);

  useEffect(() => {
    if (records.length && !records.some((r) => r.report_id === selectedReportId)) {
      setSelectedReportId(records[0].report_id);
    }
  }, [records, selectedReportId]);

  if (loading) {
    return <div className="studio-loading">Layer2 对话数据加载中…</div>;
  }

  if (!dialogues.length && !reports.length) {
    return (
      <div className="layer-view-empty">
        <p>
          暂无 <strong>{botLabel}</strong> 对话记录
          {reportFile ? `（${reportFile}）` : ""}
        </p>
        {loadError ? <p className="layer2-load-error">{loadError}</p> : null}
        <button type="button" className="btn-ghost" onClick={() => onRefresh?.(true)}>
          重新跑当前 Bot 评测
        </button>
      </div>
    );
  }

  const violationCount = (selected?.violations || []).length;

  return (
    <div className="layer-view layer2-view">
      <div className="layer2-bot-banner">
        <span className={`layer2-bot-badge ${activeBot}`}>{botLabel}</span>
        <span className="layer2-bot-banner-meta">
          用户模拟仍为 Qwen（qwen-plus）· 评委 Qwen
          {botModel ? ` · 被测 Bot 模型 ${botModel}` : ""}
          {reportFile ? ` · 报告 ${reportFile}` : ""}
        </span>
      </div>
      <div className="layer-view-toolbar">
        <span>
          对话 <strong>{dialogues.length}</strong> 条 · 报告 <strong>{reports.length}</strong> 份
        </span>
        <button type="button" className="btn-ghost" onClick={() => onRefresh?.(false)}>
          刷新
        </button>
        <button type="button" className="btn-ghost" onClick={() => onRefresh?.(true)}>
          重新评测
        </button>
      </div>

      <div className="layer2-split">
        <aside className="layer2-nav">
          <div className="layer2-nav-section">
            <div className="layer2-nav-label">Persona</div>
            <div className="chip-row">
              {personaKeys.map((k) => (
                <button
                  key={k}
                  type="button"
                  className={`studio-chip ${selectedPersona === k ? "active" : ""}`}
                  onClick={() => {
                    setPersonaFocus(k);
                    setPathFocus("");
                  }}
                  title={personas[k]?.emotion_description || personaLabel(k)}
                >
                  <PersonaIconMark type={k} className="studio-chip-icon" />
                  {personaLabel(k)}
                </button>
              ))}
            </div>
          </div>
          <div className="layer2-nav-section">
            <div className="layer2-nav-label">路径</div>
            <div className="chip-row">
              {pathKeys.map((pk) => (
                <button
                  key={pk}
                  type="button"
                  className={`studio-chip violet ${selectedPath === pk ? "active" : ""}`}
                  onClick={() => setPathFocus(pk)}
                  title={pathsById[pk]?.category_label || pk}
                >
                  {pk}
                </button>
              ))}
            </div>
          </div>
          <div className="layer2-nav-section layer2-nav-scroll">
            <div className="layer2-nav-label">用例</div>
            {records.map((r) => {
              const vCount = (r.violations || []).length;
              const isControl = isPotentialSemanticContradiction(r.plan_group);
              return (
                <button
                  key={r.report_id}
                  type="button"
                  className={`layer2-case-btn ${selected?.report_id === r.report_id ? "active" : ""}`}
                  onClick={() => setSelectedReportId(r.report_id)}
                  title={r.plan_reason || ""}
                >
                  <span>
                    {r.path_id}
                    {isControl ? (
                      <span className="layer2-plan-badge control">可能矛盾</span>
                    ) : null}
                  </span>
                  <span className="muted">
                    {r.total_score ?? "-"} · {(r.messages || []).length} 轮
                    {vCount > 0 ? ` · 违规${vCount}` : ""}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        <div className="layer2-dialogue">
          {selected ? (
            <>
              <div className="layer2-dialogue-head">
                <strong>
                  {selected.path_id} · {personaLabel(selected.persona_type)}
                  {isPotentialSemanticContradiction(selected.plan_group) ? (
                    <span className="layer2-plan-badge control">
                      {planGroupDisplayLabel(selected.plan_group)}
                    </span>
                  ) : null}
                </strong>
                <span>
                  得分 {selected.total_score ?? "-"} ({selected.grade || "-"}) ·{" "}
                  {terminationLabel(selected.termination_reason)}
                </span>
              </div>

              <PathContextPanel pathMeta={pathMeta} record={selected} />

              <PersonaDefinitionBar
                personaType={selected.persona_type}
                personaCard={activePersonaCard}
              />

              <PersonaLegend personas={personas} />

              {isPotentialSemanticContradiction(selected.plan_group) ? (
                <div className="layer2-control-banner" title={selected.plan_reason || ""}>
                  标注：该路径×角色组合可能存在语义矛盾（
                  {selected.plan_reason?.replace(/^[^:]+:/, "") || "与路径标签不匹配"}）。
                  用户行为仍由路径节点驱动，Persona 主要影响措辞；解读得分时请结合路径设计，勿等同于该角色的典型场景。
                </div>
              ) : null}

              {violationCount > 0 ? (
                <div className="layer2-violation-summary">
                  本用例共 <strong>{violationCount}</strong> 条规则违规，已在下方对话轮次中标注（
                  {[...turnViolationMap.keys()].sort((a, b) => a - b).map((t) => `T${t}`).join("、")}
                  ）
                </div>
              ) : (
                <div className="layer2-violation-summary ok">本用例无规则违规记录</div>
              )}

              <div className="layer2-messages">
                {(selected.messages || []).map((m, i) => {
                  const turn = Number(m?.turn);
                  const turnViols = Number.isFinite(turn) ? turnViolationMap.get(turn) : undefined;
                  return (
                    <DialogueTurn
                      key={`${m.turn}-${i}`}
                      m={m}
                      turnViolations={turnViols}
                      pathMeta={pathMeta}
                      flowAdherenceRate={selected.flow_adherence_rate}
                      personaCard={activePersonaCard}
                    />
                  );
                })}
              </div>
            </>
          ) : (
            <div className="studio-empty">
              {selectedPersona && selectedPath
                ? `暂无 ${personaLabel(selectedPersona)} × ${selectedPath} 对应用例，请重新跑 Layer2 或换选路径/Persona。`
                : "选择左侧 Persona 与路径查看对应用例"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

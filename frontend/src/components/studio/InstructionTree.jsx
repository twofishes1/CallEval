import { useMemo } from "react";

const TYPE_LABELS = {
  role: "角色",
  flow: "流程",
  knowledge: "知识",
  dialogue: "话术",
  boundary: "边界",
};

const TYPE_CHIP = {
  role: "role",
  flow: "flow",
  knowledge: "know",
  dialogue: "dial",
  boundary: "boun",
};

function groupConstraints(constraints) {
  const groups = {
    role: [],
    flow: [],
    knowledge: [],
    dialogue: [],
    boundary: [],
    other: [],
  };
  for (const c of constraints || []) {
    const t = String(c?.type || c?.constraint_type || "other").toLowerCase();
    if (groups[t]) groups[t].push(c);
    else groups.other.push(c);
  }
  return groups;
}

function Section({ title, chip, chipClass, count, defaultOpen, children }) {
  return (
    <details className="inst-section" open={defaultOpen}>
      <summary>
        <span>{title}</span>
        {chip ? <span className={`inst-chip ${chipClass || ""}`}>{chip}</span> : null}
        {count != null ? (
          <span className="inst-chip soft" style={{ marginLeft: 4 }}>
            {count}
          </span>
        ) : null}
      </summary>
      <div className="inst-section-body">{children}</div>
    </details>
  );
}

export default function InstructionTree({ parsed, variableValues, rawInstruction }) {
  const groups = useMemo(
    () => groupConstraints(parsed?.constraints || []),
    [parsed?.constraints]
  );

  const flowSteps = parsed?.flow_steps || [];
  const branchesByStep = parsed?.flow_branches_by_step || {};
  const faqItems = parsed?.faq_items || [];
  const knowledgeNodes = parsed?.knowledge_nodes || [];
  const vars = Object.entries(variableValues || {});

  if (!parsed && !rawInstruction) {
    return <div className="studio-empty">选择数据集后显示解析项</div>;
  }

  return (
    <>
      {parsed?.role_description ? (
        <Section title="角色 Role" chip="R" chipClass="role" defaultOpen>
          <div className="inst-item">
            <div className="inst-item-text">{parsed.role_description}</div>
          </div>
        </Section>
      ) : null}

      {parsed?.task_description ? (
        <Section title="任务 Task" defaultOpen>
          <div className="inst-item">
            <div className="inst-item-text">{parsed.task_description}</div>
          </div>
        </Section>
      ) : null}

      {parsed?.opening_line ? (
        <Section title="开场 Opening" defaultOpen>
          <div className="inst-item">
            <div className="inst-item-text">{parsed.opening_line}</div>
            <div className="inst-item-meta">首句可超过 30 字限制</div>
          </div>
        </Section>
      ) : null}

      {flowSteps.length > 0 ? (
        <Section
          title="流程 Call Flow"
          chip={`${flowSteps.length} 步`}
          chipClass="flow"
          defaultOpen
        >
          {flowSteps.map((step, i) => {
            const stepNo = String(i + 1);
            const branches = branchesByStep[stepNo] || [];
            return (
              <div className="inst-item" key={`f-${i}`}>
                <div className="inst-item-id">F{i + 1}</div>
                <div className="inst-item-text">{step}</div>
                {branches.length > 0 ? (
                  <ul className="inst-branch-list">
                    {branches.map((b) => (
                      <li className="inst-branch-item" key={b.branch_id || `${stepNo}-${b.branch_index}`}>
                        <div className="inst-branch-head">
                          <span className="inst-chip flow inst-branch-chip">分支 {b.branch_index}</span>
                          {b.section ? (
                            <span className="inst-item-meta inst-branch-section">{b.section}</span>
                          ) : null}
                        </div>
                        <div className="inst-item-text inst-branch-line">
                          若 {b.condition} → {b.action}
                        </div>
                        {b.op_steps?.length ? (
                          <ol className="inst-op-list">
                            {b.op_steps.map((op, j) => (
                              <li key={`${b.branch_id}-op-${j}`}>{op}</li>
                            ))}
                          </ol>
                        ) : null}
                        {b.target_step ? (
                          <div className="inst-item-meta">跳转至 F{b.target_step}</div>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            );
          })}
        </Section>
      ) : null}

      {Object.entries(groups).map(([type, items]) => {
        if (!items.length || type === "other") return null;
        return (
          <Section
            key={type}
            title={`约束 ${TYPE_LABELS[type] || type}`}
            chip={String(items.length)}
            chipClass={TYPE_CHIP[type] || "soft"}
          >
            {items.map((c) => (
              <div className="inst-item" key={c.id || c.text}>
                <div className="inst-item-id">
                  {c.id || "—"}
                  {c.is_hard != null && (
                    <span
                      className={`inst-chip ${c.is_hard ? "hard" : "soft"}`}
                      style={{ marginLeft: 6 }}
                    >
                      {c.is_hard ? "硬约束" : "软约束"}
                    </span>
                  )}
                </div>
                <div className="inst-item-text">{c.text}</div>
                {c.detection_method ? (
                  <div className="inst-item-meta">检测: {c.detection_method}</div>
                ) : null}
              </div>
            ))}
          </Section>
        );
      })}

      {faqItems.length > 0 ? (
        <Section title="FAQ / 知识库" chip={String(faqItems.length)} chipClass="know">
          {faqItems.slice(0, 24).map((f, i) => (
            <div className="inst-item" key={`faq-${i}`}>
              {f.q ? <div className="inst-item-id">Q: {f.q}</div> : null}
              <div className="inst-item-text">{f.a || f.text || "—"}</div>
              {f.terms ? (
                <div className="inst-item-meta">触发词: {f.terms}</div>
              ) : null}
            </div>
          ))}
          {faqItems.length > 24 ? (
            <div className="inst-item-meta">另有 {faqItems.length - 24} 条未展开</div>
          ) : null}
        </Section>
      ) : null}

      {knowledgeNodes.length > 0 ? (
        <Section title="知识节点" chip={String(knowledgeNodes.length)} chipClass="know">
          {knowledgeNodes.slice(0, 16).map((k, i) => (
            <div className="inst-item" key={k.id || i}>
              <div className="inst-item-id">{k.id || `K${i + 1}`}</div>
              <div className="inst-item-text">{k.text || k.content || "—"}</div>
            </div>
          ))}
        </Section>
      ) : null}

      {vars.length > 0 ? (
        <Section title="变量" chip={String(vars.length)} chipClass="role">
          {vars.map(([k, v]) => (
            <div className="inst-item" key={k}>
              <div className="inst-item-id">{k}</div>
              <div className="inst-item-text">{v}</div>
            </div>
          ))}
        </Section>
      ) : null}

      {!parsed?.flow_steps?.length && (rawInstruction || parsed?.raw_text) ? (
        <Section title="原始指令" defaultOpen>
          <div className="inst-item">
            <div
              className="inst-item-text"
              style={{ maxHeight: 200, overflowY: "auto", fontSize: 11 }}
            >
              {rawInstruction || parsed.raw_text}
            </div>
          </div>
        </Section>
      ) : null}
    </>
  );
}

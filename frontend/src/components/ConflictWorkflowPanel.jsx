import { useState } from "react";

const PERSONAS = {
  cooperative: { label: "配合型", color: "#22d37f", emoji: "😊" },
  resistant: { label: "抵触型", color: "#f87171", emoji: "😤" },
  ignorant: { label: "无知型", color: "#38bdf8", emoji: "🤔" },
  impatient: { label: "急躁型", color: "#fbbf24", emoji: "⚡" },
  off_topic: { label: "偏题型", color: "#a78bfa", emoji: "🌀" },
};

export default function ConflictWorkflowPanel({ kgViz }) {
  const [page, setPage] = useState(0);
  const [tcFilter, setTcFilter] = useState("all");
  const [selectedTc, setSelectedTc] = useState(null);

  if (!kgViz) {
    return (
      <div className="workflow-empty">
        构建规则图谱后显示冲突修复与测试用例工作流
      </div>
    );
  }

  const conflicts = kgViz.conflicts || [];
  const repairs = kgViz.repairs || [];
  const testCases = kgViz.test_cases || [];
  const scoreRules = kgViz.score_rules || [];

  const filteredTc = testCases.filter((tc) => {
    if (tcFilter === "all") return true;
    if (tcFilter === "conflict") return tc.conflict_cover;
    return tc.persona === tcFilter;
  });

  const severe = conflicts.filter((c) => c.severity === "SEVERE").length;

  return (
    <div className="workflow-panel">
      <div className="workflow-tabs">
        {["① 冲突检测", "② 修复方案", "③ 测试用例", "④ 评分映射"].map(
          (label, i) => (
            <button
              key={label}
              type="button"
              className={`wf-tab ${page === i ? "active" : ""}`}
              onClick={() => setPage(i)}
            >
              {label}
            </button>
          )
        )}
      </div>

      {page === 0 && (
        <div className="wf-page">
          <div className="wf-summary">
            <div className="sum-card">
              <div className="sum-num orange">{conflicts.length}</div>
              <div>冲突总数</div>
            </div>
            <div className="sum-card">
              <div className="sum-num red">{severe}</div>
              <div>严重冲突</div>
            </div>
            <div className="sum-card">
              <div className="sum-num green">{kgViz.summary?.node_count || 0}</div>
              <div>图谱节点</div>
            </div>
            <div className="sum-card">
              <div className="sum-num blue">{testCases.length}</div>
              <div>测试用例</div>
            </div>
          </div>
          {conflicts.map((c, i) => (
            <div key={i} className="conf-card">
              <div className="conf-head">
                <span className={`conf-badge ${c.severity === "SEVERE" ? "severe" : "tension"}`}>
                  {c.severity || "WARN"}
                </span>
                <div>
                  <div className="conf-ids">[{c.ids?.join("] × [")}]</div>
                  <div className="conf-type">{c.type}</div>
                  <div className="conf-desc">{c.desc}</div>
                </div>
              </div>
              {c.fix && (
                <div className="conf-fix">修复方案: {c.fix}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {page === 1 && (
        <div className="wf-page">
          {repairs.length > 0 ? (
            repairs.map((r, i) => (
              <div key={i} className="fix-card">
                <strong>{r.modified_constraint_id}</strong>
                <p>{r.modified_text}</p>
                <small>{r.rationale}</small>
              </div>
            ))
          ) : (
            conflicts.map((c, i) => (
              <div key={i} className="fix-card green">
                <div className="conf-ids">[{c.ids?.join("] × [")}]</div>
                <p>{c.fix || "（待 LLM 构建时生成修复建议）"}</p>
              </div>
            ))
          )}
        </div>
      )}

      {page === 2 && (
        <div className="wf-page">
          <div className="tc-filters">
            {[
              ["all", `全部 (${testCases.length})`],
              ["cooperative", "😊 配合型"],
              ["resistant", "😤 抵触型"],
              ["ignorant", "🤔 无知型"],
              ["conflict", "⚠ 冲突覆盖"],
            ].map(([f, label]) => (
              <button
                key={f}
                type="button"
                className={`wf-flt ${tcFilter === f ? "active" : ""}`}
                onClick={() => {
                  setTcFilter(f);
                  setSelectedTc(null);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="tc-grid">
            {filteredTc.map((tc) => {
              const p = PERSONAS[tc.persona] || PERSONAS.cooperative;
              return (
                <div
                  key={tc.id}
                  className={`tc-card ${selectedTc?.id === tc.id ? "selected" : ""}`}
                  onClick={() => setSelectedTc(tc)}
                >
                  <div className="tc-top">
                    <span className="tc-id">{tc.id}</span>
                    <span style={{ color: p.color }}>
                      {p.emoji} {p.label}
                    </span>
                  </div>
                  <div className="tc-title">{tc.title}</div>
                  <div className="tc-chips">
                    {(tc.focus || []).slice(0, 5).map((f) => (
                      <span key={f} className="chip focus">
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
          {selectedTc && (
            <div className="tc-detail show">
              <h4>
                {selectedTc.id} · {selectedTc.title}
              </h4>
              <p>{selectedTc.desc}</p>
              <div className="tc-chips">
                {(selectedTc.focus || []).map((f) => (
                  <span key={f} className="chip focus">
                    {f}
                  </span>
                ))}
              </div>
              {selectedTc.fsm_path?.length > 0 && (
                <div className="fsm-path">
                  {selectedTc.fsm_path.join(" → ")}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {page === 3 && (
        <div className="wf-page">
          <table className="score-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>内容</th>
                <th>检测</th>
                <th>维度</th>
                <th>扣分</th>
              </tr>
            </thead>
            <tbody>
              {scoreRules.map((r) => (
                <tr key={r.id}>
                  <td className={r.hard ? "hard" : ""}>{r.id}</td>
                  <td>
                    {r.text}
                    {r.note && <div className="note">{r.note}</div>}
                  </td>
                  <td>
                    <span className={`method ${r.method}`}>{r.method}</span>
                  </td>
                  <td>{r.dim}</td>
                  <td>-{r.deduct}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

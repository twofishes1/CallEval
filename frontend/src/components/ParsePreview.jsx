/** Layer1 解析预览 — 对照设计文档六类节点 */

const TYPE_LABELS = {
  ROLE: "角色 R*",
  FLOW: "流程 F*",
  KNOWLEDGE: "知识 K*",
  DIALOGUE: "话术 D*",
  BOUNDARY: "边界 B*",
};

export default function ParsePreview({ parsed, loading, onRefresh, checklist }) {
  if (loading) {
    return <div className="parse-preview loading">解析中…</div>;
  }
  if (!parsed) {
    return (
      <div className="parse-preview empty">
        <p>选择左侧数据集后自动解析，或点击「刷新解析预览」。</p>
        {onRefresh && (
          <button type="button" className="ghost-btn" onClick={onRefresh}>
            刷新解析预览
          </button>
        )}
      </div>
    );
  }

  const byType = {};
  (parsed.constraints || []).forEach((c) => {
    byType[c.type] = byType[c.type] || [];
    byType[c.type].push(c);
  });

  return (
    <div className="parse-preview">
      <div className="parse-preview-header">
        <h3>Layer1 解析预览（对照设计文档 §3.1）</h3>
        {onRefresh && (
          <button type="button" className="ghost-btn" onClick={onRefresh}>
            刷新解析预览
          </button>
        )}
      </div>

      {checklist && (
        <div className="design-checklist">
          {checklist.map((row) => (
            <span
              key={row.label}
              className={`check-chip ${row.ok ? "ok" : "warn"}`}
              title={row.detail}
            >
              {row.ok ? "✓" : "△"} {row.label}
            </span>
          ))}
        </div>
      )}

      <div className="six-type-grid">
        {Object.entries(TYPE_LABELS).map(([type, label]) => (
          <div key={type} className="type-card">
            <strong>{label}</strong>
            <span className="type-count">{(byType[type] || []).length}</span>
          </div>
        ))}
        <div className="type-card">
          <strong>变量 VAR_*</strong>
          <span className="type-count">
            {Object.keys(parsed.variables || {}).length}
          </span>
        </div>
        <div className="type-card">
          <strong>FAQ 节点</strong>
          <span className="type-count">{(parsed.faq_items || []).length}</span>
        </div>
      </div>

      <div className="parse-meta">
        <p>
          <strong>Role：</strong>
          {parsed.role_description || "—"}
        </p>
        <p>
          <strong>Task：</strong>
          {parsed.task_description || "—"}
        </p>
        <p>
          <strong>Opening：</strong>
          {(parsed.opening_line || "").slice(0, 120)}
          {(parsed.opening_line || "").length > 120 ? "…" : ""}
        </p>
      </div>

      <details open>
        <summary>Call Flow → flow_0…n（对应 F1…Fn）</summary>
        <ol className="parse-list">
          {(parsed.flow_steps || []).map((s, i) => (
            <li key={i}>
              <code>flow_{i}</code> / <code>F{i + 1}</code> {s}
            </li>
          ))}
        </ol>
      </details>

      <details>
        <summary>FAQ → faq_* 与 K* 约束（{(parsed.faq_items || []).length} 条）</summary>
        <table className="constraints-table compact">
          <thead>
            <tr>
              <th>#</th>
              <th>问 (q)</th>
              <th>答 (a)</th>
            </tr>
          </thead>
          <tbody>
            {(parsed.faq_items || []).slice(0, 12).map((it, i) => (
              <tr key={i}>
                <td>
                  faq_{i} / K{i + 1}
                </td>
                <td>{(it.q || "").slice(0, 80)}</td>
                <td>{(it.a || "").slice(0, 100)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <details open>
        <summary>约束六类表（{(parsed.constraints || []).length} 条）</summary>
        <div className="constraints-table-wrap">
          <table className="constraints-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>类型</th>
                <th>P</th>
                <th>硬</th>
                <th>可测</th>
                <th>检测规则</th>
                <th>文本</th>
              </tr>
            </thead>
            <tbody>
              {(parsed.constraints || []).map((c) => (
                <tr key={c.id}>
                  <td>
                    <code>{c.id}</code>
                  </td>
                  <td>{c.type}</td>
                  <td>{c.priority}</td>
                  <td>{c.is_hard ? "是" : "否"}</td>
                  <td>{c.measurable ? "是" : "否"}</td>
                  <td className="rule-cell">
                    {(c.detection_rule || "—").slice(0, 48)}
                  </td>
                  <td>{c.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <details>
        <summary>变量 VAR_*</summary>
        <ul className="var-list">
          {Object.entries(parsed.variables || {}).map(([k, v]) => (
            <li key={k}>
              <code>VAR_{k}</code> = {v}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

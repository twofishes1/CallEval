/** 规则违规列表 — 用于每个用例展示具体违反的规则 */

import { formatViolationDisplay } from "../utils/scoringAnalytics.js";

function violationKey(v, i) {
  return `${v?.constraint_id || v?.constraint_ref || "v"}-${v?.turn_index ?? i}-${i}`;
}

/** 单行摘要，用于用例列表 */
export function ViolationSummary({ violations }) {
  const list = Array.isArray(violations) ? violations : [];
  if (!list.length) return null;

  const uniqueRules = [];
  const seen = new Set();
  list.forEach((v) => {
    const card = formatViolationDisplay(v, {});
    const key = `${v?.constraint_id}-${v?.violation_type}`;
    if (seen.has(key)) return;
    seen.add(key);
    uniqueRules.push({ id: v?.constraint_id, title: card.title });
  });

  return (
    <div
      style={{
        marginTop: 4,
        fontSize: 11,
        color: "var(--ember)",
        lineHeight: 1.45,
      }}
    >
      <span style={{ fontWeight: 600 }}>规则违规 {list.length} 条</span>
      {uniqueRules.map((r) => (
        <div key={r.id} style={{ color: "var(--silver)", marginTop: 2 }}>
          · {r.title}
        </div>
      ))}
    </div>
  );
}

/** 完整违规证据链，用于用例详情 */
export function ViolationList({
  violations,
  title = "规则违规",
  pathMeta = null,
  flowAdherenceRate = null,
}) {
  const list = Array.isArray(violations) ? violations : [];
  const ctx = { pathMeta, flowAdherenceRate };

  if (!list.length) {
    return (
      <div>
        <h5>{title}</h5>
        <p className="muted" style={{ fontSize: 12 }}>
          无规则违规
        </p>
      </div>
    );
  }

  const totalDeduction = list.reduce((s, v) => s + Number(v?.deduction || 0), 0);

  return (
    <div>
      <h5>
        {title}（{list.length} 条，合计 −{totalDeduction.toFixed(1)} 分）
      </h5>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {list.map((v, i) => {
          const card = formatViolationDisplay(v, ctx);
          return (
            <div className="violation violation-card-rich" key={violationKey(v, i)}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: "#b45309",
                    background: "#fff7ed",
                    padding: "2px 6px",
                    borderRadius: 4,
                  }}
                >
                  {card.badge}
                </span>
                {v.turn_index != null ? (
                  <span style={{ fontSize: 11, color: "var(--smoke)" }}>轮次 T{v.turn_index}</span>
                ) : null}
              </div>
              <strong style={{ display: "block", marginTop: 6, fontSize: 13 }}>{card.title}</strong>
              {card.typeLabel ? (
                <div style={{ fontSize: 11, marginTop: 4, color: "var(--smoke)" }}>
                  违规类型：{card.typeLabel}
                </div>
              ) : null}
              {card.idNote ? (
                <div style={{ fontSize: 11, marginTop: 4, color: "#64748b" }}>{card.idNote}</div>
              ) : null}
              <div style={{ fontSize: 12, marginTop: 6, color: "var(--silver)", lineHeight: 1.5 }}>
                {card.body}
              </div>
              {card.expectedPath ? (
                <div style={{ fontSize: 11, marginTop: 4, color: "#047857" }}>
                  应对路径：{card.expectedPath}
                </div>
              ) : null}
              {v.bot_utterance ? (
                <div style={{ fontSize: 12, marginTop: 4, color: "var(--jade)" }}>
                  Bot：「{v.bot_utterance}」
                </div>
              ) : null}
              <div style={{ fontSize: 11, marginTop: 6, color: "var(--ember)" }}>
                扣分 −{Number(v.deduction || 0).toFixed(1)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

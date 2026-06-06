import { dimLabel } from "../../utils/scoringAnalytics.js";

/** Model-level final score summary (shown before per-case drill-down). */
export function ModelFinalScoreHero({ summary, meta, analytics, recalcSummary, useRecalcCoverage }) {
  const avg = summary?.average_score;
  const count = summary?.count ?? 0;
  const grades = summary?.grade_distribution || {};
  const dimAvg = summary?.dimension_averages || {};
  const weightRule = meta?.weight_rule ?? "0.4";
  const weightLlm = meta?.weight_llm ?? "0.6";

  const topDim = Object.entries(dimAvg).sort((a, b) => b[1] - a[1])[0];
  const lowDim = Object.entries(dimAvg).sort((a, b) => a[1] - b[1])[0];

  const ruleDeductionCases = analytics?.casesWithRuleDeduction ?? 0;
  const pathGapCases = analytics?.materialPathGapCases ?? analytics?.pathCoverageGapCases ?? 0;
  const pathGapMinor = Math.max(
    0,
    (analytics?.pathCoverageGapCases ?? 0) - (analytics?.materialPathGapCases ?? 0),
  );
  const runtimeCases = analytics?.runtimeViolationCases ?? 0;
  const totalRecords = analytics?.totalViolations ?? 0;
  const recordCases = analytics?.casesWithViolations ?? 0;

  return (
    <section className="model-final-score-hero" aria-label="模型最终评分">
      <div className="model-final-score-main">
        <div className="model-final-score-value">
          {avg != null ? Number(avg).toFixed(1) : "—"}
        </div>
        <div className="model-final-score-meta">
          <h2>模型最终评分</h2>
          <p>
            综合 {count} 个测试用例 · 规则权重 {weightRule} + LLM 权重 {weightLlm}
          </p>
        </div>
      </div>
      <p className="model-final-score-eval-note">
        {useRecalcCoverage && recalcSummary ? (
          <>
            已用修正口径离线重算（未重跑 Layer2）：flow_miss {recalcSummary.flowMissOld}→
            {recalcSummary.flowMissNew}，均分 {recalcSummary.avgOld}→{recalcSummary.avgNew}。
          </>
        ) : null}
        路径覆盖按「实际走过的分支」计分，FAQ/挽留节点未触发不计缺失；覆盖率低于 85% 才记规则违规。
        {pathGapMinor > 0
          ? ` 另有 ${pathGapMinor} 例轻微偏差（85%–100%）未计入规则扣分。`
          : ""}
      </p>
      <div className="model-final-score-grid">
        {Object.entries(grades).map(([g, n]) => (
          <div className="model-final-stat" key={g}>
            <strong>{n}</strong>
            <span>{g} 级</span>
          </div>
        ))}
        <div
          className="model-final-stat warn"
          title="规则分低于 100 的用例数，与下方违规记录口径一致"
        >
          <strong>{ruleDeductionCases}</strong>
          <span>规则扣分用例</span>
        </div>
        <div
          className="model-final-stat warn"
          title="路径节点覆盖率低于 85% 的用例（计入规则 flow_miss）"
        >
          <strong>{pathGapCases}</strong>
          <span>路径覆盖不足</span>
        </div>
        <div
          className="model-final-stat"
          title="话术超长、硬边界、F4 未完成等在对话中触发的违规"
        >
          <strong>{runtimeCases}</strong>
          <span>话术/流程违规</span>
        </div>
        <div
          className="model-final-stat accent"
          title={`共 ${totalRecords} 条违规记录，分布在 ${recordCases} 个用例中；单用例可同时有路径覆盖与话术违规`}
        >
          <strong>{totalRecords}</strong>
          <span className="model-final-stat-sub">
            违规记录 · {recordCases} 例
          </span>
        </div>
        {topDim ? (
          <div className="model-final-stat accent">
            <strong>{Number(topDim[1]).toFixed(1)}</strong>
            <span>最高维 {dimLabel(topDim[0])}</span>
          </div>
        ) : null}
        {lowDim ? (
          <div className="model-final-stat warn">
            <strong>{Number(lowDim[1]).toFixed(1)}</strong>
            <span>最低维 {dimLabel(lowDim[0])}</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

export default ModelFinalScoreHero;

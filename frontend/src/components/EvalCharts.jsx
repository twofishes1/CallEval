import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { DIM_LABELS, violationTypeLabel } from "../utils/scoringAnalytics.js";

export { DIM_LABELS };

function RuleFailureTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload || {};
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-title">{row.constraint_id || row.name}</div>
      {row.description ? <div className="chart-tooltip-desc">{row.description}</div> : null}
      {row.violation_type ? (
        <div className="chart-tooltip-meta">违规类型：{violationTypeLabel(row.violation_type)}</div>
      ) : null}
      <div className="chart-tooltip-metrics">
        {payload.map((p) => (
          <div key={p.dataKey}>
            {p.name}：<strong>{p.value}</strong>
            {p.dataKey === "deduction" ? " 分" : " 次"}
          </div>
        ))}
      </div>
    </div>
  );
}

export function DimensionRadar({
  dimensionAverages,
  title = "六维能力雷达图",
  height = 320,
  compact = false,
  pdf = false,
  fill = false,
}) {
  const data = Object.entries(dimensionAverages || {})
    .map(([k, v]) => ({
      dimension: DIM_LABELS[k] || k,
      score: Math.round(Number(v) * 10) / 10,
      fullMark: 100,
    }))
    .sort((a, b) => a.dimension.localeCompare(b.dimension, "zh"));

  if (!data.length) return null;

  const h = pdf ? height || 252 : compact ? 220 : height;
  const outerRadius = pdf ? "92%" : fill ? "94%" : compact ? "86%" : "88%";
  const chartMargin = pdf
    ? { top: 2, right: 2, bottom: 2, left: 2 }
    : fill
      ? { top: 0, right: 0, bottom: 0, left: 0 }
      : { top: 4, right: 8, bottom: 4, left: 8 };
  const labelFontSize = pdf ? 11 : fill ? 11 : compact ? 10 : 12;

  return (
    <div
      className={`chart-box chart-box-radar${pdf ? " chart-box-radar-pdf" : ""}${fill ? " chart-box-radar-fill" : ""}`}
    >
      <h4>{title}</h4>
      <div className="chart-radar-body">
        <ResponsiveContainer width="100%" height={fill ? "100%" : h}>
          <RadarChart
            data={data}
            cx="50%"
            cy="50%"
            outerRadius={outerRadius}
            margin={chartMargin}
          >
            <PolarGrid stroke="#cbd5e1" strokeDasharray="3 3" />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{
                fontSize: labelFontSize,
                fill: "#334155",
                fontWeight: 500,
              }}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 100]}
              tickCount={pdf ? 4 : fill ? 4 : 5}
              tick={pdf || fill ? false : { fontSize: 10, fill: "#64748b" }}
              axisLine={false}
            />
            <Radar
              name="得分"
              dataKey="score"
              stroke="#0d9488"
              fill="#14b8a6"
              fillOpacity={0.42}
              strokeWidth={2}
              dot={{ r: fill ? 3.5 : 4, fill: "#0f766e", strokeWidth: 1, stroke: "#fff" }}
            />
            <Tooltip
              formatter={(value) => [`${value} 分`, "维度得分"]}
              labelFormatter={(label) => label}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function RuleFailureBar({
  ruleFailures,
  title = "规则失败统计",
  height,
  pdf = false,
}) {
  const data = (ruleFailures || []).slice(0, 8).map((r) => ({
    name: r.constraint_id,
    constraint_id: r.constraint_id,
    description: r.description || r.text || "",
    violation_type: r.violation_type || "",
    text: r.text || "",
    count: r.count,
    deduction: Math.round(r.totalDeduction * 10) / 10,
  }));
  const chartH = height ?? (pdf ? Math.max(168, data.length * 22 + 28) : Math.max(200, data.length * 28));
  const xMax = data.length
    ? Math.ceil(Math.max(...data.map((d) => Math.max(d.count, d.deduction))) * 1.12)
    : 10;
  if (!data.length) {
    return (
      <div className="chart-box">
        <h4>{title}</h4>
        <p className="chart-empty">暂无规则违规记录</p>
      </div>
    );
  }
  return (
    <div className={`chart-box${pdf ? " chart-box-pdf" : ""}`}>
      <h4>{title}</h4>
      {!pdf ? <p className="chart-hint">悬停条形可查看规则说明</p> : null}
      <ResponsiveContainer width="100%" height={chartH}>
        <BarChart
          data={data}
          layout="vertical"
          margin={pdf ? { left: 2, right: 12, top: 2, bottom: 2 } : { left: 4, right: 8, top: 4, bottom: 4 }}
          barCategoryGap={pdf ? "18%" : undefined}
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis
            type="number"
            allowDecimals={false}
            domain={[0, xMax]}
            tick={{ fontSize: pdf ? 9 : 10 }}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={pdf ? 44 : 52}
            tick={{ fontSize: pdf ? 9 : 10 }}
            tickFormatter={(id) => {
              const row = data.find((d) => d.name === id);
              const desc = row?.description || "";
              return desc.length > 14 ? `${id}…` : id;
            }}
          />
          {!pdf ? <Tooltip content={<RuleFailureTooltip />} /> : null}
          <Legend wrapperStyle={{ fontSize: pdf ? 9 : 10 }} />
          <Bar dataKey="count" name="触发" fill="#f59e0b" radius={[0, 4, 4, 0]} maxBarSize={pdf ? 14 : undefined} />
          <Bar dataKey="deduction" name="扣分" fill="#ef4444" radius={[0, 4, 4, 0]} maxBarSize={pdf ? 14 : undefined} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PersonaScoreBar({
  personaStats,
  title = "不同角色均分对比",
  height = 240,
  pdf = false,
}) {
  const data = (personaStats || []).map((p) => ({
    name: p.label || p.persona_type,
    avgScore: p.avgScore,
    violations: p.violations,
    count: p.count,
  }));
  if (!data.length) return null;
  return (
    <div className={`chart-box${pdf ? " chart-box-pdf" : ""}`}>
      <h4>{title}</h4>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={pdf ? { bottom: 4, left: 0, right: 4, top: 4 } : { bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: pdf ? 9 : 11 }}
            interval={0}
            angle={pdf ? -22 : -18}
            textAnchor="end"
            height={pdf ? 52 : 56}
          />
          <YAxis domain={[0, 100]} tick={{ fontSize: pdf ? 9 : 11 }} width={pdf ? 28 : undefined} />
          {!pdf ? (
            <Tooltip
              formatter={(val, key) => {
                if (key === "avgScore") return [`${val} 分`, "均分"];
                if (key === "violations") return [`${val} 次`, "违规"];
                return [val, key];
              }}
            />
          ) : null}
          <Legend wrapperStyle={{ fontSize: pdf ? 9 : 11 }} />
          <Bar dataKey="avgScore" name="均分" fill="#0d9488" radius={[4, 4, 0, 0]} />
          <Bar dataKey="violations" name="违规次数" fill="#f97316" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TerminationBar({
  terminationStats,
  title = "对话终止原因分布",
  height = 200,
  pdf = false,
}) {
  const data = (terminationStats || []).map((t) => ({
    name: t.label || t.reason,
    count: t.count,
  }));
  if (!data.length) return null;
  return (
    <div className={`chart-box${pdf ? " chart-box-pdf" : ""}`}>
      <h4>{title}</h4>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={pdf ? { bottom: 4, left: 0, right: 4, top: 4 } : undefined}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: pdf ? 9 : 10 }}
            interval={0}
            angle={pdf ? -16 : -12}
            textAnchor="end"
            height={pdf ? 44 : 48}
          />
          <YAxis allowDecimals={false} tick={{ fontSize: pdf ? 9 : 11 }} width={pdf ? 28 : undefined} />
          {!pdf ? <Tooltip /> : null}
          <Bar dataKey="count" name="用例数" fill="#6366f1" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function GradeBar({ gradeDistribution, height = 220, pdf = false }) {
  const data = Object.entries(gradeDistribution || {}).map(([grade, count]) => ({
    grade,
    count,
  }));
  if (!data.length) return null;
  return (
    <div className={`chart-box${pdf ? " chart-box-pdf" : ""}`}>
      <h4>等级分布</h4>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={pdf ? { bottom: 4, left: 0, right: 4, top: 4 } : undefined}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="grade" tick={{ fontSize: pdf ? 10 : 12 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: pdf ? 9 : 11 }} width={pdf ? 28 : undefined} />
          {!pdf ? <Tooltip /> : null}
          <Bar dataKey="count" fill="#4f6ef7" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CaseScoreBar({ reports, fullReports }) {
  const data = (reports || []).map((r) => {
    const full = fullReports?.[r.report_id];
    return {
      name: r.persona_type,
      score: r.total_score,
      grade: r.grade,
      rule: full?.aggregated?.rule_score,
      llm: full?.aggregated?.llm_score,
    };
  });
  if (!data.length) return null;
  return (
    <div className="chart-box">
      <h4>各用例得分</h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} layout="vertical" margin={{ left: 80 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" domain={[0, 100]} />
          <YAxis type="category" dataKey="name" width={72} tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Bar dataKey="score" name="总分" fill="#4f6ef7" />
          <Bar dataKey="rule" name="规则分" fill="#38a169" />
          <Bar dataKey="llm" name="LLM分" fill="#d69e2e" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ScoreBreakdown({ aggregated }) {
  if (!aggregated) return null;
  return (
    <div className="breakdown-box">
      <h4>计分说明</h4>
      {aggregated.score_breakdown ? (
        <p className="breakdown-formula">{aggregated.score_breakdown}</p>
      ) : null}
      <div className="breakdown-metrics">
        <span className="breakdown-metric">
          规则分：<strong>{aggregated.rule_score}</strong>
        </span>
        <span className="breakdown-metric">
          LLM 分：<strong>{aggregated.llm_score}</strong>
        </span>
        {(aggregated.consistency_penalty ?? 0) > 0 && (
          <span className="breakdown-metric">
            一致性惩罚：<strong>{aggregated.consistency_penalty}</strong>
          </span>
        )}
        <span className="breakdown-metric breakdown-metric-total">
          总分：<strong>{aggregated.total_score}</strong>（{aggregated.grade}）
        </span>
      </div>
    </div>
  );
}

export function ModelScoreSummary({ averageScore, count, gradeDistribution }) {
  return (
    <div className="score-card">
      <div className="item">
        <strong>{Number(averageScore).toFixed(1)}</strong>
        模型均分
      </div>
      <div className="item">
        <strong>{count}</strong>
        用例数
      </div>
      {Object.entries(gradeDistribution || {}).map(([g, n]) => (
        <div className="item" key={g}>
          <strong>{n}</strong>
          {g} 级
        </div>
      ))}
    </div>
  );
}

const DIM_WEIGHTS = {
  flow_adherence: 0.25,
  dialogue_compliance: 0.2,
  knowledge_accuracy: 0.2,
  retention_effectiveness: 0.15,
  boundary_handling: 0.1,
  naturalness: 0.1,
};

export function EvidenceChainPanel({ evidence }) {
  const rows = Array.isArray(evidence) ? evidence : [];
  if (!rows.length) {
    return (
      <div className="evidence-chain">
        <h5>Judge 证据链</h5>
        <p className="muted">暂无维度证据（可能跳过了 LLM Judge）</p>
      </div>
    );
  }
  return (
    <div className="evidence-chain">
      <h5>Judge 证据链（Rubric + CoT 轮次引用）</h5>
      {rows.map((d) => {
        const dim = d.dimension || "";
        const label = DIM_LABELS[dim] || dim;
        const w = DIM_WEIGHTS[dim] ?? d.weight ?? 0;
        const score = d.score ?? "?";
        const na = d.applicable === false;
        const turns = na ? "" : (d.evidence_turns || []).map((t) => `[T${t}]`).join(" ");
        return (
          <div className="evidence-item" key={dim}>
            <div className="evidence-head">
              <strong>{label}</strong>
              <span>
                {na
                  ? "本任务不适用"
                  : `Rubric ${score}/5 · 权重 ${(w * 100).toFixed(0)}%`}
              </span>
              {turns && <span className="turn-refs">{turns}</span>}
            </div>
            <p className="evidence-reason">{d.reasoning}</p>
            {(d.key_issues || []).length > 0 && (
              <ul className="evidence-issues">
                {d.key_issues.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

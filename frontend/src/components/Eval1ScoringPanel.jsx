import { useMemo, useState } from "react";
import {
  CaseScoreBar,
  DimensionRadar,
  GradeBar,
  ScoreBreakdown,
} from "./EvalCharts";
import { ViolationList, ViolationSummary } from "./ViolationList";

const DIM_LABELS = {
  flow_adherence: "流程遵循",
  dialogue_compliance: "话术合规",
  knowledge_accuracy: "知识准确",
  retention_effectiveness: "挽留效果",
  boundary_handling: "边界处理",
  naturalness: "自然度",
};

function dimLabel(key) {
  return DIM_LABELS[key] || key;
}

export default function Eval1ScoringPanel({ payload, loading }) {
  const reports = payload?.reports || [];
  const summary = payload?.summary || {};
  const dialogues = payload?.layer2?.dialogues || [];

  const reportById = useMemo(() => {
    const m = {};
    reports.forEach((r) => {
      if (r?.report_id) m[r.report_id] = r;
    });
    dialogues.forEach((d) => {
      const id = d?.report_id;
      if (!id) return;
      m[id] = { ...(m[id] || {}), ...d };
    });
    return m;
  }, [reports, dialogues]);

  const fullReportsMap = useMemo(() => {
    const map = {};
    Object.entries(reportById).forEach(([id, r]) => {
      map[id] = {
        aggregated: {
          rule_score: r.rule_score,
          llm_score: r.llm_score,
          total_score: r.total_score,
          grade: r.grade,
          consistency_penalty: r.consistency_penalty || 0,
          score_breakdown: r.score_breakdown,
          dimension_scores: r.dimension_scores,
        },
        dimension_evidence:
          r.dimension_evidence || r.judge_evidence_chain || [],
        judge_comment: r.judge_comment,
      };
    });
    return map;
  }, [reportById]);

  const [selectedId, setSelectedId] = useState(null);
  const selected = selectedId ? reportById[selectedId] : null;

  const aggregateForCharts = useMemo(
    () => ({
      average_score: summary.average_score,
      reports: reports.map((r) => ({
        report_id: r.report_id,
        persona_type: r.persona_type,
        path_id: r.path_id,
        total_score: r.total_score,
        grade: r.grade,
      })),
      grade_distribution: summary.grade_distribution,
      dimension_averages: summary.dimension_averages,
    }),
    [reports, summary]
  );

  if (loading) {
    return (
      <div className="card fade-up">
        <div className="card-body muted">评分数据加载中…</div>
      </div>
    );
  }

  if (!reports.length) {
    return (
      <div className="card fade-up">
        <div className="card-body muted">暂无评测报告，请先运行 Layer2 评测或刷新。</div>
      </div>
    );
  }

  return (
    <div className="card fade-up">
      <div className="card-head">
        <span className="card-icon">📊</span>
        <span className="card-title">Eval1 评分可视化</span>
        <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>
          模型均分 {summary.average_score ?? "-"} · {summary.count ?? reports.length} 用例
        </span>
      </div>
      <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="score-card" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
          <div className="item">
            <strong>{summary.average_score ?? "-"}</strong>
            模型均分
          </div>
          <div className="item">
            <strong>{summary.count ?? reports.length}</strong>
            用例数
          </div>
          <div className="item">
            <strong>{summary.meta?.weight_rule ?? "0.4"}</strong>
            规则权重
          </div>
          <div className="item">
            <strong>{summary.meta?.weight_llm ?? "0.6"}</strong>
            LLM权重
          </div>
        </div>

        <div className="charts-grid">
          <DimensionRadar dimensionAverages={aggregateForCharts.dimension_averages} />
          <GradeBar gradeDistribution={aggregateForCharts.grade_distribution} />
          <CaseScoreBar
            reports={aggregateForCharts.reports}
            fullReports={fullReportsMap}
          />
        </div>

        <div className="case-detail-grid">
          <ul className="report-list">
            {reports.map((r) => (
              <li
                key={r.report_id}
                className={selectedId === r.report_id ? "active" : ""}
                onClick={() => setSelectedId(r.report_id)}
              >
                <div>
                  {r.path_id} · {r.persona_type} — {r.total_score} ({r.grade})
                </div>
                <small>
                  规则 {r.rule_score} + LLM {r.llm_score}
                </small>
                <ViolationSummary violations={r.violations} />
              </li>
            ))}
          </ul>

          {selected && (
            <div className="case-detail">
              <h4>
                {selected.path_id} · {selected.persona_type} · {selected.total_score} ({selected.grade})
              </h4>
              <ScoreBreakdown aggregated={fullReportsMap[selected.report_id]?.aggregated} />
              {selected.judge_comment ? <p>{selected.judge_comment}</p> : null}

              <ViolationList violations={selected.violations} />

              <h5>维度证据链（Rubric + CoT + 轮次引用）</h5>
              {(selected.dimension_evidence || []).length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {(selected.dimension_evidence || []).map((d, i) => (
                    <div className="violation" key={`${d.dimension}-${i}`}>
                      <strong>
                        {dimLabel(d.dimension)}
                        {d.applicable === false
                          ? " · 不适用"
                          : ` · ${d.score}/5${d.weight ? ` (权重 ${(d.weight * 100).toFixed(0)}%)` : ""}`}
                      </strong>
                      <div style={{ fontSize: 12, marginTop: 4 }}>
                        证据轮次:{" "}
                        {d.applicable === false
                          ? "—"
                          : (d.evidence_turns || []).join(", ") || "-"}
                      </div>
                      <div style={{ fontSize: 12, marginTop: 4, lineHeight: 1.5 }}>
                        {d.reasoning}
                      </div>
                      {(d.key_issues || []).length > 0 && (
                        <div style={{ fontSize: 11, color: "var(--ember)", marginTop: 4 }}>
                          问题: {d.key_issues.join("；")}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="muted">暂无维度证据（需重新跑评测以生成 Judge 输出）</p>
              )}

              <h5>对话记录</h5>
              <div className="dialogue">
                {(selected.messages || []).map((t) => (
                  <div className={`turn ${t.role}`} key={t.turn}>
                    [T{t.turn}] {t.role}: {t.content}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

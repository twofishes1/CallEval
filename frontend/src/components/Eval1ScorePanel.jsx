import { useMemo, useState } from "react";
import {
  CaseScoreBar,
  DimensionRadar,
  EvidenceChainPanel,
  GradeBar,
  ModelScoreSummary,
  ScoreBreakdown,
} from "./EvalCharts";

export default function Eval1ScorePanel({ data, loading }) {
  const reports = useMemo(() => {
    const fromTop = Array.isArray(data?.reports) ? data.reports : [];
    const dialogues = data?.layer2?.dialogues || [];
    if (fromTop.length) return fromTop;
    return dialogues.map((d, i) => ({
      report_id: d.report_id || `dlg-${i}`,
      persona_type: d.persona_type,
      path_id: d.path_id,
      total_score: d.total_score,
      grade: d.grade,
      rule_score: d.rule_score,
      llm_score: d.llm_score,
      score_breakdown: d.score_breakdown,
      dimension_scores: d.dimension_scores || {},
      dimension_evidence: d.dimension_evidence || [],
      judge_comment: d.judge_comment,
      top_improvement: d.top_improvement,
      summary: `${d.path_id} · ${d.persona_type}`,
      messages: d.messages,
    }));
  }, [data]);

  const dimensionAverages = data?.dimension_averages || data?.summary?.dimension_averages || {};
  const gradeDistribution = data?.grade_distribution || data?.summary?.grade_distribution || {};
  const averageScore = data?.summary?.average_score ?? data?.average_score ?? 0;
  const count = data?.summary?.count ?? data?.count ?? reports.length;

  const [selectedId, setSelectedId] = useState("");
  const selected = useMemo(() => {
    const id = selectedId || reports[0]?.report_id;
    return reports.find((r) => r.report_id === id) || reports[0] || null;
  }, [reports, selectedId]);

  const fullReportsMap = useMemo(() => {
    const m = {};
    reports.forEach((r) => {
      m[r.report_id] = {
        aggregated: {
          total_score: r.total_score,
          grade: r.grade,
          rule_score: r.rule_score,
          llm_score: r.llm_score,
          score_breakdown: r.score_breakdown,
          consistency_penalty: 0,
        },
        dimension_evidence: r.dimension_evidence,
        judge_comment: r.judge_comment,
        top_improvement: r.top_improvement,
        dialogue_turns: (r.messages || []).map((m) => ({
          turn: m.turn,
          role: m.role,
          content: m.content,
        })),
      };
    });
    return m;
  }, [reports]);

  if (loading && !reports.length) {
    return <p className="muted">评分数据加载中…</p>;
  }
  if (!reports.length) {
    return <p className="muted">暂无评测报告，请先运行 Eval1 Layer2。</p>;
  }

  return (
    <div className="eval1-score-panel">
      <ModelScoreSummary
        averageScore={averageScore}
        count={count}
        gradeDistribution={gradeDistribution}
      />

      <div className="charts-grid">
        <DimensionRadar dimensionAverages={dimensionAverages} title="模型六维均分" />
        <GradeBar gradeDistribution={gradeDistribution} />
        <CaseScoreBar
          reports={reports.map((r) => ({
            report_id: r.report_id,
            persona_type: `${r.path_id?.slice(0, 12) || ""} · ${r.persona_type}`,
            total_score: r.total_score,
            grade: r.grade,
          }))}
          fullReports={fullReportsMap}
        />
      </div>

      <div className="case-detail-grid">
        <ul className="report-list">
          {reports.map((r) => (
            <li
              key={r.report_id}
              className={selected?.report_id === r.report_id ? "active" : ""}
              onClick={() => setSelectedId(r.report_id)}
            >
              <div>
                {r.persona_type} — {Number(r.total_score).toFixed(1)} ({r.grade})
              </div>
              <small>{r.path_id}</small>
            </li>
          ))}
        </ul>

        {selected && (
          <div className="case-detail">
            <h4>
              {selected.path_id} · {selected.persona_type} · {Number(selected.total_score).toFixed(1)} (
              {selected.grade})
            </h4>
            <ScoreBreakdown aggregated={fullReportsMap[selected.report_id]?.aggregated} />
            {selected.judge_comment && <p className="judge-comment">{selected.judge_comment}</p>}
            <DimensionRadar
              dimensionAverages={selected.dimension_scores}
              title="本用例六维得分"
            />
            <EvidenceChainPanel evidence={selected.dimension_evidence || []} />
            {selected.top_improvement && (
              <>
                <h5>首要改进</h5>
                <p>{selected.top_improvement}</p>
              </>
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
  );
}

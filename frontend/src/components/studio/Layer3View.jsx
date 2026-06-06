import { useEffect, useMemo, useRef, useState } from "react";
import {
  DimensionRadar,
  GradeBar,
  PersonaScoreBar,
  RuleFailureBar,
  ScoreBreakdown,
  TerminationBar,
} from "../EvalCharts.jsx";
import { ViolationList, ViolationSummary } from "../ViolationList.jsx";
import { ModelFinalScoreHero } from "../scoring/ModelFinalScoreHero.jsx";
import EvalTestReportDocument from "../scoring/EvalTestReportDocument.jsx";
import { buildEvalTestReport } from "../../utils/buildEvalTestReport.js";
import {
  buildRecalcSummary,
  recalcReportsFromDialogues,
} from "../../utils/recalcCoverage.js";
import { buildScoringAnalytics, dimLabel, personaLabel } from "../../utils/scoringAnalytics.js";
import { generateEvalReportPdf } from "../../utils/generateEvalReportPdf.js";

const EMPTY_REPORTS = [];
const EMPTY_DIALOGUES = [];

const BOT_PROVIDER_LABELS = {
  qwen: "Qwen Bot",
  deepseek: "DeepSeek Bot",
};

export default function Layer3View({ data, loading, datasetName, botProvider = "qwen", loadError = "" }) {
  const activeBot = data?.bot_provider || botProvider || "qwen";
  const botLabel = BOT_PROVIDER_LABELS[activeBot] || activeBot;
  const reports = useMemo(() => {
    const r = data?.reports;
    return Array.isArray(r) ? r : EMPTY_REPORTS;
  }, [data?.reports]);
  const summary = data?.summary || {};
  const meta = summary?.meta || data?.meta || {};
  const dialogues = useMemo(() => {
    const d = data?.layer2?.dialogues;
    return Array.isArray(d) ? d : EMPTY_DIALOGUES;
  }, [data?.layer2?.dialogues]);
  const pathsById = useMemo(
    () => data?.layer2?.paths_by_id ?? {},
    [data?.layer2?.paths_by_id],
  );

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

  const enrichedReports = useMemo(
    () => reports.map((r) => reportById[r.report_id] || r),
    [reports, reportById],
  );

  const canRecalcCoverage = useMemo(
    () => dialogues.some((d) => Array.isArray(d?.path_nodes) && d.path_nodes.length > 0),
    [dialogues],
  );

  const [useRecalcCoverage, setUseRecalcCoverage] = useState(true);

  const effectiveReports = useMemo(() => {
    if (!useRecalcCoverage || !canRecalcCoverage) return enrichedReports;
    return recalcReportsFromDialogues(reports, dialogues, meta);
  }, [useRecalcCoverage, canRecalcCoverage, enrichedReports, reports, dialogues, meta]);

  const recalcSummary = useMemo(() => {
    if (!canRecalcCoverage) return null;
    return buildRecalcSummary(reports, recalcReportsFromDialogues(reports, dialogues, meta));
  }, [canRecalcCoverage, reports, dialogues, meta]);

  const displaySummary = useMemo(() => {
    if (!useRecalcCoverage || !canRecalcCoverage) return summary;
    const count = effectiveReports.length;
    if (!count) return summary;
    const grades = {};
    let sum = 0;
    for (const r of effectiveReports) {
      sum += Number(r.total_score || 0);
      const g = r.grade || "?";
      grades[g] = (grades[g] || 0) + 1;
    }
    return {
      ...summary,
      count,
      average_score: Math.round((sum / count) * 100) / 100,
      grade_distribution: grades,
      coverage_recalc: true,
    };
  }, [useRecalcCoverage, canRecalcCoverage, summary, effectiveReports]);

  const analytics = useMemo(() => buildScoringAnalytics(effectiveReports), [effectiveReports]);

  const testReport = useMemo(
    () =>
      buildEvalTestReport({
        summary: displaySummary,
        meta,
        analytics,
        reports: effectiveReports,
        datasetName: datasetName || data?.dataset_name,
        datasetId: data?.dataset_id,
        layer1Summary: data?.layer1_summary,
      }),
    [displaySummary, meta, analytics, effectiveReports, datasetName, data],
  );

  const [selectedId, setSelectedId] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [showPdfAppendix, setShowPdfAppendix] = useState(false);
  const pdfReportRef = useRef(null);

  const selected = selectedId ? (effectiveReports.find((r) => r.report_id === selectedId) || reportById[selectedId]) : null;

  useEffect(() => {
    if (!reports.length) {
      setSelectedId(null);
      return;
    }
    if (selectedId && reportById[selectedId]) return;
    setSelectedId(reports[0].report_id);
  }, [reports, selectedId, reportById]);

  const fullAggregated = useMemo(() => {
    if (!selected) return null;
    return {
      rule_score: selected.rule_score,
      llm_score: selected.llm_score,
      total_score: selected.total_score,
      grade: selected.grade,
      consistency_penalty: selected.consistency_penalty || 0,
      score_breakdown: selected.score_breakdown,
      dimension_scores: selected.dimension_scores,
    };
  }, [selected]);

  const evidence =
    selected?.dimension_evidence || selected?.judge_evidence_chain || [];

  const handleExportPdf = async () => {
    const reportEl = pdfReportRef.current;
    if (!reportEl) return;
    setExporting(true);
    setShowPdfAppendix(true);
    try {
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      await new Promise((r) => setTimeout(r, 280));
      const name = datasetName || data?.dataset_id || "eval1";
      const date = new Date().toISOString().slice(0, 10);
      await generateEvalReportPdf({
        reportElement: reportEl,
        filename: `${name}-评测报告-${date}.pdf`,
      });
    } catch (e) {
      console.error(e);
      window.alert(`生成 PDF 失败：${e?.message || e}`);
    } finally {
      setShowPdfAppendix(false);
      setExporting(false);
    }
  };

  if (loading) {
    return <div className="studio-loading">Layer3 评分数据加载中…</div>;
  }

  if (!reports.length) {
    return (
      <div className="layer-view-empty">
        <p>
          暂无 <strong>{botLabel}</strong> 评分报告
          {data?.report_file ? `（${data.report_file}）` : ""}
        </p>
        {loadError ? <p className="layer2-load-error">{loadError}</p> : null}
      </div>
    );
  }

  return (
    <div className="layer-view layer3-view">
      <div className="layer3-toolbar">
        <span className="layer3-toolbar-hint">
          <span className={`layer2-bot-badge ${activeBot}`}>{botLabel}</span>
          {" "}
          先查看模型总评与多角度统计，再展开各测试用例明细
          {data?.report_file ? ` · ${data.report_file}` : ""}
        </span>
        {canRecalcCoverage ? (
          <label className="studio-control-toggle layer3-recalc-toggle" title="用 bot_state_log + 新覆盖算法离线重算 flow_miss，无需重跑 Layer2">
            <input
              type="checkbox"
              checked={useRecalcCoverage}
              onChange={(e) => setUseRecalcCoverage(e.target.checked)}
            />
            修正口径统计
            {recalcSummary ? (
              <span className="layer3-recalc-hint">
                flow_miss {recalcSummary.flowMissOld}→{recalcSummary.flowMissNew}
              </span>
            ) : null}
          </label>
        ) : null}
        <button
          type="button"
          className="btn-primary layer3-export-btn"
          onClick={handleExportPdf}
          disabled={exporting}
        >
          {exporting ? "正在生成 PDF…" : "一键生成评测报告 (PDF)"}
        </button>
      </div>

      <div className="eval-report-pdf-stack" aria-hidden="true">
        <div className="eval-report-pdf-source" ref={pdfReportRef}>
          <EvalTestReportDocument report={testReport} />

          {showPdfAppendix ? (
            <div className="eval-report-pdf-appendix">
              <section
                className="eval-report-pdf-appendix-block eval-report-pdf-appendix-head"
                data-pdf-section
                data-pdf-appendix
              >
                <h2 className="eval-report-pdf-appendix-title">附录：统计数据图表</h2>
                <p className="eval-report-pdf-appendix-desc">
                  以下图表与正文统计口径一致，供可视化查阅；正文以表格数据为准。
                </p>
              </section>

              <section
                className="eval-report-pdf-appendix-block eval-report-pdf-appendix-charts"
                data-pdf-section
                data-pdf-appendix
              >
                <div className="eval-report-pdf-appendix-row eval-report-pdf-appendix-row-2">
                  <div className="eval-report-pdf-appendix-cell">
                    <DimensionRadar
                      dimensionAverages={displaySummary.dimension_averages}
                      title="六维能力雷达"
                      height={252}
                      pdf
                    />
                  </div>
                  <div className="eval-report-pdf-appendix-cell">
                    <GradeBar
                      gradeDistribution={displaySummary.grade_distribution}
                      height={252}
                      pdf
                    />
                  </div>
                </div>
              </section>

              <section
                className="eval-report-pdf-appendix-block eval-report-pdf-appendix-charts"
                data-pdf-section
                data-pdf-appendix
              >
                <div className="eval-report-pdf-appendix-row eval-report-pdf-appendix-row-2">
                  <div className="eval-report-pdf-appendix-cell">
                    <PersonaScoreBar
                      personaStats={analytics.personaStats}
                      height={252}
                      pdf
                    />
                  </div>
                  <div className="eval-report-pdf-appendix-cell">
                    <TerminationBar
                      terminationStats={analytics.terminationStats}
                      height={252}
                      pdf
                    />
                  </div>
                </div>
              </section>

              <section
                className="eval-report-pdf-appendix-block eval-report-pdf-appendix-charts"
                data-pdf-section
                data-pdf-appendix
              >
                <div className="eval-report-pdf-appendix-row">
                  <div className="eval-report-pdf-appendix-cell eval-report-pdf-appendix-cell-wide">
                    <RuleFailureBar ruleFailures={analytics.ruleFailures} pdf />
                  </div>
                </div>
              </section>
            </div>
          ) : null}
        </div>
      </div>

      <div className="layer3-body" id="eval-report-export-root">
        <div className="layer3-scroll layer3-scroll-top">
          <ModelFinalScoreHero summary={displaySummary} meta={meta} analytics={analytics} recalcSummary={recalcSummary} useRecalcCoverage={useRecalcCoverage && canRecalcCoverage} />

          <section className="layer3-section">
            <h3 className="layer3-section-title">多角度统计分析</h3>
            <div className="layer3-analytics-grid layer3-analytics-row-3">
              <div className="layer3-analytics-cell">
                <DimensionRadar
                  dimensionAverages={displaySummary.dimension_averages}
                  title="六维能力雷达"
                  fill
                />
              </div>
              <div className="layer3-analytics-cell">
                <GradeBar gradeDistribution={displaySummary.grade_distribution} height={260} />
              </div>
              <div className="layer3-analytics-cell">
                <RuleFailureBar ruleFailures={analytics.ruleFailures} height={260} />
              </div>
            </div>
            <div className="layer3-analytics-grid layer3-analytics-row-2">
              <div className="layer3-analytics-cell">
                <PersonaScoreBar personaStats={analytics.personaStats} height={240} />
              </div>
              <div className="layer3-analytics-cell">
                <TerminationBar terminationStats={analytics.terminationStats} height={240} />
              </div>
            </div>
          </section>
        </div>

        <section className="layer3-section layer3-cases-section">
          <h3 className="layer3-section-title">各测试用例分析</h3>
          <div className="layer3-detail-split">
            <ul className="layer3-report-list" role="listbox" aria-label="测试用例列表">
              {reports.map((r) => {
                const row = effectiveReports.find((x) => x.report_id === r.report_id) || r;
                return (
                <li
                  key={r.report_id}
                  role="option"
                  aria-selected={selectedId === r.report_id}
                  className={selectedId === r.report_id ? "active" : ""}
                  onClick={() => setSelectedId(r.report_id)}
                >
                  <div className="layer3-report-row-title">
                    <span>{row.path_id}</span>
                    <span className="layer3-report-score">
                      {Number(row.total_score).toFixed(1)} · {row.grade}
                      {row.coverage_recalc_applied ? (
                        <span className="layer3-recalc-badge" title="已用修正口径重算">↻</span>
                      ) : null}
                    </span>
                  </div>
                  <small>
                    {personaLabel(row.persona_type)} · 规则 {row.rule_score} + LLM {row.llm_score}
                    {row.flow_adherence_rate_legacy != null &&
                    row.flow_adherence_rate !== row.flow_adherence_rate_legacy ? (
                      <> · 覆盖 {Math.round(Number(row.flow_adherence_rate) * 1000) / 10}%</>
                    ) : null}
                  </small>
                  <ViolationSummary violations={row.violations} />
                </li>
              );})}
            </ul>

            <div className="layer3-detail">
              {selected ? (
                <>
                  <h4 className="layer3-case-title">
                    {selected.path_id} · {personaLabel(selected.persona_type)} ·{" "}
                    {Number(selected.total_score).toFixed(1)} ({selected.grade})
                  </h4>

                  <div className="layer3-case-head">
                    <div className="layer3-case-head-main">
                      <ScoreBreakdown aggregated={fullAggregated} />
                      {selected.judge_comment ? (
                        <p className="judge-comment">{selected.judge_comment}</p>
                      ) : null}
                      {selected.top_improvement ? (
                        <div className="layer3-improvement">
                          <h5>首要改进</h5>
                          <p className="judge-comment">{selected.top_improvement}</p>
                        </div>
                      ) : null}
                    </div>
                    <div className="layer3-case-head-radar">
                      <DimensionRadar
                        dimensionAverages={selected.dimension_scores}
                        title="本用例六维得分"
                        fill
                      />
                    </div>
                  </div>

                  <ViolationList
                    violations={selected.violations}
                    pathMeta={pathsById[selected.path_id]}
                    flowAdherenceRate={selected.flow_adherence_rate}
                  />

                  <h5>维度证据链</h5>
                  <div className="evidence-stack">
                    {evidence.length ? (
                      evidence.map((d, i) => (
                        <div className="evidence-card" key={`${d.dimension}-${i}`}>
                          <div className="evidence-card-head">
                            <strong>{dimLabel(d.dimension)}</strong>
                            {d.applicable === false ? (
                              <span className="na-tag">不适用</span>
                            ) : (
                              <span>
                                {d.score}/5
                                {d.weight
                                  ? ` · 权重 ${(d.weight * 100).toFixed(0)}%`
                                  : ""}
                              </span>
                            )}
                          </div>
                          <p>{d.reasoning}</p>
                          {(d.key_issues || []).length > 0 && (
                            <ul className="issue-list">
                              {d.key_issues.map((x, j) => (
                                <li key={j}>{x}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      ))
                    ) : (
                      <p className="muted">暂无维度证据</p>
                    )}
                  </div>
                </>
              ) : (
                <div className="studio-empty">选择左侧用例查看详情</div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

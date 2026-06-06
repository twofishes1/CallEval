/** Structured test report (narrative), distinct from chart dashboard. */
import { cnSectionNum, cnSubSectionNum } from "../../utils/reportSectionNumbers.js";

const REPORT_PRODUCT = "CallEval";
const REPORT_TITLE = `${REPORT_PRODUCT} 复杂指令对话模型评测报告`;

export default function EvalTestReportDocument({ report }) {
  if (!report) return null;
  const {
    header,
    verdict,
    executiveSummary,
    testOverview,
    scoreSummary,
    gradeRows,
    dimensionRows,
    personaRows,
    pathRows,
    ruleFailureRows,
    violationTypeRows,
    terminationRows,
    planGroupRows,
    improvementRows,
    findings,
    conclusions,
    recommendations,
    weakCases = [],
    bestPaths,
  } = report;

  let sectionIdx = 0;
  const nextSection = () => cnSectionNum(sectionIdx++);

  const sections = [];

  sections.push({
    key: "summary",
    title: `${nextSection()}、执行摘要`,
    body: (
      <>
        {executiveSummary.map((p, i) => (
          <p key={i} className="eval-test-report-p">
            {p}
          </p>
        ))}
      </>
    ),
  });

  sections.push({
    key: "overview",
    title: `${nextSection()}、测试概况`,
    body: (
      <>
        <ul className="eval-test-report-list">
          <li>
            <strong>测试范围：</strong>
            {testOverview.scope}
          </li>
          <li>
            <strong>测试方法：</strong>
            {testOverview.method}
          </li>
          <li>
            <strong>计分规则：</strong>
            {testOverview.scoring}
          </li>
        </ul>
        {scoreSummary?.avgTotal != null ? (
          <div className="eval-test-report-kpi-row">
            <div className="eval-test-report-kpi">
              <span className="eval-test-report-kpi-label">综合均分</span>
              <span className="eval-test-report-kpi-value">{scoreSummary.avgTotal}</span>
            </div>
            <div className="eval-test-report-kpi">
              <span className="eval-test-report-kpi-label">规则均分</span>
              <span className="eval-test-report-kpi-value">{scoreSummary.avgRule ?? "—"}</span>
            </div>
            <div className="eval-test-report-kpi">
              <span className="eval-test-report-kpi-label">LLM 均分</span>
              <span className="eval-test-report-kpi-value">{scoreSummary.avgLlm ?? "—"}</span>
            </div>
            <div className="eval-test-report-kpi">
              <span className="eval-test-report-kpi-label">路径覆盖率</span>
              <span className="eval-test-report-kpi-value">
                {scoreSummary.avgFlowAdherence != null
                  ? `${scoreSummary.avgFlowAdherence}%`
                  : "—"}
              </span>
            </div>
          </div>
        ) : null}
      </>
    ),
  });

  const resultsSectionIndex = sectionIdx;
  sections.push({
    key: "results",
    title: `${nextSection()}、测试结果`,
    body: (
      <div className="eval-test-report-tables eval-test-report-tables-pdf">
        <div className="eval-test-report-table-wrap">
          <h3>{cnSubSectionNum(resultsSectionIndex, 1)} 等级分布</h3>
          <table className="eval-test-report-table">
            <thead>
              <tr>
                <th>等级</th>
                <th>用例数</th>
                <th>占比</th>
              </tr>
            </thead>
            <tbody>
              {(gradeRows || []).map((row) => (
                <tr key={row.grade}>
                  <td>{row.grade}</td>
                  <td>{row.count}</td>
                  <td>{row.percent}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="eval-test-report-table-wrap">
          <h3>{cnSubSectionNum(resultsSectionIndex, 2)} 六维能力均分</h3>
          <table className="eval-test-report-table">
            <thead>
              <tr>
                <th>维度</th>
                <th>均分</th>
              </tr>
            </thead>
            <tbody>
              {(dimensionRows || []).map((row) => (
                <tr key={row.dimension}>
                  <td>{row.dimension}</td>
                  <td>{row.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    ),
  });

  sections.push({
    key: "persona",
    title: `${nextSection()}、用户角色分析`,
    body: (personaRows || []).length ? (
      <table className="eval-test-report-table eval-test-report-table-wide eval-test-report-table-pdf">
        <thead>
          <tr>
            <th>角色</th>
            <th>用例数</th>
            <th>均分</th>
            <th>规则均分</th>
            <th>LLM 均分</th>
            <th>违规次数</th>
          </tr>
        </thead>
        <tbody>
          {personaRows.map((row) => (
            <tr key={row.persona}>
              <td>{row.persona}</td>
              <td>{row.count}</td>
              <td>{row.avgScore}</td>
              <td>{row.avgRule}</td>
              <td>{row.avgLlm}</td>
              <td>{row.violations}</td>
            </tr>
          ))}
        </tbody>
      </table>
    ) : (
      <p className="eval-test-report-p eval-test-report-note">暂无角色维度统计数据。</p>
    ),
  });

  const pathRowsPdf = (pathRows || []).slice(0, 16);
  sections.push({
    key: "paths",
    title: `${nextSection()}、测试路径分析`,
    body: (
      <>
        {bestPaths?.length ? (
          <p className="eval-test-report-p eval-test-report-note">
            表现最佳路径：
            {bestPaths.map((p) => `${p.path_id}（${p.avgScore} 分）`).join("、")}。
          </p>
        ) : null}
        {(pathRows || []).length ? (
          <>
            <table className="eval-test-report-table eval-test-report-table-wide eval-test-report-table-compact eval-test-report-table-pdf">
              <thead>
                <tr>
                  <th>路径 ID</th>
                  <th>用例数</th>
                  <th>均分</th>
                  <th>违规次数</th>
                </tr>
              </thead>
              <tbody>
                {pathRowsPdf.map((row) => (
                  <tr key={row.path_id}>
                    <td>{row.path_id}</td>
                    <td>{row.count}</td>
                    <td>{row.avgScore}</td>
                    <td>{row.violations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(pathRows || []).length > pathRowsPdf.length ? (
              <p className="eval-test-report-p eval-test-report-note">
                另有 {(pathRows || []).length - pathRowsPdf.length} 条路径未列入 PDF，完整列表请在系统中查看。
              </p>
            ) : null}
          </>
        ) : (
          <p className="eval-test-report-p eval-test-report-note">暂无路径维度统计数据。</p>
        )}
      </>
    ),
  });

  const rulesSectionIndex = sectionIdx;
  sections.push({
    key: "rules",
    title: `${nextSection()}、规则与终止统计`,
    body: (
      <>
        <div className="eval-test-report-tables eval-test-report-tables-pdf">
          {ruleFailureRows?.length ? (
            <div className="eval-test-report-table-wrap">
              <h3>{cnSubSectionNum(rulesSectionIndex, 1)} 高频规则违规</h3>
              <table className="eval-test-report-table eval-test-report-table-compact">
                <thead>
                  <tr>
                    <th>约束 ID</th>
                    <th>类型</th>
                    <th>次数</th>
                    <th>累计扣分</th>
                  </tr>
                </thead>
                <tbody>
                  {ruleFailureRows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.id}</td>
                      <td className="eval-test-report-cell-muted">{row.type}</td>
                      <td>{row.count}</td>
                      <td>{row.deduction}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="eval-test-report-table-note">
                {ruleFailureRows.slice(0, 3).map((r) => `${r.id}：${r.description}`).join("；")}
              </p>
            </div>
          ) : (
            <div className="eval-test-report-table-wrap">
              <h3>{cnSubSectionNum(rulesSectionIndex, 1)} 规则违规</h3>
              <p className="eval-test-report-p">本轮未记录规则扣分项。</p>
            </div>
          )}
          {violationTypeRows?.length ? (
            <div className="eval-test-report-table-wrap">
              <h3>{cnSubSectionNum(rulesSectionIndex, 2)} 违规类型分布</h3>
              <table className="eval-test-report-table">
                <thead>
                  <tr>
                    <th>类型</th>
                    <th>次数</th>
                    <th>占比</th>
                  </tr>
                </thead>
                <tbody>
                  {violationTypeRows.map((row) => (
                    <tr key={row.type}>
                      <td>{row.type}</td>
                      <td>{row.count}</td>
                      <td>{row.percent}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
        {terminationRows?.length ? (
          <>
            <h3>{cnSubSectionNum(rulesSectionIndex, 3)} 对话终止原因</h3>
            <table className="eval-test-report-table">
              <thead>
                <tr>
                  <th>终止原因</th>
                  <th>用例数</th>
                  <th>占比</th>
                </tr>
              </thead>
              <tbody>
                {terminationRows.map((row) => (
                  <tr key={row.reason}>
                    <td>{row.reason}</td>
                    <td>{row.count}</td>
                    <td>{row.percent}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}
      </>
    ),
  });

  if (planGroupRows?.length > 1) {
    sections.push({
      key: "plan-groups",
      title: `${nextSection()}、语义标注分组对比`,
      body: (
        <>
          <p className="eval-test-report-p eval-test-report-note">
            「可能语义矛盾」为路径×角色组合的标注（非额外跑数）；用于对比语义匹配与非常态组合下的得分差异。
          </p>
          <table className="eval-test-report-table eval-test-report-table-wide">
            <thead>
              <tr>
                <th>分组</th>
                <th>用例数</th>
                <th>均分</th>
                <th>规则/LLM</th>
                <th>路径覆盖</th>
                <th>违规</th>
                <th>D/F 级</th>
              </tr>
            </thead>
            <tbody>
              {planGroupRows.map((row) => (
                <tr key={row.group}>
                  <td>{row.group}</td>
                  <td>{row.count}</td>
                  <td>{row.avgScore}</td>
                  <td>
                    {row.avgRule} / {row.avgLlm}
                  </td>
                  <td>{row.avgFlow}</td>
                  <td>{row.violations}</td>
                  <td>{row.failCount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ),
    });
  }

  sections.push({
    key: "findings",
    title: `${nextSection()}、主要发现`,
    body: (
      <>
        <ol className="eval-test-report-findings">
          {(findings || []).map((f, i) => (
            <li key={i}>
              <strong>{f.title}</strong>
              <p>{f.body}</p>
            </li>
          ))}
        </ol>
        {improvementRows?.length ? (
          <>
            <h3>评委高频改进建议</h3>
            <ul className="eval-test-report-list">
              {improvementRows.map((imp, i) => (
                <li key={i}>
                  {imp.count > 1 ? `（${imp.count} 例）` : ""}
                  {imp.text}
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </>
    ),
  });

  sections.push({
    key: "conclusions",
    title: `${nextSection()}、结论与改进建议`,
    body: (
      <>
        <h3>结论</h3>
        <ul className="eval-test-report-list">
          {(conclusions || []).map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
        <h3>改进建议</h3>
        <ol className="eval-test-report-recommendations">
          {(recommendations || []).map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ol>
        {weakCases.length > 0 ? (
          <>
            <h3>待重点关注用例（低分 / D·F 级）</h3>
            <table className="eval-test-report-table eval-test-report-table-wide eval-test-report-table-weak">
              <thead>
                <tr>
                  <th>路径</th>
                  <th>角色</th>
                  <th>总分</th>
                  <th>等级</th>
                  <th>规则/LLM</th>
                  <th>路径覆盖</th>
                  <th>终止</th>
                  <th>违规</th>
                  <th>主要问题</th>
                </tr>
              </thead>
              <tbody>
                {weakCases.map((c) => (
                  <tr key={`${c.path_id}-${c.persona}-${c.score}`}>
                    <td>{c.path_id}</td>
                    <td>{c.persona}</td>
                    <td>{c.score}</td>
                    <td>{c.grade}</td>
                    <td>
                      {c.rule_score}/{c.llm_score}
                    </td>
                    <td>{c.flow_adherence}</td>
                    <td className="eval-test-report-cell-muted">{c.termination}</td>
                    <td>{c.violation_count}</td>
                    <td className="eval-test-report-issue">{c.top_issue}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}
      </>
    ),
  });

  const displayTitle = header?.title || REPORT_TITLE;

  return (
    <article className="eval-test-report" aria-label="评测测试报告">
      <header className="eval-test-report-header" data-pdf-section>
        <div className="eval-test-report-brand">
          <span className="eval-test-report-badge">{REPORT_PRODUCT} · 复杂指令评测</span>
          <h1 className="eval-test-report-title">{displayTitle}</h1>
          <p className="eval-test-report-subtitle">{header.subtitle}</p>
        </div>
        <dl className="eval-test-report-meta">
          <div>
            <dt>报告日期</dt>
            <dd>{header.reportDate}</dd>
          </div>
          <div>
            <dt>被测对象</dt>
            <dd>{header.modelName}</dd>
          </div>
          <div>
            <dt>数据集</dt>
            <dd>{header.datasetId}</dd>
          </div>
          <div>
            <dt>用例规模</dt>
            <dd>
              {header.caseCount} 例
              {header.pathCount != null ? ` / ${header.pathCount} 路径` : ""}
            </dd>
          </div>
          <div className="eval-test-report-verdict-cell">
            <dt>综合评定</dt>
            <dd>
              <span className={`eval-verdict eval-verdict-${verdict.level}`}>{verdict.level}</span>
            </dd>
          </div>
        </dl>
      </header>

      {sections.map((sec) => (
        <section key={sec.key} className="eval-test-report-section" data-pdf-section>
          <h2>{sec.title}</h2>
          {sec.body}
        </section>
      ))}
    </article>
  );
}

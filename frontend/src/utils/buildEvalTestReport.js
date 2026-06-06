import {
  dimLabel,
  enrichRuleDescription,
  personaLabel,
  planGroupDisplayLabel,
  terminationLabel,
  violationTypeLabel,
} from "./scoringAnalytics.js";

function overallVerdict(avg) {
  const n = Number(avg);
  if (Number.isNaN(n)) return { level: "—", summary: "暂无有效总分数据。" };
  if (n >= 90) {
    return {
      level: "优秀",
      summary: "模型在复杂指令场景下整体表现优秀，多数用例达到 A 级，可进入小范围灰度或定向优化阶段。",
    };
  }
  if (n >= 80) {
    return {
      level: "良好",
      summary: "模型整体达到良好水平，主流程与话术基本可靠，但仍有可优化的维度与规则合规问题。",
    };
  }
  if (n >= 70) {
    return {
      level: "合格",
      summary: "模型达到基本可用标准，建议在关键薄弱维度与高频违规项上优先整改后再扩大覆盖。",
    };
  }
  if (n >= 60) {
    return {
      level: "待改进",
      summary: "模型尚未稳定达标，存在较多流程、话术或知识类问题，需针对性迭代与复测。",
    };
  }
  return {
    level: "不达标",
    summary: "模型当前综合表现未达上线要求，建议暂停放量，按主要发现逐项修复后重新全量评测。",
  };
}

function pct(part, total) {
  if (!total) return 0;
  return Math.round((part / total) * 1000) / 10;
}

function collectImprovements(reports, limit = 8) {
  const freq = new Map();
  for (const r of reports || []) {
    const items = [];
    if (r.top_improvement) items.push(String(r.top_improvement).trim());
    for (const s of r.improvement_suggestions || []) {
      const t = String(s || "").trim();
      if (t) items.push(t);
    }
    for (const t of items) {
      if (t.length < 4) continue;
      freq.set(t, (freq.get(t) || 0) + 1);
    }
  }
  return [...freq.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([text, count]) => ({ text, count }));
}

function flowPct(rate) {
  if (rate == null || Number.isNaN(Number(rate))) return "—";
  const n = Number(rate);
  const val = n <= 1 ? n * 100 : n;
  return `${Math.round(val * 10) / 10}%`;
}

export function buildEvalTestReport({
  summary = {},
  meta = {},
  analytics = {},
  reports = [],
  datasetName,
  datasetId,
  layer1Summary,
}) {
  const count = summary.count ?? reports.length;
  const avg = Number(summary.average_score);
  const grades = summary.grade_distribution || {};
  const dimAvg = summary.dimension_averages || {};
  const verdict = overallVerdict(avg);

  const weightRule = meta.weight_rule ?? "0.4";
  const weightLlm = meta.weight_llm ?? "0.6";
  const modelName = meta.model_name || meta.model || "被测对话模型";
  const reportDate = new Date().toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const passCount = (grades.A || 0) + (grades.B || 0);
  const failCount = (grades.D || 0) + (grades.F || 0);
  const violationCases = analytics.casesWithViolations ?? 0;
  const totalViolations = analytics.totalViolations ?? 0;
  const ruleDeductionCases = analytics.casesWithRuleDeduction ?? violationCases;
  const pathGapCases = analytics.pathCoverageGapCases ?? 0;
  const runtimeCases = analytics.runtimeViolationCases ?? 0;
  const scoreSummary = analytics.scoreSummary || {};

  const dimSorted = Object.entries(dimAvg).sort((a, b) => b[1] - a[1]);
  const topDim = dimSorted[0];
  const lowDim = dimSorted[dimSorted.length - 1];

  const personaStats = analytics.personaStats || [];
  const pathStats = analytics.pathStats || [];
  const bestPersona = personaStats[0];
  const worstPersona = personaStats[personaStats.length - 1];
  const worstPaths = [...pathStats].sort((a, b) => a.avgScore - b.avgScore).slice(0, 8);
  const bestPaths = pathStats.slice(0, 5);

  const ruleFailures = analytics.ruleFailures || [];
  const violationTypes = analytics.violationTypes || [];
  const termStats = analytics.terminationStats || [];
  const planGroupStats = analytics.planGroupStats || [];
  const hasContradictionAnnotation = analytics.hasContradictionAnnotation ?? analytics.hasControlGroup;

  const findings = [];

  if (count > 0) {
    findings.push({
      title: "综合得分与等级分布",
      body: `共执行 ${count} 个测试用例，加权综合均分 ${Number.isNaN(avg) ? "—" : avg.toFixed(1)} 分，综合评定为「${verdict.level}」。其中 A/B 级 ${passCount} 例（${pct(passCount, count)}%），D/F 级 ${failCount} 例（${pct(failCount, count)}%）。规则均分 ${scoreSummary.avgRule ?? "—"}，LLM 均分 ${scoreSummary.avgLlm ?? "—"}；计分采用规则分×${weightRule} + LLM 评委分×${weightLlm}。`,
    });
  }

  if (scoreSummary.avgFlowAdherence != null) {
    findings.push({
      title: "路径覆盖与流程遵循",
      body: `平均路径节点覆盖率 ${scoreSummary.avgFlowAdherence}%，${scoreSummary.fullPathCoverage ?? 0} 个用例达到 100% 完整覆盖（占有效样本 ${scoreSummary.fullPathCoveragePct ?? 0}%）。流程遵循维度均分 ${dimAvg.flow_adherence != null ? Number(dimAvg.flow_adherence).toFixed(1) : "—"}，是当前最需关注的硬指标之一。`,
    });
  }

  if (lowDim) {
    findings.push({
      title: "能力维度短板",
      body: `六维评测中，「${dimLabel(lowDim[0])}」均分最低（${Number(lowDim[1]).toFixed(1)}），「${dimLabel(topDim?.[0])}」相对最高（${Number(topDim?.[1] ?? 0).toFixed(1)}）。建议优先针对低分维度对应的 Rubric 条目做话术与流程补强。`,
    });
  }

  if (violationCases > 0) {
    const ruleLines = ruleFailures
      .slice(0, 5)
      .map(
        (r) =>
          `「${r.constraint_id}」${r.description || ""}（${r.count} 次，扣 ${Math.round(r.totalDeduction * 10) / 10} 分）`,
      )
      .join("；");
    const typeLines = violationTypes
      .slice(0, 4)
      .map((v) => `${v.label} ${v.count} 次`)
      .join("、");
    findings.push({
      title: "规则合规与硬约束",
      body: `${ruleDeductionCases} 个用例规则分低于满分；共记录 ${totalViolations} 条违规（涉及 ${violationCases} 个用例，其中 ${pathGapCases} 例路径未 100% 覆盖、${runtimeCases} 例含话术/流程类违规，单用例可同时有多条）。类型分布：${typeLines || "—"}。高频项：${ruleLines || "见下表"}。`,
    });
  } else {
    findings.push({
      title: "规则合规与硬约束",
      body: "本轮测试未记录到规则引擎扣分项，规则分均为满分；仍需结合 LLM 维度分审视流程与表达质量。",
    });
  }

  if (personaStats.length >= 2 && bestPersona && worstPersona) {
    const gap = Math.round((bestPersona.avgScore - worstPersona.avgScore) * 10) / 10;
    findings.push({
      title: "用户角色差异",
      body: `${bestPersona.label} 均分最高（${bestPersona.avgScore}，规则 ${bestPersona.avgRule} / LLM ${bestPersona.avgLlm}），${worstPersona.label} 最低（${worstPersona.avgScore}），分差约 ${gap} 分。${worstPersona.label} 场景违规 ${worstPersona.violations} 次，需重点验证。`,
    });
  }

  if (worstPaths.length) {
    const lines = worstPaths
      .slice(0, 4)
      .map((p) => `${p.path_id}（均分 ${p.avgScore}，${p.count} 例，违规 ${p.violations} 次）`)
      .join("；");
    findings.push({
      title: "薄弱测试路径",
      body: `均分最低的路径包括：${lines}。建议对照 Layer2 对话回放，检查该路径节点是否被跳过或话术拆分不当。`,
    });
  }

  if (hasContradictionAnnotation && planGroupStats.length >= 2) {
    const semantic = planGroupStats.find((g) => g.group === "semantic");
    const contradiction = planGroupStats.find((g) => g.group === "contradiction" || g.group === "control");
    if (semantic && contradiction) {
      findings.push({
        title: "语义标注分组观察",
        body: `语义匹配 ${semantic.count} 例均分 ${semantic.avgScore}，可能语义矛盾 ${contradiction.count} 例均分 ${contradiction.avgScore}（全路径×全角色覆盖下的标注，非额外对照跑数）。矛盾标注组 D/F 级 ${contradiction.failCount} 例，违规 ${contradiction.violations} 次；若两组得分接近，说明在非常态组合下 Bot 仍可能「蒙混过关」，需加强路径约束检测。`,
      });
    }
  }

  if (termStats.length) {
    const topTerm = termStats[0];
    findings.push({
      title: "对话终止情况",
      body: `对话终止以「${topTerm.label}」为主（${topTerm.count} 例，${pct(topTerm.count, count)}%）。${termStats.length > 1 ? `其余：${termStats.slice(1, 4).map((t) => `${t.label} ${t.count} 例`).join("、")}。` : ""}非正常终止（拒绝/硬违规/运行错误）占比过高时需排查仿真与 Bot 策略。`,
    });
  }

  const improvements = collectImprovements(reports);
  const recommendations = [];

  if (failCount > 0) {
    recommendations.push(
      `对 ${failCount} 个 D/F 级用例做人工复盘，对照路径设计与 Judge 证据链定位根因。`,
    );
  }
  if (scoreSummary.avgFlowAdherence != null && scoreSummary.avgFlowAdherence < 85) {
    recommendations.push(
      `路径覆盖率仅 ${scoreSummary.avgFlowAdherence}%，优先修复 flow_miss / flow_incomplete 类违规，确保 F1–F4 节点按序完整输出。`,
    );
  }
  if (lowDim && Number(lowDim[1]) < 75) {
    recommendations.push(
      `围绕「${dimLabel(lowDim[0])}」补充训练样本或 Prompt 约束，并在 Layer2 对话中增加该维度的抽检。`,
    );
  }
  for (const r of ruleFailures.slice(0, 4)) {
    recommendations.push(
      `治理规则 ${r.constraint_id}：${enrichRuleDescription(r.constraint_id, r.text, r.violation_type)}（${r.count} 次）`,
    );
  }
  for (const imp of improvements.slice(0, 5)) {
    recommendations.push(
      imp.count > 1 ? `（${imp.count} 例提及）${imp.text}` : imp.text,
    );
  }
  if (!recommendations.length) {
    recommendations.push("维持当前策略，定期复测并跟踪维度均分与违规率变化。");
  }

  const weakCases = [...reports]
    .filter((r) => ["D", "F"].includes(r.grade) || Number(r.total_score) < 70)
    .sort((a, b) => Number(a.total_score) - Number(b.total_score))
    .slice(0, 12)
    .map((r) => ({
      path_id: r.path_id,
      persona: personaLabel(r.persona_type),
      score: Number(r.total_score).toFixed(1),
      grade: r.grade,
      rule_score: r.rule_score != null ? Number(r.rule_score).toFixed(1) : "—",
      llm_score: r.llm_score != null ? Number(r.llm_score).toFixed(1) : "—",
      flow_adherence: flowPct(r.flow_adherence_rate),
      termination: terminationLabel(r.termination_reason),
      violation_count: (r.violations || []).length,
      plan_group: planGroupDisplayLabel(r.plan_group),
      top_issue:
        r.top_improvement ||
        r.judge_comment?.slice(0, 80) ||
        r.violations?.[0]?.constraint_text ||
        "—",
    }));

  const pathCount = layer1Summary?.path_count ?? layer1Summary?.paths ?? null;

  return {
    header: {
      title: "CallEval 复杂指令对话模型评测报告",
      subtitle: datasetName || datasetId || "Eval1 测试集",
      reportDate,
      modelName,
      datasetId: datasetId || "—",
      caseCount: count,
      pathCount: typeof pathCount === "number" ? pathCount : null,
    },
    verdict,
    executiveSummary: [
      `本次对「${modelName}」在「${datasetName || datasetId || "指定数据集"}」上完成 ${count} 条复杂指令对话测试。综合均分 ${Number.isNaN(avg) ? "—" : avg.toFixed(1)}，评定等级：${verdict.level}。`,
      verdict.summary,
      scoreSummary.avgFlowAdherence != null
        ? `路径节点平均覆盖率 ${scoreSummary.avgFlowAdherence}%，100% 覆盖 ${scoreSummary.fullPathCoverage ?? 0} 例（${scoreSummary.fullPathCoveragePct ?? 0}%）。`
        : null,
      violationCases > 0
        ? `${ruleDeductionCases} 个用例规则分被扣减，共 ${totalViolations} 条违规记录（${violationCases} 例至少 1 条；路径未完整覆盖 ${pathGapCases} 例）。`
        : "规则引擎未记录扣分，上线评估可主要依据 LLM 六维能力与等级分布。",
    ].filter(Boolean),
    testOverview: {
      scope: count
        ? `覆盖 ${count} 条测试用例${pathCount != null ? `，对应 Layer1 路径规划 ${pathCount} 条` : ""}，为路径×全角色笛卡尔积${hasContradictionAnnotation ? "（部分组合标注可能语义矛盾）" : ""}。`
        : "暂无用例数据。",
      method:
        "采用 Eval1 三层评测：Layer1 知识图谱与路径规划 → Layer2 多角色对话仿真 → Layer3 规则分 + LLM Rubric 六维评分。",
      scoring: `总分 = 规则分 × ${weightRule} + LLM 分 × ${weightLlm}，等级按总分区间映射 A–F。`,
    },
    scoreSummary: {
      avgTotal: Number.isNaN(avg) ? null : Math.round(avg * 10) / 10,
      avgRule: scoreSummary.avgRule,
      avgLlm: scoreSummary.avgLlm,
      avgFlowAdherence: scoreSummary.avgFlowAdherence,
      fullPathCoverage: scoreSummary.fullPathCoverage,
      fullPathCoveragePct: scoreSummary.fullPathCoveragePct,
      weightRule,
      weightLlm,
    },
    gradeRows: Object.entries(grades)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([grade, n]) => ({
        grade,
        count: n,
        percent: pct(n, count),
      })),
    dimensionRows: dimSorted.map(([key, val]) => ({
      dimension: dimLabel(key),
      key,
      score: Math.round(Number(val) * 10) / 10,
    })),
    personaRows: personaStats.map((p) => ({
      persona: p.label,
      count: p.count,
      avgScore: p.avgScore,
      avgRule: p.avgRule,
      avgLlm: p.avgLlm,
      violations: p.violations,
    })),
    pathRows: pathStats.map((p) => ({
      path_id: p.path_id,
      count: p.count,
      avgScore: p.avgScore,
      violations: p.violations,
    })),
    ruleFailureRows: ruleFailures.slice(0, 12).map((r) => ({
      id: r.constraint_id,
      description: r.description || enrichRuleDescription(r.constraint_id, r.text, r.violation_type),
      count: r.count,
      deduction: Math.round(r.totalDeduction * 10) / 10,
      type: violationTypeLabel(r.violation_type) || r.violation_type || "—",
    })),
    violationTypeRows: violationTypes.map((v) => ({
      type: v.label,
      count: v.count,
      percent: pct(v.count, totalViolations),
    })),
    terminationRows: termStats.map((t) => ({
      reason: t.label,
      count: t.count,
      percent: pct(t.count, count),
    })),
    planGroupRows: planGroupStats.map((g) => ({
      group: g.label,
      count: g.count,
      avgScore: g.avgScore,
      avgRule: g.avgRule,
      avgLlm: g.avgLlm,
      avgFlow: g.avgFlow != null ? `${g.avgFlow}%` : "—",
      violations: g.violations,
      failCount: g.failCount,
    })),
    improvementRows: improvements,
    findings,
    conclusions: [
      `综合结论：模型本轮评测结果为「${verdict.level}」${Number.isNaN(avg) ? "" : `（均分 ${avg.toFixed(1)}）`}。`,
      scoreSummary.avgFlowAdherence != null && scoreSummary.avgFlowAdherence < 80
        ? `路径覆盖率 ${scoreSummary.avgFlowAdherence}% 偏低，流程类问题是当前主要风险。`
        : null,
      failCount > 0
        ? `存在 ${failCount} 个低等级用例，不建议在未修复前全量发布。`
        : "低等级用例占比较低，可在修复已知违规项后安排回归测试。",
      bestPersona && worstPersona
        ? `角色维度上需关注 ${worstPersona.label} 场景；规则与流程类问题请对照 Layer2 对话与违规明细。`
        : null,
    ].filter(Boolean),
    recommendations: [...new Set(recommendations)],
    weakCases,
    bestPaths: bestPaths.map((p) => ({
      path_id: p.path_id,
      avgScore: p.avgScore,
      count: p.count,
    })),
  };
}

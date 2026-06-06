/** Offline recalc path coverage from saved Layer2 dialogues (mirrors eval1/report/recalc_coverage.py). */

export const FLOW_COVERAGE_VIOLATION_THRESHOLD = 0.85;

const INTERRUPTION_NODES = new Set([
  "OBJECTION",
  "F3_RETAIN",
  "FAQ_NORMAL",
  "FAQ_OOB",
  "OBJ_FINAL",
]);

export function parseBotActionSteps(botActionLog) {
  const steps = new Set();
  for (const entry of botActionLog || []) {
    const text = String(entry || "");
    if (!text) continue;
    if (text.includes("opening_line")) steps.add("OPENING");
    if (text.includes(":")) {
      const step = text.split(":").pop()?.trim();
      if (step) steps.add(step);
    }
  }
  return steps;
}

export function inferCoveredNodes(dialogue) {
  const covered = [];
  for (const entry of dialogue?.bot_state_log || []) {
    const sid = String(entry?.current_step_id || "").trim();
    if (sid && !covered.includes(sid)) covered.push(sid);
  }
  return covered;
}

export function mergeEffectiveCoverage(pathNodes, coveredNodes, botActionLog) {
  const visited = new Set((coveredNodes || []).filter(Boolean));
  for (const s of parseBotActionSteps(botActionLog)) visited.add(s);
  if (visited.has("OPENING") && pathNodes.includes("F1")) visited.add("F1");
  if (visited.has("CLOSING") || visited.has("END")) visited.add("CLOSING");
  return visited;
}

export function getApplicablePathNodes(pathNodes, visited) {
  const core = (pathNodes || []).filter((n) => n !== "START" && n !== "END");
  if (!core.length) return [];
  const applicable = [];
  for (const node of core) {
    if (INTERRUPTION_NODES.has(node)) {
      if (visited.has(node)) applicable.push(node);
      continue;
    }
    applicable.push(node);
  }
  return applicable;
}

export function recalcFlowAdherence(dialogue) {
  const pathNodes = dialogue?.path_nodes || [];
  if (!pathNodes.length) return Number(dialogue?.flow_adherence_rate ?? 1);
  const covered = inferCoveredNodes(dialogue);
  const log = dialogue?.bot_state?.bot_action_log || [];
  const visited = mergeEffectiveCoverage(pathNodes, covered, log);
  const applicable = getApplicablePathNodes(pathNodes, visited);
  if (!applicable.length) return 1;
  const hit = applicable.filter((n) => visited.has(n)).length;
  return hit / applicable.length;
}

function runtimeViolations(violations) {
  return (violations || []).filter((v) => v?.violation_type !== "flow_miss");
}

function flowMissViolation(pathId, flow, messageCount) {
  return {
    turn_index: Math.max(1, Math.floor((messageCount || 0) / 2)),
    violation_type: "flow_miss",
    constraint_id: pathId,
    constraint_text: `测试路径 ${pathId} 未按设计节点完整覆盖`,
    bot_utterance: "",
    explanation: `路径节点覆盖率 ${Math.round(flow * 1000) / 10}%（低于 ${FLOW_COVERAGE_VIOLATION_THRESHOLD * 100}% 阈值，修正口径）`,
    deduction: Math.round((1 - flow) * 20 * 100) / 100,
  };
}

function estimateRuleScore({
  violations,
  flow,
  repetitiveBotCount,
  openingLineMatch,
}) {
  let totalDeduction = 0;
  const seen = new Set();
  for (const v of violations) {
    const key = `${v.constraint_id}:${v.turn_index}`;
    if (seen.has(key)) continue;
    seen.add(key);
    let ded = Number(v.deduction || 0);
    if (ded <= 0) {
      const vt = v.violation_type || "";
      if (vt === "hard_boundary") ded = 20;
      else if (vt === "dialogue_length") ded = 7;
      else if (vt === "flow_miss") ded = Math.max(5, (1 - flow) * 20);
      else if (vt === "flow_incomplete") ded = 10;
      else ded = 5;
    }
    totalDeduction += ded;
  }
  if (flow < 0.6) totalDeduction += 10;
  else if (flow < FLOW_COVERAGE_VIOLATION_THRESHOLD) totalDeduction += 5;
  if ((repetitiveBotCount || 0) > 0) {
    totalDeduction += Math.min(15, repetitiveBotCount * 4);
  }
  if (!openingLineMatch) totalDeduction += 8;
  return Math.max(0, Math.round((100 - totalDeduction) * 100) / 100);
}

function gradeForScore(total) {
  if (total >= 90) return "A";
  if (total >= 80) return "B";
  if (total >= 70) return "C";
  if (total >= 60) return "D";
  return "F";
}

function aggregateTotal(ruleScore, llmScore, weightRule = 0.4, weightLlM = 0.6) {
  const total = Math.max(0, Math.min(100, ruleScore * weightRule + llmScore * weightLlM));
  return {
    total_score: Math.round(total * 100) / 100,
    grade: gradeForScore(total),
    score_breakdown: `规则分=${ruleScore}×${weightRule}+LLM分=${llmScore}×${weightLlM} => ${Math.round(total * 100) / 100} (${gradeForScore(total)}) [修正口径]`,
  };
}

/** Patch one report+dialogue merge with recalculated coverage metrics. */
export function recalcReportRecord(report, dialogue, meta = {}) {
  if (!dialogue?.path_nodes?.length) return report;
  const weightRule = Number(meta.weight_rule ?? 0.4);
  const weightLlm = Number(meta.weight_llm ?? 0.6);
  const newFlow = recalcFlowAdherence(dialogue);
  const pathId = report.path_id || dialogue.path_id || "?";

  let violations = runtimeViolations(report.violations);
  if (newFlow < FLOW_COVERAGE_VIOLATION_THRESHOLD) {
    violations = [
      ...violations,
      flowMissViolation(pathId, newFlow, (dialogue.messages || []).length),
    ];
  }

  const ruleScore = estimateRuleScore({
    violations,
    flow: newFlow,
    repetitiveBotCount: dialogue.repetitive_bot_count ?? report.repetitive_bot_count,
    openingLineMatch: dialogue.opening_line_match ?? report.opening_line_match,
  });
  const llmScore = Number(report.llm_score ?? dialogue.llm_score ?? 0);
  const agg = aggregateTotal(ruleScore, llmScore, weightRule, weightLlm);

  return {
    ...report,
    ...dialogue,
    flow_adherence_rate: Math.round(newFlow * 1000) / 1000,
    flow_adherence_rate_legacy: report.flow_adherence_rate,
    violations,
    rule_score: ruleScore,
    total_score: agg.total_score,
    grade: agg.grade,
    score_breakdown: agg.score_breakdown,
    coverage_recalc_applied: true,
  };
}

/** Recalc all reports when layer2 dialogues are present. */
export function recalcReportsFromDialogues(reports, dialogues, meta = {}) {
  const byId = {};
  for (const d of dialogues || []) {
    if (d?.report_id) byId[d.report_id] = d;
  }
  return (reports || []).map((r) => {
    const d = byId[r.report_id];
    return d ? recalcReportRecord(r, d, meta) : r;
  });
}

export function buildRecalcSummary(reports, recalcReports) {
  const oldFm = (reports || []).filter((r) =>
    (r.violations || []).some((v) => v.violation_type === "flow_miss"),
  ).length;
  const newFm = (recalcReports || []).filter((r) =>
    (r.violations || []).some((v) => v.violation_type === "flow_miss"),
  ).length;
  const avg = (list) => {
    if (!list?.length) return null;
    return Math.round((list.reduce((s, r) => s + Number(r.total_score || 0), 0) / list.length) * 10) / 10;
  };
  return {
    flowMissOld: oldFm,
    flowMissNew: newFm,
    avgOld: avg(reports),
    avgNew: avg(recalcReports),
  };
}

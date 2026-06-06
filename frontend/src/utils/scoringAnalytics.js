/** Aggregate eval reports for multi-angle Layer3 analytics. */

export const DIM_LABELS = {
  flow_adherence: "流程遵循",
  dialogue_compliance: "话术合规",
  knowledge_accuracy: "知识准确",
  retention_effectiveness: "挽留效果",
  boundary_handling: "边界处理",
  naturalness: "自然度",
};

export function dimLabel(key) {
  return DIM_LABELS[key] || key;
}

export const PERSONA_LABELS = {
  cooperative: "配合型",
  impatient: "急躁型",
  resistant: "抵触型",
  questioning: "质疑型",
  ignorant: "懵懂型",
  off_topic: "跑题型",
};

/** Persona type → display icon (emoji). */
export const PERSONA_ICONS = {
  cooperative: "🤝",
  impatient: "⚡",
  resistant: "🛡️",
  questioning: "❓",
  ignorant: "🤔",
  off_topic: "💭",
};

export function personaIcon(type) {
  return PERSONA_ICONS[type] || "👤";
}

function normalizePersonaEmotion(type, emotion) {
  const t = String(type || "");
  let e = String(emotion || "").trim();
  if (t === "impatient") {
    e = e.replace(/嫌站长啰嗦/g, "嫌啰嗦");
  }
  return e;
}

export const TERMINATION_LABELS = {
  goal_achieved: "目标达成",
  max_turns: "轮次上限",
  user_refused: "用户拒绝",
  hangup: "挂断",
  hard_violation: "硬边界违规",
  runner_error: "运行错误",
  plan_timeout: "计划超时",
};

export function personaLabel(type) {
  return PERSONA_LABELS[type] || type || "未知角色";
}

export function isPotentialSemanticContradiction(planGroup) {
  return planGroup === "potential_contradiction" || planGroup === "control_contradictory";
}

export function planGroupAnalyticsKey(planGroup) {
  return isPotentialSemanticContradiction(planGroup) ? "contradiction" : "semantic";
}

export function planGroupDisplayLabel(planGroup) {
  if (planGroup === "potential_contradiction") return "可能语义矛盾";
  if (planGroup === "control_contradictory") return "语义矛盾（旧对照）";
  if (planGroup === "semantic_match") return "语义匹配";
  return "—";
}

/** Bot-side rule violations should attach to Bot message turns. */
const BOT_VIOLATION_TYPES = new Set(["dialogue_length", "hard_boundary"]);

export function resolveViolationTurn(v, messages) {
  const t = Number(v?.turn_index);
  if (!Number.isFinite(t) || !Array.isArray(messages) || !messages.length) return t;
  const vtype = String(v?.violation_type || "");
  if (!BOT_VIOLATION_TYPES.has(vtype)) return t;

  const msgAtT = messages.find((m) => Number(m?.turn) === t);
  const role = String(msgAtT?.role || "").toLowerCase();
  if (role === "bot") return t;

  const botText = String(v?.bot_utterance || "").trim();
  if (botText) {
    const exact = messages.find(
      (m) => String(m?.role || "").toLowerCase() === "bot" && String(m?.content || "") === botText
    );
    if (exact) return Number(exact.turn);
  }

  let fallback = t;
  for (const m of messages) {
    const turn = Number(m?.turn);
    if (!Number.isFinite(turn) || turn > t) continue;
    if (String(m?.role || "").toLowerCase() === "bot") fallback = turn;
  }
  return fallback;
}

export function violationsByTurnMap(violations, messages) {
  const map = new Map();
  for (const v of violations || []) {
    const t = resolveViolationTurn(v, messages);
    if (!Number.isFinite(t)) continue;
    if (!map.has(t)) map.set(t, []);
    map.get(t).push(v);
  }
  return map;
}

export function personaBrief(card) {
  if (!card || typeof card !== "object") return null;
  const type = card.persona_type;
  return {
    type,
    icon: personaIcon(type),
    label: personaLabel(type),
    emotion: normalizePersonaEmotion(type, card.emotion_description),
    patterns: Array.isArray(card.utterance_patterns) ? card.utterance_patterns : [],
    fragment: String(card.system_prompt_fragment || "").trim(),
  };
}

export function terminationLabel(reason) {
  return TERMINATION_LABELS[reason] || reason || "其他";
}

const VIOLATION_TYPE_LABELS = {
  flow_miss: "流程未覆盖（路径级）",
  dialogue_length: "话术超长",
  hard_boundary: "硬边界",
  flow_incomplete: "流程步骤未完成",
  plan_timeout: "执行超时",
  runner_error: "运行错误",
};

const VIOLATION_TYPE_HELP = {
  flow_miss:
    "Bot 未按本用例「测试路径」设计的节点顺序完整走完；标识为 P* 的是路径编号，不是单条话术规则。",
  dialogue_length: "某轮 Bot 回复超过字数上限（如 D_LEN：每轮不超过 30 字）。",
  hard_boundary: "触犯业务硬边界（如承诺不支持的能力）。",
  flow_incomplete: "进入了某流程步（如 F4）但未说全该步要求的要点。",
};

const RULE_ID_HINTS = {
  D_LEN: "每轮 Bot 话术不超过 30 字（Opening Line 除外）",
  "B*": "边界约束：不得宣称不支持的能力",
  F4: "流程第 4 步须完整覆盖",
};

/** Human-readable rule text for charts / tooltips. */
export function enrichRuleDescription(constraintId, text, violationType) {
  const id = String(constraintId || "?");
  const raw = String(text || "").trim();
  const vt = String(violationType || "");

  if (RULE_ID_HINTS[id]) return RULE_ID_HINTS[id];

  if (raw && !/^path not fully/i.test(raw) && !/^flow adherence/i.test(raw)) {
    return raw;
  }

  if (/^P\d+$/i.test(id)) {
    return `测试路径 ${id} 未按设计步骤完整执行（路径覆盖不足）`;
  }

  if (vt && VIOLATION_TYPE_LABELS[vt]) {
    const base = VIOLATION_TYPE_LABELS[vt];
    if (raw) return `${base}：${raw}`;
    return `${base}（${id}）`;
  }

  return raw || vt || id;
}

export function violationTypeLabel(vt) {
  return VIOLATION_TYPE_LABELS[vt] || vt || "";
}

function parseFlowAdherenceRate(v, ctx = {}) {
  if (ctx.flowAdherenceRate != null && !Number.isNaN(Number(ctx.flowAdherenceRate))) {
    return Number(ctx.flowAdherenceRate);
  }
  const m = String(v?.explanation || "").match(/([\d.]+)/);
  if (!m) return null;
  const n = Number(m[1]);
  if (Number.isNaN(n)) return null;
  if (n <= 1) return n;
  if (n <= 100) return n / 100;
  return null;
}

/**
 * Structured violation copy for Layer2 / Layer3 UI (Chinese, path-aware).
 */
export function formatViolationDisplay(v, ctx = {}) {
  const id = String(v?.constraint_id || v?.constraint_ref || "?");
  const vt = String(v?.violation_type || "");
  const vtLabel = violationTypeLabel(vt);
  const typeHelp = VIOLATION_TYPE_HELP[vt] || "";
  const pathMeta = ctx.pathMeta || null;
  const flowRate = parseFlowAdherenceRate(v, ctx);
  const pct =
    flowRate != null ? `${Math.round(flowRate * 1000) / 10}%` : null;

  if (vt === "flow_miss" && /^P\d+$/i.test(id)) {
    const expectedPath = pathMeta?.nodes?.length ? pathMeta.nodes.join(" → ") : null;
    return {
      badge: "路径覆盖",
      title: `测试路径 ${id} 未按设计完整执行`,
      typeLabel: vtLabel,
      idNote: `「${id}」是本用例的测试路径编号（对应上方路径说明），不是 D_LEN / F4 等单条规则 ID`,
      body:
        typeHelp +
        (pct
          ? ` 当前路径节点覆盖率约 ${pct}（满分要求 100%）。`
          : " 当前路径节点覆盖率未达到 100%。") +
        (expectedPath ? ` 期望顺序：${expectedPath}` : ""),
      expectedPath,
    };
  }

  const desc = enrichRuleDescription(id, v.constraint_text, vt);
  const title =
    RULE_ID_HINTS[id] && id.length <= 8
      ? `${id} · ${RULE_ID_HINTS[id]}`
      : desc.length <= 48
        ? desc
        : `${id} · ${desc.slice(0, 48)}…`;

  return {
    badge: vtLabel || "规则违规",
    title,
    typeLabel: vtLabel,
    idNote: /^P\d+$/i.test(id) ? `路径编号 ${id}` : `规则/约束 ${id}`,
    body: [typeHelp, desc !== title ? desc : ""].filter(Boolean).join(" ").trim() || desc,
    expectedPath: null,
  };
}

export function buildScoringAnalytics(reports) {
  const list = Array.isArray(reports) ? reports : [];
  const ruleMap = new Map();
  const typeMap = new Map();
  const personaMap = new Map();
  const terminationMap = new Map();
  const pathMap = new Map();

  let totalViolations = 0;

  for (const r of list) {
    const persona = r.persona_type || "unknown";
    if (!personaMap.has(persona)) {
      personaMap.set(persona, {
        persona_type: persona,
        label: personaLabel(persona),
        count: 0,
        totalScore: 0,
        ruleScoreSum: 0,
        llmScoreSum: 0,
        violations: 0,
      });
    }
    const pe = personaMap.get(persona);
    pe.count += 1;
    pe.totalScore += Number(r.total_score || 0);
    pe.ruleScoreSum += Number(r.rule_score || 0);
    pe.llmScoreSum += Number(r.llm_score || 0);

    const pathId = r.path_id || "?";
    if (!pathMap.has(pathId)) {
      pathMap.set(pathId, {
        path_id: pathId,
        count: 0,
        totalScore: 0,
        violations: 0,
      });
    }
    const pa = pathMap.get(pathId);
    pa.count += 1;
    pa.totalScore += Number(r.total_score || 0);

    const term = r.termination_reason || "unknown";
    terminationMap.set(term, (terminationMap.get(term) || 0) + 1);

    const vlist = Array.isArray(r.violations) ? r.violations : [];
    totalViolations += vlist.length;
    pe.violations += vlist.length;
    pa.violations += vlist.length;

    for (const v of vlist) {
      const cid = v.constraint_id || v.constraint_ref || "?";
      if (!ruleMap.has(cid)) {
        ruleMap.set(cid, {
          constraint_id: cid,
          count: 0,
          totalDeduction: 0,
          text: v.constraint_text || "",
          violation_type: v.violation_type || "",
          description: enrichRuleDescription(cid, v.constraint_text, v.violation_type),
        });
      }
      const re = ruleMap.get(cid);
      re.count += 1;
      re.totalDeduction += Number(v.deduction || 0);
      if (!re.text && v.constraint_text) re.text = v.constraint_text;
      if (!re.violation_type && v.violation_type) re.violation_type = v.violation_type;
      re.description = enrichRuleDescription(cid, re.text || v.constraint_text, re.violation_type || v.violation_type);

      const vt = v.violation_type || "other";
      typeMap.set(vt, (typeMap.get(vt) || 0) + 1);
    }
  }

  const personaStats = [...personaMap.values()]
    .map((p) => ({
      ...p,
      avgScore: p.count ? Math.round((p.totalScore / p.count) * 10) / 10 : 0,
      avgRule: p.count ? Math.round((p.ruleScoreSum / p.count) * 10) / 10 : 0,
      avgLlm: p.count ? Math.round((p.llmScoreSum / p.count) * 10) / 10 : 0,
    }))
    .sort((a, b) => b.avgScore - a.avgScore);

  const pathStats = [...pathMap.values()]
    .map((p) => ({
      ...p,
      avgScore: p.count ? Math.round((p.totalScore / p.count) * 10) / 10 : 0,
    }))
    .sort((a, b) => b.avgScore - a.avgScore);

  let ruleSum = 0;
  let llmSum = 0;
  let flowSum = 0;
  let flowCount = 0;
  let fullPathCoverage = 0;
  const planGroupMap = new Map();

  for (const r of list) {
    ruleSum += Number(r.rule_score || 0);
    llmSum += Number(r.llm_score || 0);
    const flow = Number(r.flow_adherence_rate);
    if (!Number.isNaN(flow)) {
      flowSum += flow;
      flowCount += 1;
      if (flow >= 0.999) fullPathCoverage += 1;
    }

    const group = planGroupAnalyticsKey(r.plan_group);
    if (!planGroupMap.has(group)) {
      planGroupMap.set(group, {
        group,
        label: group === "contradiction" ? "可能语义矛盾" : "语义匹配",
        count: 0,
        totalScore: 0,
        ruleScoreSum: 0,
        llmScoreSum: 0,
        flowSum: 0,
        flowCount: 0,
        violations: 0,
        failCount: 0,
      });
    }
    const g = planGroupMap.get(group);
    g.count += 1;
    g.totalScore += Number(r.total_score || 0);
    g.ruleScoreSum += Number(r.rule_score || 0);
    g.llmScoreSum += Number(r.llm_score || 0);
    g.violations += (r.violations || []).length;
    if (["D", "F"].includes(r.grade)) g.failCount += 1;
    if (!Number.isNaN(flow)) {
      g.flowSum += flow;
      g.flowCount += 1;
    }
  }

  const n = list.length;
  const planGroupStats = [...planGroupMap.values()]
    .map((g) => ({
      ...g,
      avgScore: g.count ? Math.round((g.totalScore / g.count) * 10) / 10 : 0,
      avgRule: g.count ? Math.round((g.ruleScoreSum / g.count) * 10) / 10 : 0,
      avgLlm: g.count ? Math.round((g.llmScoreSum / g.count) * 10) / 10 : 0,
      avgFlow:
        g.flowCount ? Math.round((g.flowSum / g.flowCount) * 1000) / 10 : null,
    }))
    .sort((a, b) => (a.group === "semantic" ? -1 : 1));

  let casesWithRuleDeduction = 0;
  let pathCoverageGapCases = 0;
  let materialPathGapCases = 0;
  let runtimeViolationCases = 0;
  const PATH_GAP_THRESHOLD = 0.999;
  const MATERIAL_PATH_GAP = 0.85;
  const RUNTIME_VIOLATION_TYPES = new Set([
    "dialogue_length",
    "hard_boundary",
    "flow_incomplete",
  ]);

  for (const r of list) {
    if (Number(r.rule_score) < 100) casesWithRuleDeduction += 1;
    const flow = Number(r.flow_adherence_rate);
    if (!Number.isNaN(flow) && flow < PATH_GAP_THRESHOLD) pathCoverageGapCases += 1;
    if (!Number.isNaN(flow) && flow < MATERIAL_PATH_GAP) materialPathGapCases += 1;
    const vlist = Array.isArray(r.violations) ? r.violations : [];
    if (vlist.some((v) => RUNTIME_VIOLATION_TYPES.has(v.violation_type))) {
      runtimeViolationCases += 1;
    }
  }

  return {
    ruleFailures: [...ruleMap.values()].sort((a, b) => b.count - a.count),
    violationTypes: [...typeMap.entries()]
      .map(([type, count]) => ({
        type,
        count,
        label: violationTypeLabel(type) || type,
      }))
      .sort((a, b) => b.count - a.count),
    personaStats,
    pathStats,
    terminationStats: [...terminationMap.entries()]
      .map(([reason, count]) => ({
        reason,
        count,
        label: terminationLabel(reason),
      }))
      .sort((a, b) => b.count - a.count),
    scoreSummary: {
      avgRule: n ? Math.round((ruleSum / n) * 10) / 10 : 0,
      avgLlm: n ? Math.round((llmSum / n) * 10) / 10 : 0,
      avgFlowAdherence:
        flowCount ? Math.round((flowSum / flowCount) * 1000) / 10 : null,
      fullPathCoverage,
      fullPathCoveragePct: flowCount
        ? Math.round((fullPathCoverage / flowCount) * 1000) / 10
        : null,
    },
    planGroupStats,
    hasContradictionAnnotation: planGroupMap.has("contradiction"),
    /** @deprecated use hasContradictionAnnotation */
    hasControlGroup: planGroupMap.has("contradiction") || planGroupMap.has("control"),
    totalViolations,
    casesWithViolations: list.filter((r) => (r.violations || []).length > 0).length,
    casesWithRuleDeduction,
    pathCoverageGapCases,
    materialPathGapCases,
    runtimeViolationCases,
    pathCoverageThreshold: MATERIAL_PATH_GAP,
  };
}

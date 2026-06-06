import { useMemo, useState } from "react";
import { ViolationList } from "./ViolationList";

function BotStatePanel({ botState, botStateLog }) {
  const state = botState || {};
  const stateLog = Array.isArray(botStateLog) ? botStateLog : [];
  const slots = state.slot_values || {};
  const repeatGuard = Array.isArray(state.repeat_guard_window) ? state.repeat_guard_window : [];
  const actionLog = Array.isArray(state.bot_action_log) ? state.bot_action_log : [];
  const usedKnowledge = Array.isArray(state.used_knowledge_ids) ? state.used_knowledge_ids : [];
  const latestStates = stateLog.slice(-4);

  return (
    <div
      style={{
        border: "1px solid var(--mist)",
        borderRadius: 8,
        padding: 8,
        background: "rgba(3,7,18,.25)",
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div style={{ fontSize: 12, color: "var(--smoke)" }}>Bot状态快照</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, fontSize: 11 }}>
        <span className="tn" style={{ color: "var(--violet)" }}>
          step: {String(state.current_step_id || "-")}
        </span>
        <span className="tn" style={{ color: "var(--silver)" }}>
          used_knowledge: {usedKnowledge.length}
        </span>
        <span className="tn" style={{ color: "var(--silver)" }}>
          repeat_window: {repeatGuard.length}
        </span>
      </div>
      <div style={{ fontSize: 11, color: "var(--silver)" }}>
        current_step_text: {String(state.current_step_text || "-")}
      </div>
      <div style={{ fontSize: 11, color: "var(--silver)" }}>
        last_bot_utterance: {String(state.last_bot_utterance || "-")}
      </div>
      <details>
        <summary style={{ cursor: "pointer", fontSize: 11, color: "var(--smoke)" }}>
          Slot Values（{Object.keys(slots).length}）
        </summary>
        <div style={{ marginTop: 6, display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", gap: 6 }}>
          {Object.keys(slots).length === 0 ? (
            <div style={{ fontSize: 11, color: "var(--silver)" }}>-</div>
          ) : (
            Object.entries(slots).map(([k, v]) => (
              <div
                key={k}
                style={{
                  border: "1px solid var(--mist)",
                  borderRadius: 6,
                  padding: "4px 6px",
                  fontSize: 11,
                  color: "var(--silver)",
                }}
              >
                {k}: {String(v)}
              </div>
            ))
          )}
        </div>
      </details>
      <details>
        <summary style={{ cursor: "pointer", fontSize: 11, color: "var(--smoke)" }}>
          Bot Action Log（最近{Math.min(8, actionLog.length)}条）
        </summary>
        <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
          {actionLog.slice(-8).map((x, i) => (
            <div key={`act-${i}`} style={{ fontSize: 11, color: "var(--jade)", fontFamily: "var(--mono)" }}>
              {x}
            </div>
          ))}
          {actionLog.length === 0 ? <div style={{ fontSize: 11, color: "var(--silver)" }}>-</div> : null}
        </div>
      </details>
      <details>
        <summary style={{ cursor: "pointer", fontSize: 11, color: "var(--smoke)" }}>
          状态轨迹（最近{latestStates.length}步）
        </summary>
        <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
          {latestStates.map((s, i) => (
            <div
              key={`s-${i}`}
              style={{
                border: "1px solid var(--mist)",
                borderRadius: 6,
                padding: "4px 6px",
                fontSize: 11,
                color: "var(--silver)",
              }}
            >
              {String(s.current_step_id || "-")} · {String(s.current_step_text || "-")}
            </div>
          ))}
          {latestStates.length === 0 ? <div style={{ fontSize: 11, color: "var(--silver)" }}>-</div> : null}
        </div>
      </details>
    </div>
  );
}

export default function Eval1Layer2Panel({ data, loading, onRefresh }) {
  const layer2 = data?.layer2 || {};
  const personas = layer2?.persona_registry || {};
  const plans = Array.isArray(layer2?.plans) ? layer2.plans : [];
  const dialogues = Array.isArray(layer2?.dialogues) ? layer2.dialogues : [];

  const personaKeys = useMemo(() => Object.keys(personas), [personas]);
  const [personaFocus, setPersonaFocus] = useState("");
  const [pathFocus, setPathFocus] = useState("");

  const selectedPersona = personaFocus || personaKeys[0] || "";
  const personaDialogues = useMemo(
    () =>
      dialogues.filter(
        (d) => String(d?.persona_type || "").toLowerCase() === selectedPersona.toLowerCase()
      ),
    [dialogues, selectedPersona]
  );
  const pathKeys = useMemo(
    () => [...new Set(personaDialogues.map((d) => d?.path_id).filter(Boolean))].sort(),
    [personaDialogues]
  );
  const selectedPath = pathFocus || pathKeys[0] || "";
  const records = useMemo(
    () => personaDialogues.filter((d) => String(d?.path_id || "") === String(selectedPath)),
    [personaDialogues, selectedPath]
  );
  const matrix = useMemo(() => {
    const cell = {};
    dialogues.forEach((d) => {
      const p = String(d?.persona_type || "");
      const k = String(d?.path_id || "");
      if (!p || !k) return;
      const id = `${p}::${k}`;
      if (!cell[id]) {
        cell[id] = {
          persona: p,
          path: k,
          count: 0,
          scoreSum: 0,
          turnsSum: 0,
          coveredCount: 0,
        };
      }
      cell[id].count += 1;
      cell[id].scoreSum += Number(d?.total_score || 0);
      cell[id].turnsSum += (d?.messages || []).length;
      cell[id].coveredCount += d?.path_covered ? 1 : 0;
    });
    return Object.values(cell).sort((a, b) =>
      a.persona === b.persona ? a.path.localeCompare(b.path) : a.persona.localeCompare(b.persona)
    );
  }, [dialogues]);

  const exportCsv = () => {
    const rows = [
      [
        "persona_type",
        "path_id",
        "report_id",
        "total_score",
        "grade",
        "termination_reason",
        "path_covered",
        "flow_adherence_rate",
        "forced_action_retry_count",
        "turn_count",
        "messages",
      ],
    ];
    dialogues.forEach((d) => {
      rows.push([
        String(d?.persona_type || ""),
        String(d?.path_id || ""),
        String(d?.report_id || ""),
        String(d?.total_score ?? ""),
        String(d?.grade || ""),
        String(d?.termination_reason || ""),
        String(Boolean(d?.path_covered)),
        String(d?.flow_adherence_rate ?? ""),
        String(d?.forced_action_retry_count ?? 0),
        String((d?.messages || []).length),
        JSON.stringify(d?.messages || []),
      ]);
    });
    const esc = (v) => `"${String(v).replace(/"/g, '""')}"`;
    const csv = rows.map((r) => r.map(esc).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `eval1_layer2_dialogues_${data?.dataset_id || "dataset"}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="card fade-up">
      <div className="card-head">
        <span className="card-icon">🎭</span>
        <span className="card-title">Eval1 Layer2 用户构建与全部对话记录</span>
        <button type="button" className="tn" onClick={onRefresh} style={{ marginLeft: "auto" }}>
          {loading ? "加载中..." : "刷新Layer2"}
        </button>
      </div>
      <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ fontSize: 12, color: "var(--smoke)" }}>
          计划数 {plans.length} · 对话记录 {dialogues.length}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button type="button" className="tn act" onClick={exportCsv} disabled={!dialogues.length}>
            导出CSV
          </button>
        </div>

        <div style={{ border: "1px solid var(--mist)", borderRadius: 8, padding: 8, background: "rgba(3,7,18,.35)" }}>
          <div style={{ fontSize: 12, color: "var(--silver)", marginBottom: 6 }}>
            Persona × Path 矩阵（聚合）
          </div>
          <div style={{ maxHeight: 180, overflowY: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr style={{ color: "var(--smoke)" }}>
                  <th style={{ textAlign: "left", padding: "4px 6px" }}>persona</th>
                  <th style={{ textAlign: "left", padding: "4px 6px" }}>path</th>
                  <th style={{ textAlign: "right", padding: "4px 6px" }}>runs</th>
                  <th style={{ textAlign: "right", padding: "4px 6px" }}>avg_score</th>
                  <th style={{ textAlign: "right", padding: "4px 6px" }}>avg_turns</th>
                  <th style={{ textAlign: "right", padding: "4px 6px" }}>coverage%</th>
                </tr>
              </thead>
              <tbody>
                {matrix.map((m) => {
                  const avgScore = m.count ? (m.scoreSum / m.count).toFixed(1) : "0.0";
                  const avgTurns = m.count ? (m.turnsSum / m.count).toFixed(1) : "0.0";
                  const cov = m.count ? ((m.coveredCount * 100) / m.count).toFixed(0) : "0";
                  return (
                    <tr
                      key={`${m.persona}-${m.path}`}
                      onClick={() => {
                        setPersonaFocus(m.persona);
                        setPathFocus(m.path);
                      }}
                      style={{ cursor: "pointer" }}
                    >
                      <td style={{ padding: "4px 6px", color: "var(--silver)" }}>{m.persona}</td>
                      <td style={{ padding: "4px 6px", color: "var(--violet)" }}>{m.path}</td>
                      <td style={{ padding: "4px 6px", color: "var(--silver)", textAlign: "right" }}>{m.count}</td>
                      <td style={{ padding: "4px 6px", color: "var(--jade)", textAlign: "right" }}>{avgScore}</td>
                      <td style={{ padding: "4px 6px", color: "var(--silver)", textAlign: "right" }}>{avgTurns}</td>
                      <td style={{ padding: "4px 6px", color: "var(--sky)", textAlign: "right" }}>{cov}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 8 }}>
          {personaKeys.map((k) => {
            const p = personas[k] || {};
            const active = selectedPersona === k;
            return (
              <button
                key={k}
                type="button"
                onClick={() => {
                  setPersonaFocus(k);
                  setPathFocus("");
                }}
                style={{
                  textAlign: "left",
                  border: `1px solid ${active ? "rgba(0,229,160,.45)" : "var(--mist)"}`,
                  borderRadius: 8,
                  padding: 8,
                  background: active ? "rgba(0,229,160,.10)" : "rgba(3,7,18,.35)",
                  color: "var(--silver)",
                  cursor: "pointer",
                }}
              >
                <div style={{ color: "var(--jade)", fontSize: 12, marginBottom: 4 }}>{k}</div>
                <div style={{ fontSize: 11 }}>cooperation: {p.cooperation_level}</div>
                <div style={{ fontSize: 11 }}>interrupt: {p.interruption_prob}</div>
                <div style={{ fontSize: 11, color: "var(--smoke)" }}>{p.emotion_description}</div>
              </button>
            );
          })}
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {pathKeys.map((pk) => (
            <button
              key={pk}
              type="button"
              className="tn"
              onClick={() => setPathFocus(pk)}
              style={{
                borderColor: selectedPath === pk ? "rgba(178,140,255,.45)" : "var(--mist)",
                background: selectedPath === pk ? "rgba(178,140,255,.10)" : "var(--ink3)",
                color: selectedPath === pk ? "var(--violet)" : "var(--silver)",
              }}
            >
              {pk}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 460, overflowY: "auto" }}>
          {records.length === 0 ? (
            <div className="muted" style={{ fontSize: 12 }}>
              暂无记录（可点击“刷新Layer2”自动生成）。
            </div>
          ) : (
            records.map((r, idx) => (
              <details
                key={`${r.report_id || "r"}-${idx}`}
                open={idx === 0}
                style={{ border: "1px solid var(--mist)", borderRadius: 8, padding: "6px 8px", background: "rgba(3,7,18,.35)" }}
              >
                <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--silver)" }}>
                  {r.path_id} · {r.persona_type} · score={r.total_score ?? "-"} · {r.termination_reason}
                  {(r.violations || []).length > 0 ? (
                    <span style={{ color: "var(--ember)", marginLeft: 6 }}>
                      违规{(r.violations || []).length}条
                    </span>
                  ) : null}
                </summary>
                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                  {(r.violations || []).length > 0 ? (
                    <ViolationList violations={r.violations} title="本用例规则违规" />
                  ) : null}
                  <BotStatePanel botState={r.bot_state} botStateLog={r.bot_state_log} />
                  {(r.messages || []).map((m, i) => (
                    <div
                      key={`m-${i}`}
                      style={{
                        fontSize: 12,
                        lineHeight: 1.45,
                        color: m?.role === "bot" ? "var(--jade)" : "var(--silver)",
                        fontFamily: "var(--mono)",
                      }}
                    >
                      [{m?.turn}] {String(m?.role || "").toUpperCase()}: {String(m?.content || "")}
                    </div>
                  ))}
                </div>
              </details>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import "../styles-eval1-studio.css";
import studioIcon from "../image/icon.png";
import {
  fetchLayer1,
  fetchLayer2Run,
  fetchReportProviders,
  listEval1Datasets,
  runEval1Pipeline,
  uploadAndRunEval1,
  uploadEval1Data,
} from "../api/eval1Client.js";

const BOT_PROVIDER_OPTIONS = [
  { id: "qwen", label: "Qwen Bot", reportHint: "eval1_reports_{id}.json" },
  { id: "deepseek", label: "DeepSeek Bot", reportHint: "eval1_reports_{id}_deepseek.json" },
];
import InstructionTree from "./studio/InstructionTree.jsx";
import Layer1View from "./studio/Layer1View.jsx";
import Layer2View from "./studio/Layer2View.jsx";
import Layer3View from "./studio/Layer3View.jsx";

const PIPELINE_STEPS = [
  { id: "upload", label: "上传数据" },
  { id: "layer1", label: "Layer1 解析" },
  { id: "layer23", label: "对话仿真与评分" },
  { id: "done", label: "完成" },
];

export default function Eval1StudioPage() {
  const [datasets, setDatasets] = useState([]);
  const [datasetId, setDatasetId] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [runData, setRunData] = useState(null);
  const [loadingL1, setLoadingL1] = useState(false);
  const [loadingRun, setLoadingRun] = useState(false);
  const [layerTab, setLayerTab] = useState("layer1");
  const [pipelineStep, setPipelineStep] = useState(null);
  const [pipelineError, setPipelineError] = useState("");
  const [pipelineMessage, setPipelineMessage] = useState("");
  const [botProvider, setBotProvider] = useState("qwen");
  const [reportProviders, setReportProviders] = useState([]);
  const [runLoadError, setRunLoadError] = useState("");
  const [datasetLoadError, setDatasetLoadError] = useState("");
  const fileInputRef = useRef(null);

  const pipelineOpts = {
    maxPlans: 0,
    concurrency: 2,
    fast: false,
    botProvider,
  };

  const loadDatasets = useCallback(async () => {
    setDatasetLoadError("");
    try {
      const rows = await listEval1Datasets();
      setDatasets(Array.isArray(rows) ? rows : []);
      return rows;
    } catch (e) {
      setDatasets([]);
      setDatasetLoadError(e?.message || String(e));
      return [];
    }
  }, []);

  const loadAnalysis = useCallback(async (id) => {
    if (!id) return;
    setLoadingL1(true);
    try {
      setAnalysis(await fetchLayer1(id));
    } catch {
      setAnalysis(null);
    } finally {
      setLoadingL1(false);
    }
  }, []);

  const applyPipelineResult = useCallback((result) => {
    if (result?.layer1) {
      setAnalysis(result.layer1);
    }
    if (result?.reports || result?.layer2) {
      setRunData({
        dataset_id: result.dataset_id,
        reports: result.reports,
        layer2: result.layer2,
        summary: result.summary,
        health: result.health,
        source: result.source,
        bot_provider:
          result.bot_provider ||
          result.summary?.meta?.bot_provider ||
          botProvider,
        report_file: result.report_file,
      });
    }
  }, [botProvider]);

  const loadReportProviders = useCallback(async (id) => {
    if (!id) {
      setReportProviders([]);
      return;
    }
    try {
      const data = await fetchReportProviders(id);
      setReportProviders(Array.isArray(data?.providers) ? data.providers : []);
    } catch {
      setReportProviders([]);
    }
  }, []);

  const loadRunData = useCallback(
    async (id, refresh = false) => {
      if (!id) return;
      setLoadingRun(true);
      setRunLoadError("");
      try {
        const data = await fetchLayer2Run(id, {
          refresh,
          ...(refresh ? pipelineOpts : { botProvider }),
        });
        setRunData(data);
        if (refresh) {
          await loadReportProviders(id);
        }
      } catch (e) {
        setRunData(null);
        setRunLoadError(e?.message || String(e));
      } finally {
        setLoadingRun(false);
      }
    },
    [botProvider, loadReportProviders],
  );

  useEffect(() => {
    loadDatasets().then((rows) => {
      if (Array.isArray(rows) && rows.length && !datasetId) {
        setDatasetId(rows[0].dataset_id);
      }
    });
  }, [loadDatasets, datasetId]);

  useEffect(() => {
    if (datasetId) loadAnalysis(datasetId);
  }, [datasetId, loadAnalysis]);

  useEffect(() => {
    if (datasetId) loadReportProviders(datasetId);
  }, [datasetId, loadReportProviders]);

  useEffect(() => {
    if (datasetId && (layerTab === "layer2" || layerTab === "layer3")) {
      loadRunData(datasetId, false);
    }
  }, [datasetId, layerTab, botProvider, loadRunData]);

  const currentDs = datasets.find((d) => d.dataset_id === datasetId);
  const parsed = analysis?.parsed || null;

  const refreshAll = () => {
    loadAnalysis(datasetId);
    if (layerTab !== "layer1") loadRunData(datasetId, false);
  };

  const handleUploadOnly = async (file) => {
    if (!file) return;
    setPipelineError("");
    setPipelineStep("upload");
    setPipelineMessage(`正在上传 ${file.name}…`);
    try {
      const ingested = await uploadEval1Data(file);
      const rows = await loadDatasets();
      const first = ingested.datasets?.[0]?.dataset_id;
      if (first) {
        setDatasetId(first);
      } else if (rows?.length) {
        setDatasetId(rows[rows.length - 1].dataset_id);
      }
      setPipelineStep("done");
      setPipelineMessage(
        `已导入 ${ingested.count} 个数据集（${ingested.filename}），可在下拉框中选择后运行评测。`,
      );
    } catch (e) {
      setPipelineError(e.message || String(e));
      setPipelineStep(null);
      setPipelineMessage("");
    }
  };

  const handleFullPipeline = async (file = null) => {
    setPipelineError("");
    setLoadingL1(true);
    setLoadingRun(true);

    try {
      if (file) {
        setPipelineStep("upload");
        setPipelineMessage(`上传并评测：${file.name}…`);
        const res = await uploadAndRunEval1(file, pipelineOpts);
        setDatasetId(res.dataset_id);
        await loadDatasets();
        applyPipelineResult(res.pipeline);
        setPipelineStep("done");
        setPipelineMessage(
          `全流程完成：${res.dataset_id}，共 ${res.pipeline?.summary?.count ?? 0} 条用例，均分 ${Number(res.pipeline?.summary?.average_score ?? 0).toFixed(1)}`,
        );
        setLayerTab("layer3");
        return;
      }

      if (!datasetId) {
        throw new Error("请先选择或上传数据集");
      }

      setPipelineStep("layer23");
      setPipelineMessage("Layer1 解析 → Layer2 对话仿真 → Layer3 评分（耗时较长，请耐心等待）…");
      const result = await runEval1Pipeline(datasetId, pipelineOpts);
      applyPipelineResult(result);
      await loadReportProviders(datasetId);
      setPipelineStep("done");
      setPipelineMessage(
        `全流程完成：${result.summary?.count ?? 0} 条用例，均分 ${Number(result.summary?.average_score ?? 0).toFixed(1)}`,
      );
      setLayerTab("layer3");
    } catch (e) {
      setPipelineError(e.message || String(e));
      setPipelineStep(null);
      setPipelineMessage("");
    } finally {
      setLoadingL1(false);
      setLoadingRun(false);
    }
  };

  const onFileChange = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) handleUploadOnly(file);
  };

  const busy = loadingL1 || loadingRun || Boolean(pipelineStep && pipelineStep !== "done");

  return (
    <div className="eval1-studio">
      <header className="studio-header">
        <h1 className="studio-header-title">
          <img src={studioIcon} alt="" className="studio-header-icon" />
          <span className="studio-header-title-text">CallEval 复杂指令评测工作台</span>
        </h1>
        <div className="studio-header-meta">
          <div className="studio-header-field">
            <label htmlFor="studio-bot-provider" className="studio-header-field-label">
              模型
            </label>
            <select
              id="studio-bot-provider"
              value={botProvider}
              onChange={(e) => setBotProvider(e.target.value)}
              aria-label="被测 Bot 模型"
              disabled={busy}
              className="studio-bot-provider-select"
              title="切换查看/评测不同 Bot 的报告文件"
            >
              {BOT_PROVIDER_OPTIONS.map((o) => {
                const avail = reportProviders.find((p) => p.bot_provider === o.id);
                const hasReport = avail?.exists;
                return (
                  <option key={o.id} value={o.id}>
                    {o.label}
                    {hasReport ? " ✓" : ""}
                  </option>
                );
              })}
            </select>
          </div>

          <div className="studio-header-field">
            <label htmlFor="studio-dataset" className="studio-header-field-label">
              指令
            </label>
            <select
              id="studio-dataset"
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
              aria-label="评测指令"
              disabled={busy}
              className="studio-dataset-select"
            >
              {datasets.length === 0 ? (
                <option value="">暂无数据集 — 请上传</option>
              ) : (
                datasets.map((d) => (
                  <option key={d.dataset_id} value={d.dataset_id}>
                    {d.name || d.dataset_id}
                  </option>
                ))
              )}
            </select>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xlsm,.json,.txt,.md"
            className="studio-file-input"
            onChange={onFileChange}
          />
          <button
            type="button"
            className="btn-ghost"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
          >
            上传数据
          </button>
          <button
            type="button"
            className="btn-primary studio-pipeline-btn"
            disabled={busy || !datasetId}
            onClick={() => handleFullPipeline(null)}
          >
            {busy ? "评测进行中…" : "一键全流程评测"}
          </button>
          <button
            type="button"
            className="btn-ghost"
            onClick={refreshAll}
            disabled={busy}
          >
            刷新
          </button>
        </div>
      </header>

      {datasetLoadError ? (
        <div className="studio-pipeline-banner error" role="alert">
          <p className="studio-pipeline-error">
            无法加载数据集：{datasetLoadError}。请确认后端已启动，或访问 /api/eval1/deploy-status 检查部署状态。
          </p>
        </div>
      ) : null}

      {(pipelineStep || pipelineError) && (
        <div
          className={`studio-pipeline-banner ${pipelineError ? "error" : ""}`}
          role="status"
        >
          {pipelineError ? (
            <p className="studio-pipeline-error">{pipelineError}</p>
          ) : (
            <>
              <ol className="studio-pipeline-steps">
                {PIPELINE_STEPS.map((s) => {
                  const order = PIPELINE_STEPS.findIndex((x) => x.id === pipelineStep);
                  const idx = PIPELINE_STEPS.findIndex((x) => x.id === s.id);
                  let state = "pending";
                  if (pipelineStep === "done") state = "done";
                  else if (idx < order) state = "done";
                  else if (idx === order) state = "active";
                  return (
                    <li key={s.id} className={state}>
                      {s.label}
                    </li>
                  );
                })}
              </ol>
              {pipelineMessage ? (
                <p className="studio-pipeline-msg">{pipelineMessage}</p>
              ) : null}
            </>
          )}
        </div>
      )}

      <div className="studio-body">
        <aside className="studio-sidebar">
          <div className="studio-sidebar-head">解析指令项</div>
          <div className="studio-sidebar-scroll">
            <InstructionTree
              parsed={parsed}
              variableValues={analysis?.variable_values}
              rawInstruction={parsed?.raw_text || currentDs?.raw_instruction}
            />
          </div>
          <div className="studio-sidebar-foot">
            <p className="studio-hint">
              支持 .xlsx（多行）、.json、.txt。上传后走 Eval1：解析 → 图谱 → 对话 → 评分。
            </p>
            <button
              type="button"
              className="btn-ghost studio-upload-run-btn"
              disabled={busy}
              onClick={() => {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = ".xlsx,.xlsm,.json,.txt,.md";
                input.onchange = () => {
                  const f = input.files?.[0];
                  if (f) handleFullPipeline(f);
                };
                input.click();
              }}
            >
              上传并立即全流程
            </button>
          </div>
        </aside>

        <main className="studio-main">
          <nav className="studio-layer-tabs" aria-label="评测层级">
            <button
              type="button"
              className={`studio-layer-tab ${layerTab === "layer1" ? "active" : ""}`}
              onClick={() => setLayerTab("layer1")}
            >
              Layer 1 · 场景构建
            </button>
            <button
              type="button"
              className={`studio-layer-tab ${layerTab === "layer2" ? "active" : ""}`}
              onClick={() => setLayerTab("layer2")}
            >
              Layer 2 · 对话仿真
            </button>
            <button
              type="button"
              className={`studio-layer-tab ${layerTab === "layer3" ? "active" : ""}`}
              onClick={() => setLayerTab("layer3")}
            >
              Layer 3 · 评分
            </button>
          </nav>

          <div className="studio-layer-content">
            {layerTab === "layer1" && <Layer1View data={analysis} loading={loadingL1} />}
            {layerTab === "layer2" && (
              <Layer2View
                data={runData}
                loading={loadingRun}
                loadError={runLoadError}
                pathCatalog={analysis?.paths}
                botProvider={botProvider}
                onRefresh={(refresh) => loadRunData(datasetId, refresh)}
              />
            )}
            {layerTab === "layer3" && (
              <Layer3View
                data={runData}
                loading={loadingRun}
                loadError={runLoadError}
                datasetName={currentDs?.name || datasetId}
                botProvider={botProvider}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

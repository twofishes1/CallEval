const API = "/api";

async function parseJsonResponse(r) {
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = data?.detail || data?.message || r.statusText || "请求失败";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

function withBotProvider(params, botProvider) {
  const q = params instanceof URLSearchParams ? params : new URLSearchParams(params);
  if (botProvider) {
    q.set("bot_provider", String(botProvider));
  }
  return q;
}

export async function listEval1Datasets() {
  const r = await fetch(`${API}/eval1/datasets`);
  return parseJsonResponse(r);
}

export async function fetchReportProviders(datasetId) {
  const r = await fetch(
    `${API}/eval1/reports/${encodeURIComponent(datasetId)}/providers?_ts=${Date.now()}`,
  );
  return parseJsonResponse(r);
}

export async function fetchLayer1(datasetId) {
  const r = await fetch(`${API}/eval1/layer1/${encodeURIComponent(datasetId)}?_ts=${Date.now()}`);
  return parseJsonResponse(r);
}

export async function fetchLayer2Run(datasetId, opts = {}) {
  const {
    maxPlans = 0,
    concurrency = 2,
    fast = false,
    refresh = false,
    planTimeoutSec = 900,
    includeControlGroup = false,
    botProvider = "qwen",
  } = opts;
  const q = withBotProvider(
    {
      refresh: String(refresh),
      _ts: String(Date.now()),
    },
    botProvider,
  );
  if (refresh) {
    q.set("max_plans", String(maxPlans));
    q.set("concurrency", String(concurrency));
    q.set("fast", String(fast));
    q.set("plan_timeout_sec", String(planTimeoutSec));
    q.set("include_control_group", String(includeControlGroup));
  }
  const r = await fetch(`${API}/eval1/layer2/${encodeURIComponent(datasetId)}?${q}`);
  return parseJsonResponse(r);
}

/** Upload xlsx / json / txt into eval1/data/uploads */
export async function uploadEval1Data(file) {
  const form = new FormData();
  form.append("file", file);
  const r = await fetch(`${API}/eval1/upload`, { method: "POST", body: form });
  return parseJsonResponse(r);
}

/** Full pipeline: Layer1 → Layer2 → Layer3 */
export async function runEval1Pipeline(datasetId, opts = {}) {
  const {
    maxPlans = 0,
    concurrency = 2,
    fast = false,
    layer1Only = false,
    planTimeoutSec = 900,
    includeControlGroup = false,
    botProvider = "qwen",
  } = opts;
  const q = withBotProvider(
    {
      max_plans: String(maxPlans),
      concurrency: String(concurrency),
      fast: String(fast),
      layer1_only: String(layer1Only),
      plan_timeout_sec: String(planTimeoutSec),
      include_control_group: String(includeControlGroup),
    },
    botProvider,
  );
  const r = await fetch(
    `${API}/eval1/pipeline/${encodeURIComponent(datasetId)}/run?${q}`,
    { method: "POST" },
  );
  return parseJsonResponse(r);
}

/** Upload file and run pipeline on first (or indexed) dataset in file */
export async function uploadAndRunEval1(file, opts = {}) {
  const form = new FormData();
  form.append("file", file);
  const q = withBotProvider(
    {
      dataset_index: String(opts.datasetIndex ?? 0),
      max_plans: String(opts.maxPlans ?? 12),
      concurrency: String(opts.concurrency ?? 2),
      fast: String(opts.fast ?? false),
      plan_timeout_sec: String(opts.planTimeoutSec ?? 900),
      include_control_group: String(opts.includeControlGroup ?? false),
    },
    opts.botProvider ?? "qwen",
  );
  const r = await fetch(`${API}/eval1/upload-and-run?${q}`, { method: "POST", body: form });
  return parseJsonResponse(r);
}

/* Thin fetch wrapper for the FastAPI backend. */
async function call(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty */ }
  if (!res.ok) {
    const msg = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : res.statusText;
    throw new Error(msg);
  }
  return data;
}

const q = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== "")).toString();

export const api = {
  symbols: () => call("GET", "/api/symbols"),
  addSymbol: (b) => call("POST", "/api/symbols", b),
  sources: () => call("GET", "/api/sources"),
  inventory: () => call("GET", "/api/inventory"),
  download: (b) => call("POST", "/api/download", b),
  downloadMany: (items) => call("POST", "/api/download-many", { items }),
  update: (symbol, interval) => call("POST", "/api/update?" + q({ symbol, interval })),
  job: (id) => call("GET", `/api/jobs/${id}`),
  importCsv: (b) => call("POST", "/api/import-csv", b),
  candles: (p) => call("GET", "/api/candles?" + q(p)),
  upstoxSearch: (text) => call("GET", "/api/upstox/search?" + q({ q: text })),
  upstoxCheck: (symbol) => call("GET", "/api/upstox/check?" + q({ symbol })),
  catalogStatus: () => call("GET", "/api/catalog/status"),
  catalogRefresh: () => call("POST", "/api/catalog/refresh"),

  // your security groups ("playlists")
  groups: () => call("GET", "/api/groups"),
  createGroup: (b) => call("POST", "/api/groups", b),
  patchGroup: (id, b) => call("PATCH", `/api/groups/${encodeURIComponent(id)}`, b),
  deleteGroup: (id) => call("DELETE", `/api/groups/${encodeURIComponent(id)}`),

  strategies: () => call("GET", "/api/strategies"),
  reload: () => call("POST", "/api/strategies/reload"),
  indicators: () => call("GET", "/api/indicators"),
  defaults: () => call("GET", "/api/settings/defaults"),
  indicator: (b) => call("POST", "/api/indicator", b),
  apply: (b) => call("POST", "/api/apply", b),
  backtest: (b) => call("POST", "/api/backtest", b),
  deep: (b) => call("POST", "/api/deep", b),
  replayPrepare: (b) => call("POST", "/api/replay/prepare", b),
  replayStep: (b) => call("POST", "/api/replay/step", b),
  reports: () => call("GET", "/api/reports"),
  report: (id) => call("GET", `/api/reports/${encodeURIComponent(id)}`),
  deleteReport: (id) => call("DELETE", `/api/reports/${encodeURIComponent(id)}`),

  // research: optimizer, universe test, developer mode
  optimizeCount: (b) => call("POST", "/api/research/optimize/count", b),
  optimizeTimeframes: (b) => call("POST", "/api/research/timeframes", b),
  optimize: (b) => call("POST", "/api/research/optimize", b),
  universe: (b) => call("POST", "/api/research/universe", b),
  devBacktest: (b) => call("POST", "/api/dev/backtest", b),
  researchReports: () => call("GET", "/api/research/reports"),
  researchReport: (kind, id) => call("GET", `/api/research/reports/${kind}/${encodeURIComponent(id)}`),
  deleteResearchReport: (kind, id) => call("DELETE", `/api/research/reports/${kind}/${encodeURIComponent(id)}`),
};

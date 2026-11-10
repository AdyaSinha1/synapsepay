export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : message;
    } catch {
      /* keep default */
    }
    throw new Error(message);
  }
  return res.json();
}

export const getHealth = () => api("/api/health");
export const getScenarios = () => api("/api/scenarios");
export const getMetrics = () => api("/api/metrics");
export const getContracts = () => api("/api/contracts");
export const runDemo = (body) =>
  api("/api/contracts/execute-demo", { method: "POST", body: JSON.stringify(body) });
export const createContract = (body) =>
  api("/api/contracts/create", { method: "POST", body: JSON.stringify(body) });
export const submitDeliverable = (contractId, body) =>
  api(`/api/contracts/${contractId}/submit`, { method: "POST", body: JSON.stringify(body) });
export const arbitrate = (contractId) =>
  api(`/api/contracts/${contractId}/arbitrate`, { method: "POST" });
export const getEvaluations = (contractId) =>
  api(`/api/contracts/${contractId}/evaluations`);

export const fmtUSD = (n) => `$${Number(n || 0).toFixed(2)}`;
export const fmtPct = (v) => `${Math.round((v || 0) * 100)}%`;

export function agentLabel(id) {
  const map = {
    "orchestrator-agent-a": "Orchestrator agent A",
    "worker-agent-b": "Worker agent B",
    "neural-arbiter": "Neural Arbiter",
    "paypal-vault": "PayPal vault",
    synapsepay: "SynapsePay",
  };
  return map[id] || id;
}

export function zipContracts(data) {
  if (!data || !Array.isArray(data.contracts)) return [];
  const escrows = data.escrows || [];
  return data.contracts
    .map((c) => ({ ...c, escrow: escrows.find((e) => e.contract_id === c.id) || null }))
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
}

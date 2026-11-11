import { getToken, getUser, setSession } from "./auth.js";

export const API_BASE = import.meta.env.VITE_API_BASE ||
  (typeof window !== "undefined" && window.location.hostname === "localhost"
    ? "http://localhost:8000"
    : "https://synapsepay-api.onrender.com");

export async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : message;
    } catch {
      /* keep default */
    }
    const error = new Error(message);
    error.status = res.status;
    throw error;
  }
  return res.json();
}

export const getHealth = () => api("/api/health");
export const getScenarios = () => api("/api/scenarios");
export const getMetrics = () => api("/api/metrics");
export const getContracts = () => api("/api/contracts");
export const getContract = (id) => api(`/api/contracts/${id}`);
export const getContractEvaluations = (id) => api(`/api/contracts/${id}/evaluations`);
export const getContractSubmissions = (id) => api(`/api/contracts/${id}/submissions`);
export const getRecentEvents = (limit = 40) => api(`/api/events/recent?limit=${limit}`);
export const getPaypalConfig = () => api("/api/paypal/config");
export const runDemo = (body) =>
  api("/api/contracts/execute-demo", { method: "POST", body: JSON.stringify(body) });
export const createContract = (body) =>
  api("/api/contracts/create", { method: "POST", body: JSON.stringify(body) });
export const createDraft = (body) =>
  api("/api/contracts/draft", { method: "POST", body: JSON.stringify(body) });
export const fundStart = (id) =>
  api(`/api/contracts/${id}/fund/start`, { method: "POST" });
export const fundComplete = (id, orderId) =>
  api(`/api/contracts/${id}/fund/complete`, { method: "POST", body: JSON.stringify({ order_id: orderId }) });
export const acceptContract = (id, worker = "") =>
  api(`/api/contracts/${id}/accept`, { method: "POST", body: JSON.stringify({ worker }) });
export const disputeContract = (id, reason) =>
  api(`/api/contracts/${id}/dispute`, { method: "POST", body: JSON.stringify({ reason }) });
export const submitDeliverable = (id, body) =>
  api(`/api/contracts/${id}/submit`, { method: "POST", body: JSON.stringify(body) });
export const arbitrate = (id) => api(`/api/contracts/${id}/arbitrate`, { method: "POST" });
export const sandboxPreview = (code, tests) =>
  api("/api/sandbox/preview", { method: "POST", body: JSON.stringify({ code, tests }) });

export async function registerAccount(username, password, role, displayName = "") {
  const data = await api("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, role, display_name: displayName }),
  });
  setSession({ token: data.token, user: data.user, expires_at: data.expires_at });
  return data.user;
}

export async function loginAccount(username, password) {
  const data = await api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  setSession({ token: data.token, user: data.user, expires_at: data.expires_at });
  return data.user;
}

export async function logoutAccount() {
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
  } catch {
    /* token may already be dead */
  }
  setSession(null);
}

export async function changePassword(oldPassword, newPassword) {
  return api("/api/auth/password", {
    method: "POST",
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
}

export async function logoutEverywhere() {
  const data = await api("/api/auth/logout-all", { method: "POST" });
  setSession(null);
  return data;
}

export { getUser };

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

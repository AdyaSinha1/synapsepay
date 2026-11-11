import { useState } from "react";
import { Asterisk, Loader2, Lock, ScrollText, ShieldCheck, Upload } from "lucide-react";
import EvaluationCard from "../components/EvaluationCard.jsx";
import { Chip, EmptyState, PageIntro, ScoreBar, SectionHeader, StatusChip } from "../components/ui.jsx";
import { fmtUSD, getEvaluations } from "../api.js";

export default function Arbiter({ contracts, running, onArbitrateRun, onNavigate }) {
  const [selectedId, setSelectedId] = useState(null);
  const [code, setCode] = useState("");
  const [result, setResult] = useState(null);
  const [audit, setAudit] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const selected = contracts.find((c) => c.id === selectedId) || null;
  const arbitrable = selected && selected.escrow?.status === "AUTHORIZED";
  const remediation = selected && selected.escrow?.status === "REMEDIATION";

  const pick = async (c) => {
    setSelectedId(c.id);
    setResult(null);
    setError(null);
    setCode(c.worker_code || "");
    try {
      const trail = await getEvaluations(c.id);
      setAudit(trail.evaluations || []);
    } catch {
      setAudit([]);
    }
  };

  const run = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const res = await onArbitrateRun(selected.id, code);
      setResult(res);
      const trail = await getEvaluations(selected.id);
      setAudit(trail.evaluations || []);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageIntro
        title="AI Arbiter"
        sub="The impartial judge. It never trusts anyone's word — it runs the tests, checks the schema, asks the LLM, and lets the threshold rule move the money."
      />

      {contracts.length === 0 ? (
        <EmptyState
          icon={Asterisk}
          title="No contracts to arbitrate yet"
          body="Create a contract first — the arbiter needs an escrow agreement to enforce."
          action={
            <button className="btn-volt" onClick={() => onNavigate("contracts")}>
              Go to Contracts
            </button>
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="space-y-6 lg:col-span-2">
            <div className="card p-6">
              <SectionHeader title="Pick a contract" sub="Only contracts with active escrow can be arbitrated." />
              <ul className="max-h-56 space-y-2 overflow-y-auto pr-1">
                {contracts.slice(0, 8).map((c) => (
                  <li key={c.id}>
                    <button
                      onClick={() => pick(c)}
                      className={`w-full rounded-xl border px-4 py-3 text-left transition ${
                        selectedId === c.id
                          ? "border-lilac bg-lilac-100/60"
                          : "border-line bg-[#FCFBF7] hover:border-lilac/40"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium text-ink">{c.title}</p>
                        <StatusChip status={c.escrow?.status || "PENDING"} />
                      </div>
                      <p className="mt-0.5 font-mono text-[11px] text-mute">SYN-{c.id} · {fmtUSD(c.bounty_value)}</p>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            {selected && (
              <div className="card p-6">
                <SectionHeader title="Worker deliverable" sub="What the worker agent submits for judgment." />
                <textarea
                  rows={9}
                  className="input font-mono text-xs"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="Paste Python code here…"
                />
                {selected.test_code && (
                  <details className="mt-3 rounded-xl border border-line bg-[#FBFAF5] px-3 py-2">
                    <summary className="flex cursor-pointer items-center gap-1.5 text-[11px] font-semibold text-mute">
                      <ScrollText className="h-3.5 w-3.5" /> View contract tests ({selected.test_code.split("\n").filter((l) => l.trim().startsWith("def test")).length} found)
                    </summary>
                    <pre className="console mt-2 max-h-40 p-2">{selected.test_code}</pre>
                  </details>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <button className="btn-volt flex-1" onClick={run} disabled={busy || running || !arbitrable}>
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                    Submit & arbitrate
                  </button>
                </div>
                {remediation && (
                  <p className="mt-2 rounded-lg bg-sun-100 px-3 py-2 text-[11px] leading-relaxed text-sun-ink">
                    Remediation round: this contract failed once near the threshold. Resubmit an improved deliverable —
                    the next arbitration settles definitively (capture, partial capture, or void). No money has moved yet.
                  </p>
                )}
                {!arbitrable && !remediation && (
                  <p className="mt-2 text-[11px] leading-relaxed text-coral">
                    This contract is already settled ({selected.escrow?.status}). Create a new contract to arbitrate again.
                  </p>
                )}
                {error && (
                  <p className="mt-2 rounded-lg bg-coral-100 px-3 py-2 text-[11px] text-coral-ink">{error}</p>
                )}
              </div>
            )}
          </div>

          <div className="space-y-6 lg:col-span-3">
            {result ? (
              <div className="fade-up space-y-6">
                <EvaluationCard evaluation={result.evaluation} />
                <div className="card p-6">
                  <SectionHeader
                    title="Sandbox evidence"
                    sub="Raw test output the verdict is built on."
                    badge={<Chip tone="lilac">{result.evaluation.sandbox?.passed}/{result.evaluation.sandbox?.total} passed</Chip>}
                  />
                  <div className="console h-64 p-3">
                    {(result.evaluation.test_logs || []).map((line, i) => (
                      <p
                        key={i}
                        className={`py-0.5 ${line.startsWith("[PASS]") ? "text-volt-ink" : line.startsWith("[FAIL]") ? "text-coral" : "text-mute"}`}
                      >
                        {line}
                      </p>
                    ))}
                    {(result.evaluation.schema_details || []).map((line, i) => (
                      <p key={`s-${i}`} className="py-0.5 text-mute">{line}</p>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <EvaluationCard evaluation={null} />
            )}

            <div className="card p-6">
              <SectionHeader
                title="Decision audit trail"
                sub="Every arbitration round is preserved with its evidence."
                badge={<Chip tone="slate">{audit.length} rounds</Chip>}
              />
              {audit.length === 0 ? (
                <p className="text-xs text-mute">No arbitration rounds recorded for this contract yet.</p>
              ) : (
                <ul className="space-y-2">
                  {audit.map((ev, i) => (
                    <li key={i} className="flex items-center justify-between gap-2 rounded-xl border border-line bg-[#FCFBF7] px-3 py-2">
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-ink">
                          Round {i + 1} · S = {Number(ev.composite).toFixed(4)}
                        </p>
                        <p className="truncate font-mono text-[10px] text-mute">
                          tests {Math.round(ev.scores?.tests * 100)}% · schema {Math.round(ev.scores?.schema * 100)}% · AI {Math.round(ev.scores?.llm * 100)}%
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Chip tone={ev.decision === "CAPTURE" ? "volt" : ev.decision === "PARTIAL" ? "sun" : "coral"}>{ev.decision}</Chip>
                        <span className="font-mono text-[10px] text-mute/60">{(ev.evaluated_at || "").slice(11, 19)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card p-6">
              <SectionHeader title="How the score works" sub="No black box — three channels, one threshold." />
              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  { w: "50%", name: "Unit tests", desc: "Deterministic sandbox run of the contract's tests", bar: "bg-volt-deep" },
                  { w: "25%", name: "Schema & policy", desc: "AST checks: required functions, forbidden imports", bar: "bg-plum-700" },
                  { w: "25%", name: "AI review", desc: "LLM rubric for quality and edge-case resilience", bar: "bg-lilac" },
                ].map((t) => (
                  <div key={t.name} className="rounded-xl border border-line bg-[#FCFBF7] p-4">
                    <p className="font-display text-xl font-extrabold text-ink">{t.w}</p>
                    <p className="mt-1 text-xs font-bold text-ink">{t.name}</p>
                    <p className="mt-1 text-[11px] leading-relaxed text-mute">{t.desc}</p>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-plum-100">
                      <div className={`h-full ${t.bar}`} style={{ width: t.w }} />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-4 rounded-xl bg-lilac-100 px-4 py-3 text-[11px] leading-relaxed text-lilac-ink">
                <Asterisk className="mr-1 inline h-3.5 w-3.5" />
                Score 85%+ captures; 80–85% triggers a scheduled partial capture; below 80% voids. Code contracts need
                at least 3 tests — fewer applies a coverage factor. The LLM only feeds one advisory channel, clamped to
                0.85; the no-key heuristic fallback is capped at 0.75. Neither can move money alone.
              </p>
              <p className="mt-3 rounded-xl border border-line bg-[#FBFAF5] px-4 py-3 text-[11px] leading-relaxed text-mute">
                <Lock className="mr-1 inline h-3.5 w-3.5 text-plum-700" />
                <span className="font-semibold text-ink">Sandbox security:</span> worker code runs in an isolated
                interpreter (no env, no user site) inside a Job Object with memory/process caps and kill-on-close — or,
                when a Docker daemon is available, in a throwaway container (no network, memory/CPU/pids caps,
                read-only filesystem, non-root). Results come back HMAC-signed and are verified before scoring. The
                AST policy scan (dynamic execution, reflection, dunder access) is a <span className="font-semibold">lint
                layer, not the security boundary</span> — the OS sandbox is. Treat every submission as hostile.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

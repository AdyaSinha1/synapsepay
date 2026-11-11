import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Loader2, Play, ShieldCheck, Upload } from "lucide-react";
import { Chip, EmptyState, PageIntro, SectionHeader, StatusChip } from "../components/ui.jsx";
import { useApp } from "../context.jsx";
import { fmtUSD, getContract, getContractEvaluations } from "../api.js";

export default function Workspace() {
  const { id } = useParams();
  const { showError, showToast } = useApp();
  const [contract, setContract] = useState(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const c = await getContract(id);
      setContract(c);
      if (!code && (c.contract.worker_code || c.contract.test_code)) {
        setCode(c.deliverable?.code || c.contract.worker_code || "");
      }
      const e = await getContractEvaluations(id).catch(() => ({ evaluations: [] }));
      setResult(e.evaluations?.length ? { evaluation: e.evaluations[e.evaluations.length - 1] } : null);
      setError(null);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await getContract(id);
      const res = await getContractEvaluations(id).catch(() => ({ evaluations: [] }));
      const rounds = res.evaluations?.length || 0;
      const latest = res.evaluations?.[rounds - 1];
      const isRemediation = latest?.decision === "VOID" && rounds === 1 && latest.composite >= 0.7;
      if (isRemediation) {
        showToast("Remediation resubmission recorded — running the arbiter again", "lilac");
      }
      const arb = await getContract(id);
      setContract(arb);
      const arbitrateRes = await import("../api.js").then((m) => m.arbitrate(id));
      setResult(arbitrateRes);
      await load();
      if (arbitrateRes.evaluation?.decision === "CAPTURE") {
        showToast(`Captured — ${arbitrateRes.receipt?.transaction_id}`, "volt");
      } else if (arbitrateRes.escrow?.status === "REMEDIATION") {
        showToast("Near-miss verdict: remediation round opened — fix the failing tests and resubmit", "lilac");
      } else {
        showToast("Verdict: VOID — hirer refunded", "coral");
      }
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="flex items-center gap-2 text-sm text-mute"><Loader2 className="h-4 w-4 animate-spin" /> Loading workspace…</div>;
  }

  if (error && !contract) {
    return <EmptyState title="Could not load workspace" body={error} action={<Link className="btn-volt" to="/board">Back to board</Link>} />;
  }

  const c = contract?.contract;
  const esc = contract?.escrow;
  if (!c) return null;

  const arbitrable = esc?.status === "AUTHORIZED" && ["FUNDED", "ACCEPTED", "SUBMITTED"].includes(c.state || "FUNDED");
  const remediation = esc?.status === "REMEDIATION";

  return (
    <div className="space-y-6">
      <PageIntro
        title={`Workspace — ${c.title}`}
        sub={<span className="font-mono">SYN-{c.id} · bounty {fmtUSD(c.bounty_value)} · worker {c.worker}</span>}
        action={
          <Link to={`/contracts/${id}`} className="btn-ghost">
            <ArrowLeft className="h-4 w-4" /> Contract page
          </Link>
        }
      />

      {(remediation || result?.escrow?.status === "REMEDIATION") && (
        <div className="rounded-2xl border border-sun/40 bg-sun-100 p-4">
          <p className="text-xs font-bold uppercase tracking-wide text-sun-ink">Remediation round open</p>
          <ul className="mt-1.5 space-y-1 text-[11px] text-sun-ink/90">
            {(result?.evaluation?.remediation_plan || []).map((p, i) => <li key={i}>• {p}</li>)}
          </ul>
          <p className="mt-1.5 text-[11px] text-sun-ink/70">One resubmission allowed — the next arbitration settles definitively.</p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <div className="card p-6">
            <SectionHeader
              title="Your deliverable"
              sub="Python code that must pass the hirer's tests inside the arbiter sandbox."
              badge={<Chip tone="plum">{c.acceptance_criteria?.length || 0} criteria</Chip>}
            />
            <textarea
              rows={16}
              className="input font-mono text-xs"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="def solve(...): ..."
            />
            {c.acceptance_criteria?.length > 0 && (
              <details className="mt-3 rounded-xl border border-line bg-[#FCFBF7] px-3 py-2">
                <summary className="cursor-pointer text-[11px] font-semibold text-mute">Acceptance criteria (visible before accept)</summary>
                <ul className="mt-1.5 space-y-1 text-xs text-mute">
                  {c.acceptance_criteria.map((x) => <li key={x}>• {x}</li>)}
                </ul>
              </details>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn-volt flex-1" onClick={submit} disabled={busy || (!arbitrable && !remediation)}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                {remediation ? "Resubmit & re-arbitrate" : "Submit & run arbitration"}
              </button>
            </div>
            {!arbitrable && !remediation && (
              <p className="mt-2 text-[11px] text-coral">
                This contract is {esc?.status || c.state || "settled"} — the workspace is read-only now.
              </p>
            )}
            {error && <p className="mt-3 rounded-lg bg-coral-100 px-3 py-2 text-xs text-coral-ink">{error}</p>}
          </div>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <div className="card p-6">
            <SectionHeader title="Contract status" />
            <div className="flex items-center justify-between text-xs">
              <span className="text-mute">Escrow</span>
              <StatusChip status={esc?.status || "PENDING"} />
            </div>
            <div className="mt-3 rounded-xl bg-[#FCFBF7] p-3 text-[11px] leading-relaxed text-mute">
              {esc?.status === "AUTHORIZED" && "Funds reserved (not deposited). Your submission decides whether the arbiter captures them."}
              {esc?.status === "REMEDIATION" && "First round failed near the threshold. Improve the code and resubmit once."}
              {esc?.status === "PARTIAL" && "Partial capture: you were paid a fraction of the bounty."}
              {esc?.status === "CAPTURED" && "Full capture: you were paid the whole bounty."}
              {esc?.status === "VOIDED" && "Verdict below the partial band — the hold was released."}
              {esc?.status === "DRAFT" && "Contract not funded yet."}
            </div>
          </div>

          {c.test_code && (
            <div className="card p-6">
              <SectionHeader title="Contract tests" sub="What your code will face in the sandbox." />
              <pre className="console max-h-56 p-3">{c.test_code}</pre>
            </div>
          )}

          {result?.evaluation && (
            <div className="card p-6">
              <SectionHeader title="Latest verdict" badge={<Chip tone={result.evaluation.decision === "CAPTURE" ? "volt" : result.evaluation.decision === "PARTIAL" ? "sun" : "coral"}>{result.evaluation.decision}</Chip>} />
              <p className="font-display text-2xl font-extrabold text-ink">
                {(result.evaluation.composite * 100).toFixed(2)}%
              </p>
              <p className="mt-1 text-[11px] text-mute">Threshold: 85% capture · 80% partial</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

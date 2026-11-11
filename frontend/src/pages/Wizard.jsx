import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, FlaskConical, Loader2, Save } from "lucide-react";
import { useApp } from "../context.jsx";
import { Chip, PageIntro, SectionHeader } from "../components/ui.jsx";
import { createDraft, fmtUSD, sandboxPreview } from "../api.js";

const STEP_LABELS = ["Task", "Criteria", "Tests", "Review", "Fund"];

export default function Wizard() {
  const navigate = useNavigate();
  const { showError, showToast, fundSimulated, health } = useApp();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    title: "",
    description: "",
    bounty: 40,
    deadline_hours: 72,
    criteria: "Expose slug(text) returning a lowercase, dash-joined slug\nCollapse repeated whitespace\nTrim leading and trailing spaces",
    testCode:
      "def test_basic():\n    assert slugify('Hello World') == 'hello-world'\n\ndef test_spaces():\n    assert slugify('  many   spaces  ') == 'many-spaces'\n\ndef test_single():\n    assert slugify('word') == 'word'\n",
    sampleCode:
      "def slugify(text):\n    \"\"\"Convert a title into a URL slug.\"\"\"\n    return '-'.join(text.lower().strip().split())\n",
  });
  const [preview, setPreview] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [draft, setDraft] = useState(null);
  const [funding, setFunding] = useState(false);
  const [funded, setFunded] = useState(null);
  const [error, setError] = useState(null);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const stepErrors = () => {
    if (step === 0) {
      const errs = [];
      if (form.title.trim().length < 3) errs.push("Title must be at least 3 characters.");
      if (!(Number(form.bounty) > 0) || Number(form.bounty) > 10000) errs.push("Bounty must be between 0 and 10,000 USD.");
      if (!/^\d+(\.\d{1,2})?$/.test(String(form.bounty))) errs.push("Bounty supports at most 2 decimal places.");
      return errs;
    }
    if (step === 1) {
      const lines = form.criteria.split("\n").map((s) => s.trim()).filter(Boolean);
      if (lines.length < 1) errs_push(lines);
      return lines.length < 1 ? ["Add at least one acceptance criterion."] : [];
    }
    if (step === 2) {
      const errs = [];
      const n = (form.testCode.match(/def\s+test_\w+/g) || []).length;
      if (n < 3) errs.push(`At least 3 unit tests are required (found ${n}). The coverage rule means one trivial test can never earn a full score.`);
      return errs;
    }
    return [];
  };

  const next = () => {
    const errs = stepErrors();
    if (errs.length) {
      setError(errs.join(" "));
      return;
    }
    setError(null);
    setStep((s) => s + 1);
  };

  const runPreview = async () => {
    setPreviewBusy(true);
    setPreview(null);
    try {
      const res = await sandboxPreview(form.sampleCode, form.testCode);
      setPreview(res);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const saveDraft = async () => {
    setFunding(true);
    setError(null);
    try {
      const created = await createDraft({
        title: form.title.trim(),
        description: form.description,
        bounty_value: Number(form.bounty),
        currency: "USD",
        acceptance_criteria: form.criteria.split("\n").map((s) => s.trim()).filter(Boolean),
        deliverable_schema: { type: "code", required_functions: [] },
        test_code: form.testCode,
        deadline_hours: Number(form.deadline_hours) || 72,
      });
      setDraft(created.contract);
      showToast("Draft saved — continue to funding", "lilac");
      setStep(4);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setFunding(false);
    }
  };

  const fund = async () => {
    if (!draft) return;
    setFunding(true);
    setError(null);
    try {
      const done = await fundSimulated(draft.id);
      setFunded(done.escrow || done);
      setTimeout(() => navigate(`/contracts/${draft.id}`), 900);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setFunding(false);
    }
  };

  const criteriaLines = form.criteria.split("\n").map((s) => s.trim()).filter(Boolean);
  const testCount = (form.testCode.match(/def\s+test_\w+/g) || []).length;

  return (
    <div className="space-y-6">
      <PageIntro
        title="New Contract"
        sub="You are the hirer. Describe the task, define the acceptance criteria and tests — the worker brings the code."
      />

      <div className="flex flex-wrap items-center gap-2">
        {STEP_LABELS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${
                i === step
                  ? "border-lilac bg-lilac-100 text-lilac-ink"
                  : i < step
                    ? "border-volt-deep/40 bg-volt-soft text-volt-ink"
                    : "border-line bg-white text-mute"
              }`}
            >
              {i < step && <Check className="h-3 w-3" />}
              {label}
            </span>
            {i < STEP_LABELS.length - 1 && <span className="h-px w-4 bg-line" />}
          </div>
        ))}
      </div>

      <div className="card p-6">
        {step === 0 && (
          <div className="space-y-4">
            <SectionHeader title="Step 1 — Task" sub="What should the worker build, and what is it worth?" />
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-mute">Title (3-120 chars)</span>
              <input className="input" value={form.title} onChange={set("title")} placeholder="Build a URL slug helper" />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-mute">Description</span>
              <textarea rows={3} className="input" value={form.description} onChange={set("description")} placeholder="Optional context for the worker." />
            </label>
            <div className="grid grid-cols-2 gap-4">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-mute">Bounty (USD, max 10,000)</span>
                <input type="number" min="1" step="0.01" className="input" value={form.bounty} onChange={set("bounty")} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-mute">Deadline (hours after funding)</span>
                <input type="number" min="1" className="input" value={form.deadline_hours} onChange={set("deadline_hours")} />
              </label>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <SectionHeader title="Step 2 — Acceptance criteria" sub="Plain-language rules the arbiter includes in its rubric." />
            <textarea rows={5} className="input font-mono text-xs" value={form.criteria} onChange={set("criteria")} />
            <p className="text-[11px] text-mute">{criteriaLines.length} criteria — one per line (max 20).</p>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <SectionHeader
              title="Step 3 — Tests"
              sub="The arbiter runs these against the worker's submission. Minimum 3 tests; they are locked at funding."
              badge={<Chip tone="lilac">{testCount} found</Chip>}
            />
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-mute">Unit tests (Python)</span>
              <textarea rows={9} className="input font-mono text-xs" value={form.testCode} onChange={set("testCode")} />
            </label>
            <div className="rounded-xl border border-line bg-[#FCFBF7] p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-ink">Dry-run against your own sample code</p>
                <button className="btn-ghost !px-3 !py-1.5 text-xs" onClick={runPreview} disabled={previewBusy}>
                  {previewBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />}
                  Run preview
                </button>
              </div>
              <textarea rows={5} className="input mt-3 font-mono text-xs" value={form.sampleCode} onChange={set("sampleCode")} />
              {preview && (
                <div className="console mt-3 max-h-40 p-2">
                  {preview.logs.map((l, i) => (
                    <p key={i} className={l.startsWith("[PASS]") ? "text-volt-ink" : l.startsWith("[FAIL]") ? "text-coral" : "text-mute"}>{l}</p>
                  ))}
                  {preview.logs.length === 0 && <p className="text-mute">No log lines.</p>}
                </div>
              )}
              {preview && (
                <p className="mt-2 text-[11px] text-mute">
                  Sample pass rate: {Math.round((preview.pass_rate || 0) * 100)}% — this preview never leaves your session.
                </p>
              )}
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <SectionHeader title="Step 4 — Review" sub="This is what the arbiter will enforce. Tests lock at funding." />
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-line bg-[#FCFBF7] p-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-mute">Task</p>
                <p className="mt-1 text-sm font-semibold text-ink">{form.title || "—"}</p>
                <p className="mt-1 text-xs text-mute">{form.description || "No description."}</p>
                <p className="mt-2 font-mono text-sm text-ink">{fmtUSD(Number(form.bounty) || 0)} · {form.deadline_hours}h deadline</p>
              </div>
              <div className="rounded-xl border border-line bg-[#FCFBF7] p-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-mute">Verification</p>
                <ul className="mt-1 space-y-1 text-xs text-mute">
                  {criteriaLines.map((c) => <li key={c}>• {c}</li>)}
                </ul>
                <p className="mt-2 font-mono text-xs text-ink">{testCount} unit tests (min 3)</p>
              </div>
            </div>
            {error && <p className="rounded-lg bg-coral-100 px-3 py-2 text-xs text-coral-ink">{error}</p>}
            <button className="btn-volt w-full" onClick={saveDraft} disabled={funding}>
              {funding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save draft & continue to funding
            </button>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-4">
            <SectionHeader
              title="Step 5 — Fund"
              sub="Funding places a PayPal authorization: funds are RESERVED, not deposited. Simulated mode moves no money at all."
              badge={<Chip tone={health?.paypal_mode === "live_sandbox" ? "volt" : "amber"}>{health?.paypal_mode === "live_sandbox" ? "Live sandbox keys" : "Simulated mode"}</Chip>}
            />
            {draft ? (
              <>
                <div className="rounded-xl border border-volt-deep/40 bg-volt-soft p-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-volt-ink">Draft saved</p>
                  <p className="mt-1 font-mono text-[11px] text-mute">SYN-{draft.id} · {fmtUSD(draft.bounty_value)}</p>
                </div>
                {error && <p className="rounded-lg bg-coral-100 px-3 py-2 text-xs text-coral-ink">{error}</p>}
                <button className="btn-volt w-full" onClick={fund} disabled={funding}>
                  {funding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                  Fund (simulated) — reserve {fmtUSD(draft.bounty_value)}
                </button>
                <p className="text-[11px] leading-relaxed text-mute/80">
                  With live sandbox keys this step shows PayPal Buttons: the buyer approves the
                  AUTHORIZE order in a popup, then the server authorizes and the contract flips to
                  FUNDED. No money is deposited until the arbiter captures.
                </p>
              </>
            ) : (
              <p className="text-xs text-mute">Save the draft first.</p>
            )}
            {funded && (
              <p className="rounded-xl bg-volt-soft p-4 text-xs font-semibold text-volt-ink">
                Funded! Redirecting to the contract page…
              </p>
            )}
          </div>
        )}

        {step < 3 && error && <p className="mt-4 rounded-lg bg-coral-100 px-3 py-2 text-xs text-coral-ink">{error}</p>}

        <div className="mt-6 flex items-center justify-between">
          <button
            className="btn-ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0 || step === 4}
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
          {step < 3 && (
            <button className="btn-volt" onClick={next}>
              Continue <ArrowRight className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

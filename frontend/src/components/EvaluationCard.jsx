import { CheckCircle2, XCircle } from "lucide-react";
import { Chip, SampleTag, ScoreBar } from "./ui.jsx";

export default function EvaluationCard({ evaluation, compact = false }) {
  if (!evaluation) {
    return (
      <div className="card p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-display text-sm font-bold text-ink">Latest AI evaluation</h3>
          <SampleTag />
        </div>
        <div className="rounded-2xl bg-lilac-100 p-4">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-lilac-ink/70">Composite score</p>
          <p className="mt-1 font-display text-4xl font-extrabold text-lilac-ink">96.75%</p>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/70">
            <div className="h-full w-[87%] rounded-full bg-lilac" />
          </div>
          <p className="mt-2 text-[11px] text-lilac-ink/70">Required threshold: 85%</p>
        </div>
        <div className="mt-4 space-y-2.5 text-xs">
          <div className="flex justify-between text-mute"><span>Unit tests</span><span className="font-mono">100%</span></div>
          <div className="flex justify-between text-mute"><span>Schema compliance</span><span className="font-mono">95%</span></div>
          <div className="flex justify-between text-mute"><span>AI review</span><span className="font-mono">92%</span></div>
        </div>
        <p className="mt-4 text-[11px] leading-relaxed text-mute/80">
          Sample values — run a demo on the Overview or Demo Studio page to watch the arbiter score a real deliverable.
        </p>
      </div>
    );
  }

  const captured = evaluation.decision === "CAPTURE";
  const partial = evaluation.decision === "PARTIAL";
  const compositePct = Math.round(evaluation.composite * 10000) / 100;
  const provider = (evaluation.llm_provider || "").startsWith("gemini") ? "Gemini evaluation" : "AI review (heuristic)";
  const panelTone = captured ? "volt" : partial ? "sun" : "coral";

  return (
    <div className="card fade-up p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-display text-sm font-bold text-ink">Latest AI evaluation</h3>
        <Chip tone={captured ? "volt" : partial ? "sun" : "coral"} dot>
          {captured ? "Passed" : partial ? "Partial pass" : "Failed"}
        </Chip>
      </div>

      <div className={`rounded-2xl p-4 ${panelTone === "volt" ? "bg-volt-soft" : panelTone === "sun" ? "bg-sun-100" : "bg-coral-100"}`}>
        <p className={`text-[10px] font-bold uppercase tracking-[0.14em] ${panelTone === "volt" ? "text-volt-ink/70" : panelTone === "sun" ? "text-sun-ink/70" : "text-coral-ink/70"}`}>
          Composite score
        </p>
        <p className={`mt-1 font-display text-4xl font-extrabold ${panelTone === "volt" ? "text-volt-ink" : panelTone === "sun" ? "text-sun-ink" : "text-coral-ink"}`}>
          {compositePct.toFixed(2)}%
        </p>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/80">
          <div
            className={`h-full rounded-full transition-all duration-700 ${panelTone === "volt" ? "bg-volt-deep" : panelTone === "sun" ? "bg-sun" : "bg-coral"}`}
            style={{ width: `${Math.min(compositePct, 100)}%` }}
          />
        </div>
        <p className="mt-2 text-[11px] text-mute">
          {captured && `Required threshold: ${Math.round(evaluation.threshold * 100)}% — met, full capture`}
          {partial && `Below the ${Math.round(evaluation.threshold * 100)}% capture bar but in the partial band — ${Math.round((evaluation.payout_fraction || 0) * 100)}% of the bounty released to the worker`}
          {!captured && !partial && `Below the partial band (${Math.round(evaluation.threshold * 100)}% / 80%) — escrow voided, hirer refunded`}
        </p>
      </div>

      <div className="mt-4 space-y-2.5">
        <ScoreBar label="Unit tests" value={evaluation.scores?.tests} bar="bg-volt-deep" />
        <ScoreBar label="Schema compliance" value={evaluation.scores?.schema} bar="bg-plum-700" />
        <ScoreBar label="AI review" value={evaluation.scores?.llm} bar="bg-lilac" />
      </div>

      {!compact && evaluation.remediation_plan && evaluation.remediation_plan.length > 0 && (
        <div className="mt-4 rounded-xl border border-sun/40 bg-sun-100 p-3">
          <p className="text-[11px] font-bold uppercase tracking-wide text-sun-ink">Remediation plan</p>
          <ul className="mt-1.5 space-y-1">
            {evaluation.remediation_plan.map((item, i) => (
              <li key={i} className="text-[11px] leading-relaxed text-sun-ink/90">• {item}</li>
            ))}
          </ul>
        </div>
      )}

      {!compact && (
        <div className="mt-4 rounded-xl border border-line bg-[#FBFAF5] p-3">
          <p className="flex items-start gap-2 text-[11px] leading-relaxed text-mute">
            {captured || partial ? (
              <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-volt-deep" />
            ) : (
              <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-coral" />
            )}
            {evaluation.llm_rationale || "No rationale recorded."}
            <span className="shrink-0 text-mute/60">[{evaluation.llm_provider}]</span>
          </p>
          <p className="mt-2 text-[10px] text-mute/60">
            Channels: tests 50% + schema 25% + AI review 25% (advisory). The LLM can never trigger settlement alone.
          </p>
        </div>
      )}
    </div>
  );
}

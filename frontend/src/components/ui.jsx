import { Asterisk } from "lucide-react";

export function Chip({ tone = "slate", children, dot = false }) {
  const tones = {
    volt: "bg-volt-soft text-volt-ink border border-volt-deep/40",
    coral: "bg-coral-100 text-coral-ink border border-coral/30",
    lilac: "bg-lilac-100 text-lilac-ink border border-lilac/30",
    sun: "bg-sun-100 text-sun-ink border border-sun/40",
    plum: "bg-plum-100 text-plum-900 border border-plum-900/15",
    slate: "bg-plum-50 text-mute border border-line",
  };
  return (
    <span className={`chip ${tones[tone] || tones.slate}`}>
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${tone === "volt" ? "bg-volt-deep" : tone === "coral" ? "bg-coral" : tone === "lilac" ? "bg-lilac" : tone === "sun" ? "bg-sun" : "bg-mute/50"}`} />}
      {children}
    </span>
  );
}

export function statusTone(status) {
  if (status === "CAPTURED") return "volt";
  if (status === "PARTIAL") return "sun";
  if (status === "REMEDIATION") return "lilac";
  if (status === "VOIDED") return "coral";
  if (status === "AUTHORIZED") return "lilac";
  return "slate";
}

export function StatusChip({ status }) {
  const labels = {
    CAPTURED: "Captured",
    PARTIAL: "Partially captured",
    REMEDIATION: "Remediation round",
    VOIDED: "Voided",
    AUTHORIZED: "Escrow active",
  };
  return <Chip tone={statusTone(status)} dot>{labels[status] || status}</Chip>;
}

export function StatCard({ icon: Icon, label, value, sub, accent = "text-plum-700/50" }) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between">
        <p className="text-sm text-mute">{label}</p>
        {Icon && <Icon className={`h-4 w-4 ${accent}`} />}
      </div>
      <p className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">{value}</p>
      {sub && <p className="mt-1.5 text-xs leading-relaxed text-mute">{sub}</p>}
    </div>
  );
}

export function ScoreBar({ label, value, bar = "bg-lilac", suffix = "%" }) {
  const pct = Math.round((value || 0) * (value <= 1 ? 100 : 1));
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-xs text-mute">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-plum-100">
        <div className={`h-full rounded-full transition-all duration-700 ${bar}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-11 shrink-0 text-right font-mono text-xs text-ink">{pct}{suffix}</span>
    </div>
  );
}

export function SectionHeader({ title, sub, right, badge }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>
        <h2 className="font-display text-base font-bold text-ink">{title}</h2>
        {sub && <p className="mt-0.5 text-xs text-mute">{sub}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {badge}
        {right}
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon, title, body, action }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-white/60 px-6 py-10 text-center">
      {Icon && (
        <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-lilac-100">
          <Icon className="h-5 w-5 text-lilac" />
        </div>
      )}
      <p className="text-sm font-semibold text-ink">{title}</p>
      {body && <p className="mt-1 max-w-sm text-xs leading-relaxed text-mute">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function SampleTag() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-plum-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-mute">
      <Asterisk className="h-3 w-3 text-lilac" /> sample
    </span>
  );
}

export function PageIntro({ title, sub, action }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink sm:text-3xl">{title}</h1>
        {sub && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-mute">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

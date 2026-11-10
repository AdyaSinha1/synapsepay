import { Asterisk, Bot, CheckCircle2, FileSignature, Landmark, Loader2, ShieldCheck } from "lucide-react";

const STAGES = [
  { icon: FileSignature, title: "Hirer agent", sub: "Task & criteria formulated", milestone: "contract_formulated" },
  { icon: Landmark, title: "PayPal vault", sub: "Fiat escrow authorized", milestone: "paypal_authorized" },
  { icon: Bot, title: "Worker agent", sub: "Deliverable produced", milestone: "worker_delivered" },
  { icon: Asterisk, title: "Neural Arbiter", sub: "Tests + schema + AI review", milestone: "arbiter_decision" },
  { icon: ShieldCheck, title: "PayPal settlement", sub: "Capture or void executed", milestone: "paypal_settlement" },
];

export default function Pipeline({ stage, running, decision }) {
  return (
    <ol className="space-y-0">
      {STAGES.map((node, i) => {
        const done = i < stage;
        const active = running && i === stage;
        const failed = i === 4 && done && decision === "VOID";
        const partial = i === 4 && done && decision === "PARTIAL";
        const isArbiter = i === 3;
        const isSettle = i === 4;
        let tint = "bg-plum-50 text-mute/60 border border-line";
        let icon = node.icon;
        if (done && failed) tint = "bg-coral-100 text-coral border border-coral/30";
        else if (done && partial) tint = "bg-sun-100 text-sun border border-sun/40";
        else if (done) tint = "bg-volt-soft text-volt-ink border border-volt-deep/40";
        else if (active) tint = "bg-lilac-100 text-lilac border border-lilac/40";
        else if (isArbiter && !done && !active) tint = "bg-lilac-100/60 text-lilac/80 border border-lilac/20";

        return (
          <li key={node.title}>
            <div className={`flex items-center gap-3 rounded-xl border px-3.5 py-3 transition-all ${active ? "border-lilac/50 bg-lilac-100/50" : "border-transparent"}`}>
              <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${tint}`}>
                {active ? <Loader2 className="h-4 w-4 animate-spin" /> : done ? <CheckCircle2 className="h-4 w-4" /> : icon}
              </div>
              <div className="min-w-0 flex-1">
                <p className={`text-sm font-semibold ${done || active ? "text-ink" : "text-mute/70"}`}>{node.title}</p>
                <p className="truncate text-[11px] text-mute">{node.sub}</p>
              </div>
              {i === 4 && decision && done && (
                <span className={`chip ${failed ? "bg-coral-100 text-coral-ink" : partial ? "bg-sun-100 text-sun-ink" : "bg-volt-soft text-volt-ink"}`}>{decision}</span>
              )}
            </div>
            {i < STAGES.length - 1 && (
              <div className={`ml-[30px] h-4 w-0.5 ${done ? "bg-volt-deep/50" : active ? "flow-dash-active" : "flow-dash"}`} style={{ width: 2 }} />
            )}
          </li>
        );
      })}
    </ol>
  );
}

import { Asterisk, Bot, FileSignature, Landmark, ShieldCheck } from "lucide-react";

const STEPS = [
  { icon: FileSignature, name: "Hirer", desc: "Creates task", tint: "bg-lilac-100 text-plum-800" },
  { icon: Landmark, name: "PayPal", desc: "Locks funds", tint: "bg-lilac-100 text-plum-800" },
  { icon: Bot, name: "Worker", desc: "Does work", tint: "bg-lilac-100 text-plum-800" },
  { icon: Asterisk, name: "Arbiter", desc: "Checks work", tint: "bg-lilac-200 text-lilac-ink" },
  { icon: ShieldCheck, name: "Settlement", desc: "Pay or void", tint: "bg-volt-soft text-volt-ink" },
];

export default function FlowSteps({ compact = false }) {
  return (
    <div className="flex items-start justify-between gap-1">
      {STEPS.map((step, i) => (
        <div key={step.name} className="flex min-w-0 flex-1 items-start">
          <div className="flex min-w-0 flex-col items-center text-center">
            <div className={`flex ${compact ? "h-10 w-10" : "h-12 w-12"} items-center justify-center rounded-full ${step.tint}`}>
              <step.icon className={compact ? "h-4 w-4" : "h-5 w-5"} />
            </div>
            <p className="mt-2 text-xs font-semibold text-ink">{step.name}</p>
            <p className="mt-0.5 text-[10px] leading-tight text-mute">{step.desc}</p>
          </div>
          {i < STEPS.length - 1 && (
            <div className="flow-dash mx-1 mt-5 hidden h-0.5 flex-1 rounded sm:block" />
          )}
        </div>
      ))}
    </div>
  );
}

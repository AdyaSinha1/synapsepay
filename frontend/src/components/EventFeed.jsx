import { useEffect, useMemo, useRef } from "react";

const LEVEL_COLORS = {
  info: "text-mute",
  success: "text-volt-ink",
  warn: "text-coral",
  error: "text-coral",
};

const STAGE_TAGS = {
  contract_formulated: { tag: "CONTRACT", cls: "bg-plum-100 text-plum-800" },
  paypal_authorized: { tag: "PAYPAL", cls: "bg-volt-soft text-volt-ink" },
  worker_execution_start: { tag: "WORKER", cls: "bg-plum-100 text-plum-800" },
  worker_delivered: { tag: "WORKER", cls: "bg-plum-100 text-plum-800" },
  arbiter_start: { tag: "ARBITER", cls: "bg-lilac-100 text-lilac-ink" },
  arbiter_sandbox: { tag: "ARBITER", cls: "bg-lilac-100 text-lilac-ink" },
  arbiter_schema: { tag: "ARBITER", cls: "bg-lilac-100 text-lilac-ink" },
  arbiter_llm: { tag: "ARBITER", cls: "bg-lilac-100 text-lilac-ink" },
  arbiter_decision: { tag: "ARBITER", cls: "bg-lilac-200 text-lilac-ink" },
  paypal_settlement: { tag: "PAYPAL", cls: "bg-volt-soft text-volt-ink" },
  paypal_settlement_failed: { tag: "PAYPAL", cls: "bg-coral-100 text-coral-ink" },
  remediation_opened: { tag: "PROTOCOL", cls: "bg-sun-100 text-sun-ink" },
  cycle_complete: { tag: "SYSTEM", cls: "bg-plum-50 text-mute" },
};

export default function EventFeed({ events, height = "h-64", placeholder = "Waiting for agent activity…" }) {
  const ref = useRef(null);
  const rows = useMemo(() => events.filter((e) => e.stage !== "worker_execution_start"), [events]);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [rows.length]);

  return (
    <div ref={ref} className={`console ${height} p-3`}>
      {rows.length === 0 && <p className="text-mute/60">$ {placeholder}</p>}
      {rows.map((e, i) => {
        const meta = STAGE_TAGS[e.stage] || { tag: (e.stage || "EVENT").toUpperCase(), cls: "bg-plum-50 text-mute" };
        return (
          <p key={`${e.ts}-${i}`} className={`py-0.5 ${LEVEL_COLORS[e.level] || LEVEL_COLORS.info}`}>
            <span className="text-mute/50">[{(e.ts || "").slice(11, 19)}]</span>{" "}
            <span className={`mr-1 inline-block rounded px-1.5 py-px text-[9px] font-bold uppercase tracking-wide ${meta.cls}`}>
              {meta.tag}
            </span>{" "}
            {e.message}
            {e.latency_ms != null && <span className="text-mute/50"> ({e.latency_ms}ms)</span>}
          </p>
        );
      })}
    </div>
  );
}

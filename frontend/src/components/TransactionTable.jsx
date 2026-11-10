import { useState } from "react";
import { ArrowUpRight, ChevronDown, ChevronRight } from "lucide-react";
import { StatusChip } from "./ui.jsx";
import { fmtUSD } from "../api.js";

export default function TransactionTable({ rows, emptyAction }) {
  const [openId, setOpenId] = useState(null);

  if (!rows.length) {
    return (
      <div className="px-6 py-10 text-center">
        <p className="text-sm font-semibold text-ink">No transactions yet</p>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-mute">
          Run a demo scenario — every settlement lands here with its full PayPal receipt.
        </p>
        {emptyAction && <div className="mt-4">{emptyAction}</div>}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px] text-left text-sm">
        <thead>
          <tr className="border-b border-line text-[10px] font-bold uppercase tracking-[0.12em] text-mute">
            <th className="px-6 py-3">Contract</th>
            <th className="px-4 py-3">Amount</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Mode</th>
            <th className="px-4 py-3 text-right">Receipt</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const open = openId === row.id;
            const esc = row.escrow;
            const receipt = esc?.receipt;
            return (
              <tr key={row.id} className="border-b border-line/70 last:border-0">
                <td className="px-6 py-3.5">
                  <button
                    onClick={() => setOpenId(open ? null : row.id)}
                    className="flex items-center gap-2 text-left"
                  >
                    {receipt ? (
                      open ? (
                        <ChevronDown className="h-3.5 w-3.5 shrink-0 text-mute" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-mute" />
                      )
                    ) : (
                      <span className="inline-block h-3.5 w-3.5 shrink-0" />
                    )}
                    <span>
                      <span className="block font-medium text-ink">{row.title}</span>
                      <span className="block font-mono text-[11px] text-mute">SYN-{row.id}</span>
                    </span>
                  </button>
                </td>
                <td className="px-4 py-3.5 font-mono text-ink">
                  {receipt?.captured_amount != null && receipt.captured_amount < receipt.amount
                    ? `${fmtUSD(receipt.captured_amount)} / ${fmtUSD(receipt.amount)}`
                    : fmtUSD(row.bounty_value)}
                </td>
                <td className="px-4 py-3.5">
                  <StatusChip status={esc?.status || "PENDING"} />
                </td>
                <td className="px-4 py-3.5">
                  <span className={`chip ${esc?.mode === "live_sandbox" ? "bg-volt-soft text-volt-ink" : "bg-plum-50 text-mute"}`}>
                    {esc?.mode === "live_sandbox" ? "Live sandbox" : "Simulated"}
                  </span>
                </td>
                <td className="px-4 py-3.5 text-right">
                  {receipt ? (
                    <button
                      onClick={() => setOpenId(open ? null : row.id)}
                      className="text-xs font-semibold text-lilac-ink hover:text-lilac"
                    >
                      {receipt.settlement_type === "CAPTURE"
                        ? "Capture"
                        : receipt.settlement_type === "PARTIAL_CAPTURE"
                          ? "Partial capture"
                          : "Void"}{" "}
                      details
                    </button>
                  ) : (
                    <span className="text-xs text-mute/60">{esc?.status === "REMEDIATION" ? "Remediation" : "Pending"}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {rows.map((row) => {
        if (openId !== row.id) return null;
        const receipt = row.escrow?.receipt;
        if (!receipt) return null;
        const captured = receipt.settlement_type === "CAPTURE";
        return (
          <div key={`${row.id}-detail`} className="fade-up border-t border-line bg-[#FBFAF5] px-6 py-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 text-xs">
                {[
                  ["Order ID", receipt.order_id],
                  ["Authorization ID", receipt.authorization_id],
                  [
                    receipt.settlement_type === "VOID" ? "Void status" : "Capture ID",
                    receipt.settlement_type === "VOID" ? receipt.status : receipt.transaction_id,
                  ],
                  ...(receipt.captured_amount != null && receipt.captured_amount < receipt.amount
                    ? [["Captured / released", `${fmtUSD(receipt.captured_amount)} paid · ${fmtUSD(receipt.released_amount ?? 0)} released back`]]
                    : []),
                  ["Settled at", (receipt.timestamp || "").slice(0, 19).replace("T", " ")],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between gap-3">
                    <span className="text-mute">{label}</span>
                    <span className="truncate font-mono text-ink">{value || "—"}</span>
                  </div>
                ))}
              </div>
              <div className="rounded-xl border border-line bg-white p-3">
                <p className="text-[11px] leading-relaxed text-mute">{receipt.notes}</p>
                <a
                  href={receipt.paypal_dashboard_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-lilac-ink hover:text-lilac"
                >
                  PayPal developer dashboard <ArrowUpRight className="h-3 w-3" />
                </a>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

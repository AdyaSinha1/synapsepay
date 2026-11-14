import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { CheckCircle2, XCircle } from "lucide-react";
import Sidebar from "./Sidebar.jsx";
import Topbar from "./Topbar.jsx";
import { useApp } from "../context.jsx";
import { getMetrics, getContracts, getHealth } from "../api.js";

export default function Shell() {
  const { health, everFailed, errorPanel, showError, toast } = useApp();
  const location = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  const retry = async () => {
    try {
      await Promise.all([getHealth(), getContracts(), getMetrics()]);
    } catch (e) {
      showError(e);
    }
  };

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="min-w-0 flex-1">
        <Topbar />
        {everFailed && !health && (
          <div className="border-b border-sun/40 bg-sun-100 px-5 py-2.5 text-center text-xs font-semibold text-sun-ink sm:px-8">
            Backend waking up — free-tier hosts sleep when idle and can take 30-60s to respond.
            Retrying automatically every 12s; data appears the moment it answers.
          </div>
        )}
        {health?.storage === "ephemeral" && (
          <div className="border-b border-coral/40 bg-coral-100 px-5 py-2.5 text-center text-xs font-semibold text-coral-ink sm:px-8">
            Storage is temporary on this deployment. Data resets on redeploy — set DATABASE_URL to a
            managed Postgres for durable storage.
          </div>
        )}
        <main className="mx-auto max-w-6xl px-4 pb-16 pt-6 sm:px-8 sm:pt-8">
          <Outlet />
        </main>
      </div>

      {errorPanel && (
        <div className="fade-up fixed bottom-6 left-4 right-4 z-50 max-w-sm rounded-2xl border border-coral/40 bg-coral-100 p-4 shadow-card sm:left-6 sm:right-auto">
          <p className="text-xs font-bold uppercase tracking-wide text-coral-ink">Action failed</p>
          <p className="mt-1.5 break-words text-xs leading-relaxed text-coral-ink/90">{errorPanel}</p>
          <p className="mt-1.5 text-[11px] leading-relaxed text-coral-ink/70">
            On free-tier hosting the first request can take up to a minute while the API wakes up.
            Funds are only ever reserved after a successful authorization.
          </p>
          <div className="mt-3 flex gap-2">
            <button className="btn-plum !px-3 !py-1.5 text-xs" onClick={retry}>
              Retry connection
            </button>
            <button className="btn-ghost !px-3 !py-1.5 text-xs" onClick={() => setErrorPanel(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      {toast && (
        <div
          className={`fade-up fixed bottom-6 right-4 z-50 flex max-w-xs items-center gap-2.5 rounded-2xl border px-4 py-3 text-sm font-semibold shadow-card sm:right-6 ${
            toast.tone === "coral"
              ? "border-coral/30 bg-coral-100 text-coral-ink"
              : toast.tone === "lilac"
                ? "border-lilac/30 bg-lilac-100 text-lilac-ink"
                : "border-volt-deep/40 bg-volt-soft text-volt-ink"
          }`}
        >
          {toast.tone === "coral" ? <XCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
          {toast.msg}
        </div>
      )}
    </div>
  );
}

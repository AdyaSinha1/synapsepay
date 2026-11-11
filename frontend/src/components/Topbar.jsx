import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Bell, LogIn, LogOut } from "lucide-react";
import { NAV_ITEMS } from "./Sidebar.jsx";
import { useApp } from "../context.jsx";

const BELL_STAGES = new Set(["paypal_settlement", "flagged_for_review", "remediation_opened", "cycle_complete"]);

function timeOf(evt) {
  return (evt?.ts || "").slice(11, 19);
}

export default function Topbar() {
  const { pathname } = useLocation();
  const { user, logoutUser, health, bellEvents, showError } = useApp();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);

  const base = NAV_ITEMS.find((n) => pathname.startsWith(n.to)) || { label: "Overview" };
  const label = base.label;

  const keyEvents = bellEvents.filter((e) => BELL_STAGES.has(e.stage)).slice(0, 8);

  useEffect(() => {
    const onClick = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-ivory/85 backdrop-blur">
      <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-8">
        <p className="truncate text-sm text-mute">
          Workspace <span className="mx-1 text-line">/</span>
          <span className="font-semibold text-ink">{label}</span>
        </p>
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="relative" ref={boxRef}>
            <button
              onClick={() => setOpen((v) => !v)}
              className="relative flex h-9 w-9 items-center justify-center rounded-full border border-line bg-white text-mute hover:text-ink"
              aria-label="Notifications"
            >
              <Bell className="h-4 w-4" />
              {keyEvents.length > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-coral px-1 text-[9px] font-bold text-white">
                  {keyEvents.length}
                </span>
              )}
            </button>
            {open && (
              <div className="fade-up absolute right-0 mt-2 w-80 rounded-2xl border border-line bg-white p-2 shadow-card">
                <p className="px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-mute">
                  Recent activity
                </p>
                {keyEvents.length === 0 && (
                  <p className="px-3 pb-3 text-xs text-mute">No key events yet.</p>
                )}
                {keyEvents.map((e, i) => (
                  <div key={i} className="rounded-xl px-3 py-2 hover:bg-[#FBFAF5]">
                    <p className="truncate text-xs font-medium text-ink">{e.message}</p>
                    <p className="font-mono text-[10px] text-mute/60">
                      {e.stage} · {timeOf(e)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          <span className="hidden items-center gap-2 rounded-full border border-line bg-white px-3.5 py-1.5 text-xs text-mute sm:inline-flex">
            <span className={`h-2 w-2 rounded-full ${health ? "animate-pulse bg-volt-deep" : "bg-coral"}`} />
            {health
              ? health.paypal_mode === "live_sandbox"
                ? "PayPal sandbox · live keys"
                : "Sandbox environment"
              : "API offline"}
          </span>

          {user ? (
            <button
              onClick={async () => {
                try {
                  await logoutUser();
                  navigate("/");
                } catch (e) {
                  showError(e);
                }
              }}
              className="flex items-center gap-1.5 rounded-full border border-line bg-white px-3 py-1.5 text-xs font-semibold text-mute hover:text-coral"
            >
              <LogOut className="h-3.5 w-3.5" /> Log out
            </button>
          ) : (
            <Link
              to="/login"
              className="inline-flex items-center gap-1.5 rounded-full border border-plum-900/25 bg-white px-3 py-1.5 text-xs font-semibold text-ink hover:border-plum-900/60"
            >
              <LogIn className="h-3.5 w-3.5" /> Sign in
            </Link>
          )}
        </div>
      </div>

      <nav className="flex gap-2 overflow-x-auto px-4 pb-3 md:hidden">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${
              pathname.startsWith(item.to) ? "border-plum-900 bg-plum-900 text-white" : "border-line bg-white text-mute"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

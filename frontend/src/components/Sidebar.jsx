import { NavLink, useLocation } from "react-router-dom";
import {
  ArrowUpRight,
  Asterisk,
  Diamond,
  Home,
  PlayCircle,
  Plus,
  ScrollText,
  UserRound,
  Users,
} from "lucide-react";
import { useApp } from "../context.jsx";

export const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: Home },
  { to: "/contracts", label: "Contracts", icon: ScrollText },
  { to: "/contracts/new", label: "New Contract", icon: Plus, exact: true },
  { to: "/board", label: "Open Board", icon: Users },
  { to: "/studio", label: "Demo Studio", icon: PlayCircle },
  { to: "/agents", label: "AI Agents", icon: Diamond },
  { to: "/arbiter", label: "AI Arbiter", icon: Asterisk },
  { to: "/payments", label: "Payments", icon: ArrowUpRight },
];

export default function Sidebar() {
  const { pathname } = useLocation();
  const { user, health } = useApp();
  const online = Boolean(health);

  const isActive = (item) =>
    item.exact ? pathname === item.to : pathname.startsWith(item.to);

  return (
    <aside className="hidden w-60 shrink-0 flex-col justify-between bg-plum-900 md:sticky md:top-0 md:flex md:h-screen">
      <div>
        <NavLink to="/" className="flex items-center gap-3 px-5 pb-6 pt-6">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-volt font-display text-xl font-extrabold text-plum-900 shadow-volt">
            S
          </div>
          <div>
            <p className="font-display text-lg font-bold leading-tight text-white">
              synapse<span className="text-volt">pay</span>
            </p>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-white/40">
              Agent escrow protocol
            </p>
          </div>
        </NavLink>

        <nav className="space-y-1 px-3">
          {NAV_ITEMS.map(({ to, label, icon: Icon, exact }) => {
            const active = isActive({ to, exact });
            return (
              <NavLink
                key={to}
                to={to}
                className={`flex w-full items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition ${
                  active ? "bg-plum-800 text-white" : "text-white/55 hover:bg-plum-800/50 hover:text-white/90"
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? "text-volt" : "text-white/40"}`} />
                {label}
              </NavLink>
            );
          })}
        </nav>
      </div>

      <div className="px-4 pb-5">
        {user && (
          <NavLink
            to="/settings"
            className="mb-3 flex items-center gap-3 rounded-2xl bg-plum-800 p-3 hover:bg-plum-700"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-lilac-200 font-display text-xs font-bold text-lilac-ink">
              {user.username.slice(0, 2).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-white">{user.display_name}</p>
              <p className="text-[10px] uppercase tracking-wider text-white/40">{user.role}</p>
            </div>
            <UserRound className="ml-auto h-3.5 w-3.5 text-white/30" />
          </NavLink>
        )}
        <div className="rounded-2xl bg-plum-800 p-4">
          <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-volt">
            <span className={`h-2 w-2 rounded-full ${online ? "animate-pulse bg-volt" : "bg-coral"}`} />
            {online ? "System operational" : "Backend offline"}
          </p>
          <p className="mt-2 text-[11px] leading-relaxed text-white/50">
            {online
              ? "Demo mode · transactions simulated. Operator-run arbiter; PayPal holds the funds."
              : "Start the API with run.bat, this panel updates automatically."}
          </p>
          <p className="mt-3 font-mono text-[9px] uppercase tracking-wider text-white/30">
            {online
              ? health.paypal_mode === "live_sandbox"
                ? "PAYPAL SANDBOX · LIVE KEYS"
                : "PAYPAL SANDBOX · SIMULATED"
              : "API OFFLINE"}
          </p>
        </div>
        <p className="px-2 pt-4 font-mono text-[10px] uppercase tracking-wider text-white/25">
          SynapsePay protocol · v2.0.0
        </p>
      </div>
    </aside>
  );
}

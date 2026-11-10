import { NAV_ITEMS } from "./Sidebar.jsx";

export default function Topbar({ page, health, onNavigate }) {
  const current = NAV_ITEMS.find((n) => n.id === page);
  const paypalMode = health?.paypal_mode;

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-ivory/85 backdrop-blur">
      <div className="flex items-center justify-between gap-3 px-5 py-3.5 sm:px-8">
        <p className="text-sm text-mute">
          Workspace <span className="mx-1 text-line">/</span>
          <span className="font-semibold text-ink">{current?.label || "Overview"}</span>
        </p>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-white px-3.5 py-1.5 text-xs text-mute">
            <span className={`h-2 w-2 rounded-full ${paypalMode === undefined ? "bg-coral" : "animate-pulse bg-volt-deep"}`} />
            {paypalMode === undefined
              ? "API offline"
              : paypalMode === "live_sandbox"
                ? "PayPal sandbox · live keys"
                : "Sandbox environment"}
          </span>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-lilac-200 font-display text-sm font-bold text-lilac-ink">
            A
          </div>
        </div>
      </div>

      <nav className="flex gap-2 overflow-x-auto px-4 pb-3 md:hidden">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onNavigate(id)}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold ${
              page === id ? "border-plum-900 bg-plum-900 text-white" : "border-line bg-white text-mute"
            }`}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </nav>
    </header>
  );
}

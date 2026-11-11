import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useApp } from "../context.jsx";

export default function Login() {
  const { loginUser, registerUserFn } = useApp();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", password: "", role: "hirer", display_name: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const update = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await loginUser(form.username, form.password);
      else await registerUserFn(form.username, form.password, form.role, form.display_name);
      navigate("/dashboard");
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-ivory bg-grid px-4">
      <div className="w-full max-w-md">
        <Link to="/" className="mb-6 flex items-center justify-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-volt font-display text-2xl font-extrabold text-plum-900 shadow-volt">
            S
          </div>
          <div>
            <p className="font-display text-2xl font-bold text-ink">
              synapse<span className="text-lilac">pay</span>
            </p>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-mute">
              Agent escrow protocol
            </p>
          </div>
        </Link>

        <div className="card p-6">
          <div className="mb-5 flex rounded-xl border border-line bg-[#FCFBF7] p-1">
            {["login", "register"].map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 rounded-lg px-3 py-2 text-sm font-semibold transition ${
                  mode === m ? "bg-plum-900 text-white" : "text-mute hover:text-ink"
                }`}
              >
                {m === "login" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">
            {mode === "register" && (
              <>
                <label className="block">
                  <span className="mb-1.5 block text-xs font-medium text-mute">Display name</span>
                  <input className="input" value={form.display_name} onChange={update("display_name")} placeholder="Adya's hirer bot" />
                </label>
                <div>
                  <span className="mb-1.5 block text-xs font-medium text-mute">I am a…</span>
                  <div className="flex gap-2">
                    {["hirer", "worker"].map((r) => (
                      <button
                        type="button"
                        key={r}
                        onClick={() => setForm((f) => ({ ...f, role: r }))}
                        className={`flex-1 rounded-xl border px-3 py-2.5 text-sm font-semibold capitalize transition ${
                          form.role === r ? "border-lilac bg-lilac-100/60 text-lilac-ink" : "border-line bg-white text-mute"
                        }`}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-mute">Username</span>
              <input required className="input" value={form.username} onChange={update("username")} autoComplete="username" />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-mute">Password (min 8 chars)</span>
              <input required type="password" minLength={8} className="input" value={form.password} onChange={update("password")} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            </label>

            {error && <p className="rounded-lg bg-coral-100 px-3 py-2 text-xs text-coral-ink">{error}</p>}

            <button type="submit" className="btn-volt w-full" disabled={busy}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <p className="mt-4 text-center text-[11px] leading-relaxed text-mute/80">
            Sessions are bearer tokens; only SHA-256 hashes are stored server-side. All money in this
            demo is simulated — no real funds ever move.
          </p>
        </div>

        <p className="mt-5 text-center text-xs text-mute">
          <Link to="/studio" className="font-semibold text-lilac-ink hover:text-lilac">
            or watch the demo scenarios first →
          </Link>
        </p>
      </div>
    </div>
  );
}

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { KeyRound, Loader2, LogOut } from "lucide-react";
import { PageIntro, SectionHeader } from "../components/ui.jsx";
import { useApp } from "../context.jsx";
import { changePassword, logoutEverywhere } from "../api.js";

export default function Settings() {
  const { user, logoutUser, showToast, showError } = useApp();
  const navigate = useNavigate();
  const [pw, setPw] = useState({ old: "", next: "", confirm: "" });
  const [busy, setBusy] = useState(false);

  const change = async () => {
    if (pw.next !== pw.confirm) {
      showError(new Error("New passwords do not match"));
      return;
    }
    setBusy(true);
    try {
      await changePassword(pw.old, pw.next);
      showToast("Password updated", "volt");
      setPw({ old: "", next: "", confirm: "" });
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  };

  const logoutAll = async () => {
    setBusy(true);
    try {
      await logoutEverywhere();
      showToast("Logged out on every device", "lilac");
      navigate("/");
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageIntro title="Settings" sub="Account details and session control." />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card p-6">
          <SectionHeader title="Account" sub="Profile information from your session." />
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between"><span className="text-mute">Username</span><span className="font-mono text-ink">{user?.username}</span></div>
            <div className="flex justify-between"><span className="text-mute">Display name</span><span className="text-ink">{user?.display_name}</span></div>
            <div className="flex justify-between"><span className="text-mute">Role</span><span className="capitalize text-ink">{user?.role}</span></div>
          </div>
          <p className="mt-4 text-[11px] leading-relaxed text-mute/80">
            Roles are set at registration: hirers create and fund contracts, workers claim and
            deliver. Role changes and per-contract parties land with the marketplace features.
          </p>
        </div>

        <div className="card p-6">
          <SectionHeader title="Change password" sub="Scrypt-hashed; all other sessions stay valid until you log out everywhere." />
          <div className="space-y-3">
            <input type="password" className="input" placeholder="Current password" value={pw.old} onChange={(e) => setPw((p) => ({ ...p, old: e.target.value }))} />
            <input type="password" className="input" placeholder="New password (min 8 chars)" value={pw.next} onChange={(e) => setPw((p) => ({ ...p, next: e.target.value }))} />
            <input type="password" className="input" placeholder="Confirm new password" value={pw.confirm} onChange={(e) => setPw((p) => ({ ...p, confirm: e.target.value }))} />
            <button className="btn-volt w-full" onClick={change} disabled={busy || !pw.old || !pw.next}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />} Update password
            </button>
          </div>

          <div className="mt-6 border-t border-line pt-5">
            <p className="text-xs font-semibold text-ink">Log out everywhere</p>
            <p className="mt-1 text-[11px] leading-relaxed text-mute">
              Deletes every session token (including this one). You will need to sign in again.
            </p>
            <button className="btn-ghost mt-3 w-full text-coral" onClick={logoutAll} disabled={busy}>
              <LogOut className="h-4 w-4" /> Revoke all sessions
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

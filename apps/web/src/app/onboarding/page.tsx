"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, toError, type ApiError } from "@/lib/api/client";
import { ErrorBox } from "@/components/States";

const PERSONAS = [
  ["ai_ml", "AI / ML engineer"],
  ["fullstack", "Full-stack developer"],
  ["data_analyst", "Data analyst"],
] as const;

export default function Onboarding() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [persona, setPersona] = useState<(typeof PERSONAS)[number][0]>("ai_ml");
  const [error, setError] = useState<ApiError>();
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    const r = mode === "signin"
      ? await api.POST("/auth/login", { body: { email, password } })
      : await api.POST("/auth/register", { body: { email, password, persona } });
    setBusy(false);
    if (r.error || !r.response.ok) setError(toError(r.response.status, r.error));
    else router.replace("/inbox");
  }

  return (
    <div className="min-h-screen grid place-items-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4" aria-label={mode === "signin" ? "Sign in" : "Create account"}>
        <div>
          <h1 className="text-2xl font-bold">GigBid</h1>
          <p className="text-sm text-muted">Your freelance copilot. It drafts; you approve every proposal and message.</p>
        </div>
        <div role="tablist" className="flex gap-1">
          {(["signin", "register"] as const).map((m) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
              className={`btn flex-1 justify-center ${mode === m ? "btn-primary" : ""}`}>
              {m === "signin" ? "Sign in" : "Create account"}
            </button>
          ))}
        </div>
        <label className="block text-sm">Email
          <input name="email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className="input w-full mt-1" />
        </label>
        <label className="block text-sm">Password
          <input name="password" type="password" required minLength={8} autoComplete={mode === "signin" ? "current-password" : "new-password"}
            value={password} onChange={(e) => setPassword(e.target.value)} className="input w-full mt-1" />
        </label>
        {mode === "register" && (
          <fieldset className="text-sm">
            <legend className="mb-1">Which profile are you?</legend>
            {PERSONAS.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 py-0.5">
                <input type="radio" name="persona" value={value} checked={persona === value} onChange={() => setPersona(value)} />
                {label}
              </label>
            ))}
          </fieldset>
        )}
        {error && <ErrorBox error={error} />}
        <button type="submit" className="btn btn-primary w-full justify-center" disabled={busy}>
          {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
        </button>
      </form>
    </div>
  );
}

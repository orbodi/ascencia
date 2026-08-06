import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Button, Input } from "../components/ui";

export function LoginPage() {
  const { user, loading, login } = useAuth();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur de connexion");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <section className="relative hidden lg:flex flex-col justify-between p-12 text-white overflow-hidden bg-[linear-gradient(145deg,#0c2220_0%,#143532_48%,#0d7a5f_140%)]">
        <div
          className="absolute inset-0 opacity-30"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 20%, rgba(213,239,230,0.25), transparent 40%), radial-gradient(circle at 80% 70%, rgba(13,122,95,0.45), transparent 45%)",
          }}
        />
        <div className="relative animate-fade-up">
          <div className="text-xs uppercase tracking-[0.2em] text-white/50 mb-6">
            Université — emplois du temps
          </div>
          <h1 className="font-[family-name:var(--font-display)] text-6xl leading-[0.95] tracking-tight max-w-md">
            Ascencia
          </h1>
          <p className="mt-5 text-white/70 max-w-sm text-base leading-relaxed">
            Pilotez plannings, absences et validations depuis un espace unique.
          </p>
        </div>
        <div className="relative text-sm text-white/45 animate-fade-up stagger-2">
          Assistant IA · Planning · Notifications
        </div>
      </section>

      <section className="relative flex items-center justify-center p-6 sm:p-10 app-shell">
        <div className="relative z-10 w-full max-w-md animate-fade-up">
          <div className="lg:hidden mb-8">
            <div className="font-[family-name:var(--font-display)] text-4xl text-ink">
              Ascencia
            </div>
            <p className="text-ink-soft text-sm mt-2">
              Connexion au back-office
            </p>
          </div>

          <div className="bg-white/85 backdrop-blur-sm border border-line rounded-3xl p-8 shadow-[0_1px_0_rgba(16,42,42,0.04)]">
            <div className="mb-6 hidden lg:block">
              <h2 className="font-[family-name:var(--font-display)] text-3xl text-ink">
                Connexion
              </h2>
              <p className="text-ink-soft text-sm mt-2">
                Accédez à l&apos;espace d&apos;administration
              </p>
            </div>
            <form className="space-y-4" onSubmit={onSubmit}>
              <Input
                label="Identifiant"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
              <Input
                label="Mot de passe"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
              {error ? (
                <div className="text-sm text-warn bg-warn/10 rounded-xl px-3 py-2.5 border border-warn/20">
                  {error}
                </div>
              ) : null}
              <Button className="w-full mt-2" disabled={busy}>
                {busy ? "Connexion…" : "Se connecter"}
              </Button>
            </form>
          </div>
        </div>
      </section>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Badge } from "./ui";
import { Sidebar } from "./Sidebar";

export function Layout() {
  const { user, loading, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center app-shell text-ink-soft">
        <div className="animate-fade-in text-sm tracking-wide">Chargement…</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;

  return (
    <div className="min-h-screen flex app-shell relative">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="relative z-10 flex-1 flex flex-col min-w-0">
        <header className="min-h-16 px-3 sm:px-5 lg:px-6 flex items-center justify-between gap-3 border-b border-line/70 bg-white/80 backdrop-blur-md sticky top-0 z-20">
          <div className="flex items-center gap-2 min-w-0">
            <button
              type="button"
              className="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-brand-blue hover:bg-brand-blue-soft lg:hidden"
              aria-label="Ouvrir le menu"
              aria-controls="main-navigation"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
            >
              <span aria-hidden className="text-xl">☰</span>
            </button>
            <img
              src="/backoffice/logo-ak.png"
              alt="Ascencia Keyce"
              className="h-10 w-24 object-contain lg:hidden"
            />
            <div className="hidden lg:block text-sm text-ink-soft font-medium tracking-wide">
              Centre de pilotage académique
            </div>
            {demoMode ? <Badge tone="warn">Mode démonstration</Badge> : null}
          </div>
          <div className="flex items-center gap-2 sm:gap-3 text-sm min-w-0">
            <span className="font-semibold text-ink truncate max-w-24 sm:max-w-none">
              {user.username}
            </span>
            <Badge tone="accent">{user.role}</Badge>
            <button
              onClick={logout}
              className="hidden sm:inline min-h-11 text-ink-soft hover:text-accent-deep transition font-medium underline-offset-4 hover:underline"
            >
              Déconnexion
            </button>
          </div>
        </header>
        <main className="flex-1 p-4 sm:p-6 md:p-8">
          <div className="max-w-6xl mx-auto animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { Badge } from "./ui";
import { Sidebar } from "./Sidebar";

export function Layout() {
  const { user, loading, logout } = useAuth();

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
      <Sidebar />
      <div className="relative z-10 flex-1 flex flex-col min-w-0">
        <header className="h-14 px-6 flex items-center justify-between border-b border-line/70 bg-white/55 backdrop-blur-md">
          <div className="text-sm text-ink-soft font-medium tracking-wide">
            Espace administration
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="font-semibold text-ink">{user.username}</span>
            <Badge tone="accent">{user.role}</Badge>
            <button
              onClick={logout}
              className="text-ink-soft hover:text-accent-deep transition font-medium underline-offset-4 hover:underline"
            >
              Déconnexion
            </button>
          </div>
        </header>
        <main className="flex-1 p-6 md:p-8 overflow-auto">
          <div className="max-w-6xl mx-auto animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

import { NavLink } from "react-router-dom";

const sections = [
  {
    title: "Vue d'ensemble",
    links: [
      { to: "/", label: "Dashboard" },
      { to: "/schedule", label: "Planning" },
      { to: "/changes", label: "Notifications" },
      { to: "/chat", label: "Chat agent" },
    ],
  },
  {
    title: "Référentiel",
    links: [
      { to: "/levels", label: "Niveaux / Parcours" },
      { to: "/teachers", label: "Enseignants" },
      { to: "/groups", label: "Groupes" },
      { to: "/rooms", label: "Salles" },
      { to: "/courses", label: "Cours" },
    ],
  },
  {
    title: "Administration",
    links: [
      { to: "/history", label: "Historique" },
      { to: "/config", label: "Config IA" },
    ],
  },
];

export function Sidebar() {
  return (
    <aside className="relative z-20 w-[15.5rem] shrink-0 flex flex-col text-white bg-[linear-gradient(180deg,var(--color-sidebar)_0%,var(--color-sidebar-mid)_100%)] border-r border-white/5">
      <div className="px-5 pt-7 pb-6">
        <div className="flex items-center gap-3">
          <div
            className="h-9 w-9 rounded-xl bg-accent/90 grid place-items-center font-[family-name:var(--font-display)] text-lg text-white"
            aria-hidden
          >
            A
          </div>
          <div>
            <div className="font-[family-name:var(--font-display)] text-[1.65rem] leading-none tracking-tight">
              Ascencia
            </div>
            <div className="text-[11px] text-white/50 mt-1 tracking-wide">
              Emplois du temps
            </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 pb-6 space-y-5 overflow-y-auto">
        {sections.map((section) => (
          <div key={section.title}>
            <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/35">
              {section.title}
            </div>
            <div className="space-y-0.5">
              {section.links.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  end={l.to === "/"}
                  className={({ isActive }) =>
                    `group relative block rounded-xl px-3 py-2 text-[0.9rem] transition duration-150 ${
                      isActive
                        ? "bg-accent text-white font-medium"
                        : "text-white/70 hover:bg-white/10 hover:text-white"
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive ? (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-r bg-white/80" />
                      ) : null}
                      {l.label}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="px-5 py-4 border-t border-white/8 text-[11px] text-white/35">
        Back-office universitaire
      </div>
    </aside>
  );
}

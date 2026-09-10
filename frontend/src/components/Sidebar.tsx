import { NavLink } from "react-router-dom";
import { Icon } from "./Icon";

type SidebarProps = {
  open: boolean;
  onClose: () => void;
};

const sections = [
  {
    title: "Vue d'ensemble",
    links: [
      { to: "/", label: "Tableau de bord", icon: "dashboard" },
      { to: "/schedule", label: "Planning", icon: "calendar" },
      { to: "/publications", label: "Génération & publication", icon: "check" },
      { to: "/changes", label: "Validations", icon: "check" },
      { to: "/chat", label: "Assistant IA", icon: "chat" },
    ],
  },
  {
    title: "Référentiel",
    links: [
      { to: "/levels", label: "Niveaux / Parcours", icon: "levels" },
      { to: "/teachers", label: "Enseignants", icon: "teachers" },
      { to: "/groups", label: "Groupes", icon: "groups" },
      { to: "/rooms", label: "Salles", icon: "rooms" },
      { to: "/courses", label: "Cours", icon: "courses" },
    ],
  },
  {
    title: "Administration",
    links: [
      { to: "/history", label: "Traçabilité", icon: "history" },
      { to: "/config", label: "Configuration IA", icon: "settings" },
    ],
  },
];

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <>
      <button
        type="button"
        aria-label="Fermer le menu"
        className={`fixed inset-0 z-30 bg-ink/55 backdrop-blur-sm transition-opacity lg:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
      />
      <aside
        id="main-navigation"
        className={`fixed inset-y-0 left-0 z-40 w-[17rem] shrink-0 flex flex-col text-white bg-[linear-gradient(180deg,var(--color-sidebar)_0%,var(--color-sidebar-mid)_100%)] border-r border-white/10 shadow-2xl transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:z-20 lg:translate-x-0 lg:shadow-none ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="px-4 pt-5 pb-5">
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-xl bg-white grid place-items-center overflow-hidden shrink-0">
              <img
                src="/backoffice/logo-ak.png"
                alt=""
                className="w-11 h-11 object-contain"
              />
            </div>
            <div className="min-w-0">
              <div className="font-[family-name:var(--font-display)] text-[1.35rem] leading-none tracking-tight">
                Ascencia Keyce
              </div>
              <div className="text-[10px] text-white/65 mt-1 tracking-wide">
                Pilotage des emplois du temps
              </div>
            </div>
            <button
              type="button"
              className="ml-auto grid h-11 w-11 place-items-center rounded-xl text-white/75 hover:bg-white/10 hover:text-white lg:hidden"
              aria-label="Fermer le menu"
              onClick={onClose}
            >
              <span aria-hidden className="text-2xl leading-none">×</span>
            </button>
          </div>
        </div>

        <nav className="flex-1 px-3 pb-6 space-y-5 overflow-y-auto">
          {sections.map((section) => (
            <div key={section.title}>
              <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-white/45">
                {section.title}
              </div>
              <div className="space-y-0.5">
                {section.links.map((link) => (
                  <NavLink
                    key={link.to}
                    to={link.to}
                    end={link.to === "/"}
                    onClick={onClose}
                    className={({ isActive }) =>
                      `group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[0.9rem] transition duration-150 ${
                        isActive
                          ? "bg-white text-sidebar font-semibold shadow-sm"
                          : "text-white/75 hover:bg-white/10 hover:text-white"
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive ? (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-r bg-accent" />
                        ) : null}
                        <Icon name={link.icon} className="h-[1.1rem] w-[1.1rem] shrink-0" />
                        <span>{link.label}</span>
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="px-5 py-4 border-t border-white/10 text-[11px] text-white/50">
          <span className="mb-1 inline-flex rounded-md bg-white/10 px-2 py-1 font-semibold text-white/80">Données de démonstration</span>
          <div>Ascencia Keyce Togo · Lomé</div>
        </div>
      </aside>
    </>
  );
}

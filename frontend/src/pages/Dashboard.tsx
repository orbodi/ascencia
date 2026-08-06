import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Card, PageHeader } from "../components/ui";

type Dashboard = {
  teachers_count: number;
  courses_count: number;
  groups_count: number;
  rooms_count: number;
  pending_changes: number;
  scheduled_this_week: number;
};

export function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Dashboard>("/admin/dashboard"),
  });

  const cards = [
    {
      label: "Enseignants",
      value: data?.teachers_count,
      hint: "Référentiel actif",
      to: "/teachers",
      tone: "default" as const,
    },
    {
      label: "Cours",
      value: data?.courses_count,
      hint: "Volumes horaires",
      to: "/courses",
      tone: "default" as const,
    },
    {
      label: "Groupes",
      value: data?.groups_count,
      hint: "Promotions",
      to: "/groups",
      tone: "default" as const,
    },
    {
      label: "Salles",
      value: data?.rooms_count,
      hint: "Capacités",
      to: "/rooms",
      tone: "default" as const,
    },
    {
      label: "Notifications",
      value: data?.pending_changes,
      hint: "En attente de validation",
      to: "/changes",
      tone: "warn" as const,
    },
    {
      label: "Séances semaine",
      value: data?.scheduled_this_week,
      hint: "Planning courant",
      to: "/schedule",
      tone: "accent" as const,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Vue d'ensemble de l'activité universitaire"
      />
      {isLoading ? (
        <p className="text-ink-soft animate-fade-in">Chargement…</p>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {cards.map((c, i) => (
            <Link
              key={c.label}
              to={c.to}
              className={`animate-fade-up stagger-${i + 1} group`}
            >
              <Card className="p-5 h-full transition duration-200 group-hover:-translate-y-0.5 group-hover:border-accent/30">
                <div className="flex items-start justify-between gap-3">
                  <div className="text-[0.8rem] font-medium text-ink-soft tracking-wide">
                    {c.label}
                  </div>
                  <span
                    className={`h-2 w-2 rounded-sm mt-1.5 ${
                      c.tone === "warn"
                        ? "bg-warn"
                        : c.tone === "accent"
                          ? "bg-accent"
                          : "bg-line"
                    }`}
                  />
                </div>
                <div className="mt-3 font-[family-name:var(--font-display)] text-4xl text-ink tracking-tight">
                  {c.value ?? "—"}
                </div>
                <div className="mt-2 text-xs text-ink-soft/80">{c.hint}</div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

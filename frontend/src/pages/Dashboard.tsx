import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Card, PageHeader } from "../components/ui";

type Dashboard = {
  teachers_count: number;
  active_teachers_count: number;
  teachers_with_whatsapp: number;
  availability_responses_count: number;
  collection_progress_percent: number;
  whatsapp_coverage_percent: number;
  courses_count: number;
  groups_count: number;
  rooms_count: number;
  pending_changes: number;
  approved_changes: number;
  scheduled_this_week: number;
  cancelled_this_week: number;
  whatsapp_conversations_count: number;
};

function Progress({ value, label }: { value: number; label: string }) {
  const safeValue = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-ink">{label}</span>
        <span className="font-semibold text-brand-blue">{safeValue}%</span>
      </div>
      <div
        className="h-2.5 overflow-hidden rounded-full bg-mist"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={safeValue}
      >
        <div
          className="h-full rounded-full bg-[linear-gradient(90deg,var(--color-brand-blue),var(--color-accent))] transition-all"
          style={{ width: `${safeValue}%` }}
        />
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Dashboard>("/admin/dashboard"),
  });

  const cards = [
    {
      label: "Enseignants actifs",
      value: data?.active_teachers_count,
      hint: `${data?.teachers_with_whatsapp ?? 0} joignables sur WhatsApp`,
      to: "/teachers",
      tone: "blue",
    },
    {
      label: "Séances cette semaine",
      value: data?.scheduled_this_week,
      hint: `${data?.cancelled_this_week ?? 0} annulée(s)`,
      to: "/schedule",
      tone: "orange",
    },
    {
      label: "Validations requises",
      value: data?.pending_changes,
      hint: `${data?.approved_changes ?? 0} décision(s) approuvée(s)`,
      to: "/changes",
      tone: "orange",
    },
    {
      label: "Conversations WhatsApp",
      value: data?.whatsapp_conversations_count,
      hint: "Interlocuteurs distincts",
      to: "/history",
      tone: "blue",
    },
  ];

  return (
    <div>
      <PageHeader
        title="Tableau de bord"
        subtitle="Suivi de la collecte, de la planification et des validations humaines"
        actions={<Badge tone="accent">Système supervisé</Badge>}
      />

      <Card className="mb-6 overflow-hidden border-brand-blue/20 bg-[linear-gradient(110deg,var(--color-sidebar)_0%,var(--color-brand-blue)_72%,var(--color-accent)_140%)] p-5 text-white sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="max-w-2xl">
            <div className="mb-2 inline-flex rounded-lg bg-white/12 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-white/90">Environnement de démonstration</div>
            <h2 className="font-[family-name:var(--font-display)] text-2xl">Un scénario complet, sans confusion avec des données réelles</h2>
            <p className="mt-2 text-sm leading-relaxed text-white/75">Les personnes et coordonnées sont fictives. Les contrôles de disponibilité, de capacité, de conflit et de validation utilisent toutefois la même logique que pour une exploitation réelle.</p>
          </div>
          <Link to="/chat" className="inline-flex min-h-11 shrink-0 items-center justify-center rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-brand-blue shadow-lg transition hover:-translate-y-0.5">Lancer la démonstration →</Link>
        </div>
      </Card>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Chargement du tableau de bord">
          {Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="h-36 animate-pulse rounded-2xl border border-line bg-white/70" />
          ))}
        </div>
      ) : error ? (
        <Card className="p-5 border-warn/30">
          <p className="font-semibold text-ink">Le tableau de bord n’a pas pu être chargé.</p>
          <button className="mt-2 min-h-11 text-sm font-semibold text-accent underline" onClick={() => void refetch()}>
            Réessayer
          </button>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map((card, index) => (
              <Link key={card.label} to={card.to} className={`animate-fade-up stagger-${index + 1} group`}>
                <Card className="h-full p-5 transition duration-200 group-hover:-translate-y-0.5 group-hover:border-brand-blue/30">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-[0.78rem] font-semibold uppercase tracking-wide text-ink-soft">
                      {card.label}
                    </div>
                    <span className={`mt-1 h-2.5 w-2.5 rounded-full ${card.tone === "orange" ? "bg-accent" : "bg-brand-blue"}`} />
                  </div>
                  <div className="mt-3 font-[family-name:var(--font-display)] text-4xl tracking-tight text-ink">
                    {card.value ?? "—"}
                  </div>
                  <div className="mt-2 text-xs text-ink-soft">{card.hint}</div>
                </Card>
              </Link>
            ))}
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <Card className="p-5 sm:p-6">
              <div className="mb-6">
                <h2 className="font-[family-name:var(--font-display)] text-2xl text-ink">Collecte des disponibilités</h2>
                <p className="mt-1 text-sm text-ink-soft">Indicateurs nécessaires avant de lancer une génération fiable.</p>
              </div>
              <div className="space-y-6">
                <Progress value={data?.collection_progress_percent ?? 0} label="Réponses structurées" />
                <Progress value={data?.whatsapp_coverage_percent ?? 0} label="Couverture WhatsApp" />
              </div>
              <div className="mt-6 grid grid-cols-2 gap-3 border-t border-line pt-5 text-sm">
                <div>
                  <div className="text-ink-soft">Disponibilités reçues</div>
                  <div className="mt-1 text-xl font-semibold text-ink">{data?.availability_responses_count ?? 0} / {data?.active_teachers_count ?? 0}</div>
                </div>
                <div>
                  <div className="text-ink-soft">Référentiel</div>
                  <div className="mt-1 text-xl font-semibold text-ink">{data?.courses_count ?? 0} cours</div>
                </div>
              </div>
            </Card>

            <Card className="p-5 sm:p-6">
              <h2 className="font-[family-name:var(--font-display)] text-2xl text-ink">Chaîne de traitement</h2>
              <p className="mt-1 text-sm text-ink-soft">Le contrôle humain reste obligatoire avant diffusion.</p>
              <ol className="mt-5 space-y-3">
                {[
                  ["1", "Données académiques", `${data?.groups_count ?? 0} groupes · ${data?.rooms_count ?? 0} salles`],
                  ["2", "Collecte conversationnelle", `${data?.collection_progress_percent ?? 0}% complétée`],
                  ["3", "Planification sous contraintes", `${data?.scheduled_this_week ?? 0} séances planifiées`],
                  ["4", "Validation humaine", `${data?.pending_changes ?? 0} décision(s) en attente`],
                  ["5", "Publication et notification", "Export PDF et WhatsApp"],
                ].map(([number, title, detail]) => (
                  <li key={number} className="flex gap-3 rounded-xl border border-line/80 bg-paper/70 p-3">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-blue text-sm font-bold text-white">{number}</span>
                    <div>
                      <div className="text-sm font-semibold text-ink">{title}</div>
                      <div className="text-xs text-ink-soft">{detail}</div>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

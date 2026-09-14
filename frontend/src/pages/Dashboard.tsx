import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Card, Input, PageHeader } from "../components/ui";

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

type PlanningCycle = {
  phase: string;
  today: string;
  collection_start_date: string | null;
  publication_date: string | null;
  target_week_start: string | null;
  collection_sent_at: string | null;
  publication_sent_at: string | null;
  availability_responses_count: number;
  active_teachers_count: number;
  can_run_collection: boolean;
  can_run_publication: boolean;
  message?: string;
};

const PHASE_LABEL: Record<string, string> = {
  idle: "Non planifié",
  scheduled: "Collecte planifiée",
  ready_to_collect: "Prêt à contacter les professeurs",
  collecting: "Collecte en cours",
  ready_to_publish: "Prêt à générer / publier",
  published: "Planning envoyé aux admins",
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
  const qc = useQueryClient();
  const [collectionDate, setCollectionDate] = useState("");
  const [publicationDate, setPublicationDate] = useState("");
  const [targetWeek, setTargetWeek] = useState("");
  const [cycleMsg, setCycleMsg] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<Dashboard>("/admin/dashboard"),
  });

  const { data: cycle } = useQuery({
    queryKey: ["planning-cycle"],
    queryFn: () => api<PlanningCycle>("/admin/planning-cycle"),
  });

  useEffect(() => {
    if (!cycle) return;
    setCollectionDate(cycle.collection_start_date || "");
    setPublicationDate(cycle.publication_date || "");
    setTargetWeek(cycle.target_week_start || "");
  }, [cycle]);

  const saveDates = useMutation({
    mutationFn: () =>
      api<PlanningCycle>("/admin/planning-cycle/dates", {
        method: "PUT",
        body: JSON.stringify({
          collection_start_date: collectionDate || null,
          publication_date: publicationDate || null,
          target_week_start: targetWeek || null,
        }),
      }),
    onSuccess: () => {
      setCycleMsg("Dates enregistrées. Le cycle a été réinitialisé.");
      void qc.invalidateQueries({ queryKey: ["planning-cycle"] });
    },
    onError: (err: Error) => setCycleMsg(err.message),
  });

  const runCycle = useMutation({
    mutationFn: () =>
      api<{ actions: string[]; message?: string; status?: PlanningCycle }>(
        "/admin/planning-cycle/run",
        { method: "POST" }
      ),
    onSuccess: (result) => {
      const actions = result.actions?.length
        ? result.actions.join(", ")
        : result.message || "Aucune action";
      setCycleMsg(actions);
      void qc.invalidateQueries({ queryKey: ["planning-cycle"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err: Error) => setCycleMsg(err.message),
  });

  function onSaveDates(e: FormEvent) {
    e.preventDefault();
    setCycleMsg(null);
    saveDates.mutate();
  }

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
      label: "Réponses dispos",
      value: data?.availability_responses_count,
      hint: `sur ${data?.active_teachers_count ?? 0} actifs`,
      to: "/teachers",
      tone: "orange",
    },
    {
      label: "Conversations WhatsApp",
      value: data?.whatsapp_conversations_count,
      hint: "Interlocuteurs distincts",
      to: "/chat",
      tone: "blue",
    },
  ];

  return (
    <div>
      <PageHeader
        title="Tableau de bord"
        subtitle="Collecte WhatsApp, génération et publication du planning"
        actions={<Badge tone="accent">Cycle planifié</Badge>}
      />

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <div
              key={index}
              className="h-36 animate-pulse rounded-2xl border border-line bg-white/70"
            />
          ))}
        </div>
      ) : error ? (
        <Card className="border-warn/30 p-5">
          <p className="font-semibold text-ink">
            Le tableau de bord n’a pas pu être chargé.
          </p>
          <button
            className="mt-2 min-h-11 text-sm font-semibold text-accent underline"
            onClick={() => void refetch()}
          >
            Réessayer
          </button>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map((card, index) => (
              <Link
                key={card.label}
                to={card.to}
                className={`animate-fade-up stagger-${index + 1} group`}
              >
                <Card className="h-full p-5 transition duration-200 group-hover:-translate-y-0.5 group-hover:border-brand-blue/30">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-[0.78rem] font-semibold uppercase tracking-wide text-ink-soft">
                      {card.label}
                    </div>
                    <span
                      className={`mt-1 h-2.5 w-2.5 rounded-full ${
                        card.tone === "orange" ? "bg-accent" : "bg-brand-blue"
                      }`}
                    />
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
              <div className="mb-4">
                <h2 className="font-[family-name:var(--font-display)] text-2xl text-ink">
                  Calendrier du cycle
                </h2>
                <p className="mt-1 text-sm text-ink-soft">
                  Configurez la date de collecte WhatsApp et la date d’envoi du
                  planning aux administrateurs.
                </p>
              </div>

              <form className="space-y-4" onSubmit={onSaveDates}>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Input
                    label="Début collecte disponibilités"
                    type="date"
                    value={collectionDate}
                    onChange={(e) => setCollectionDate(e.target.value)}
                    required
                  />
                  <Input
                    label="Date de publication (envoi admins)"
                    type="date"
                    value={publicationDate}
                    onChange={(e) => setPublicationDate(e.target.value)}
                    required
                  />
                </div>
                <Input
                  label="Semaine cible du planning (lundi, optionnel)"
                  type="date"
                  value={targetWeek}
                  onChange={(e) => setTargetWeek(e.target.value)}
                />
                <div className="flex flex-wrap gap-2">
                  <Button type="submit" disabled={saveDates.isPending}>
                    {saveDates.isPending ? "Enregistrement…" : "Enregistrer les dates"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={runCycle.isPending}
                    onClick={() => {
                      setCycleMsg(null);
                      runCycle.mutate();
                    }}
                  >
                    {runCycle.isPending
                      ? "Exécution…"
                      : "Lancer / avancer le cycle"}
                  </Button>
                </div>
              </form>

              {cycleMsg ? (
                <p className="mt-4 text-sm text-ink-soft">{cycleMsg}</p>
              ) : null}

              <div className="mt-6 space-y-3 border-t border-line pt-5 text-sm">
                <div className="flex justify-between gap-3">
                  <span className="text-ink-soft">Phase</span>
                  <span className="font-semibold">
                    {PHASE_LABEL[cycle?.phase || "idle"] || cycle?.phase}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-ink-soft">Collecte WhatsApp</span>
                  <span>
                    {cycle?.collection_sent_at
                      ? `envoyée (${cycle.collection_sent_at.slice(0, 16)})`
                      : "en attente"}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-ink-soft">Publication admins</span>
                  <span>
                    {cycle?.publication_sent_at
                      ? `envoyée (${cycle.publication_sent_at.slice(0, 16)})`
                      : "en attente"}
                  </span>
                </div>
              </div>
            </Card>

            <Card className="p-5 sm:p-6">
              <h2 className="font-[family-name:var(--font-display)] text-2xl text-ink">
                Collecte des disponibilités
              </h2>
              <p className="mt-1 text-sm text-ink-soft">
                À la date de début, l’agent contacte les professeurs via WhatsApp.
              </p>
              <div className="mt-6 space-y-6">
                <Progress
                  value={data?.collection_progress_percent ?? 0}
                  label="Réponses structurées"
                />
                <Progress
                  value={data?.whatsapp_coverage_percent ?? 0}
                  label="Couverture WhatsApp"
                />
              </div>
              <ol className="mt-6 space-y-3 border-t border-line pt-5">
                {[
                  ["1", "Date collecte", "Contact WhatsApp des professeurs"],
                  ["2", "Réponses", "Disponibilités / indisponibilités"],
                  ["3", "Date publication", "Génération + envoi PDF aux admins"],
                ].map(([number, title, detail]) => (
                  <li
                    key={number}
                    className="flex gap-3 rounded-xl border border-line/80 bg-paper/70 p-3"
                  >
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-blue text-sm font-bold text-white">
                      {number}
                    </span>
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

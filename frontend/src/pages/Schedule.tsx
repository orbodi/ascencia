import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, PageHeader } from "../components/ui";

type Entry = {
  id: number;
  course_id: number;
  room_id: number;
  timeslot_id: number;
  entry_date: string;
  status: string;
  course_title?: string;
  teacher_name?: string;
  group_name?: string;
  room_name?: string;
  timeslot_label?: string;
};

function mondayOf(d: Date): Date {
  const x = new Date(d);
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day);
  x.setHours(0, 0, 0, 0);
  return x;
}

function fmt(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

const STATUS_COLOR: Record<string, string> = {
  scheduled: "bg-brand-blue-soft border-brand-blue/30 text-brand-blue",
  cancelled: "bg-red-50 border-red-200 text-red-700",
  confirmed: "bg-emerald-100 border-emerald-300 text-emerald-800",
  moved: "bg-amber-50 border-amber-200 text-amber-800",
};

const STATUS_LABEL: Record<string, string> = {
  scheduled: "Planifiée",
  cancelled: "Annulée",
  moved: "Déplacée",
};

export function SchedulePage() {
  const qc = useQueryClient();
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const [selected, setSelected] = useState<Entry | null>(null);

  const weekParam = fmt(weekStart);
  const { data = [], isLoading, error, refetch } = useQuery({
    queryKey: ["schedule", weekParam],
    queryFn: () =>
      api<Entry[]>(`/admin/schedule?week_start=${weekParam}`),
  });

  const cancel = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/schedule/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      setSelected(null);
      void qc.invalidateQueries({ queryKey: ["schedule"] });
    },
  });

  const days = useMemo(() => {
    return Array.from({ length: 5 }, (_, i) => {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [weekStart]);

  const byDate = useMemo(() => {
    const map: Record<string, Entry[]> = {};
    for (const e of data) {
      (map[e.entry_date] ||= []).push(e);
    }
    return map;
  }, [data]);

  return (
    <div>
      <PageHeader
        title="Planning semaine"
        subtitle={`Du ${days[0].toLocaleDateString("fr-FR", { day: "2-digit", month: "long" })} au ${days[4].toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" })}`}
        actions={
          <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto">
            <Button
              variant="ghost"
              onClick={() => {
                const d = new Date(weekStart);
                d.setDate(d.getDate() - 7);
                setWeekStart(d);
              }}
            >
              ← Semaine préc.
            </Button>
            <Button
              variant="ghost"
              onClick={() => setWeekStart(mondayOf(new Date()))}
            >
              Aujourd’hui
            </Button>
            <Button
              className="col-span-2 sm:col-span-1"
              variant="ghost"
              onClick={() => {
                const d = new Date(weekStart);
                d.setDate(d.getDate() + 7);
                setWeekStart(d);
              }}
            >
              Semaine suiv. →
            </Button>
          </div>
        }
      />
      {!isLoading && !error ? (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-lg bg-brand-blue-soft px-3 py-1.5 font-semibold text-brand-blue">{data.filter((entry) => entry.status === "scheduled").length} séance(s) planifiée(s)</span>
          <span className="rounded-lg bg-red-50 px-3 py-1.5 font-semibold text-red-700">{data.filter((entry) => entry.status === "cancelled").length} annulée(s)</span>
          <span className="text-ink-soft">Sélectionnez une séance pour consulter son détail.</span>
        </div>
      ) : null}
      {isLoading ? (
        <p className="text-ink-soft">Chargement…</p>
      ) : error ? (
        <Card className="p-5 border-warn/30">
          <p className="font-semibold">Le planning n’a pas pu être chargé.</p>
          <button
            className="mt-2 min-h-11 text-sm font-semibold text-accent underline"
            onClick={() => void refetch()}
          >
            Réessayer
          </button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {days.map((d) => {
            const key = fmt(d);
            const entries = byDate[key] || [];
            return (
              <Card key={key} className="p-3 min-h-40 xl:min-h-56">
                <div className="text-xs uppercase tracking-wide text-ink-soft mb-2">
                  {d.toLocaleDateString("fr-FR", {
                    weekday: "short",
                    day: "2-digit",
                    month: "short",
                  })}
                </div>
                <div className="space-y-2">
                  {entries.length === 0 ? (
                    <div className="text-xs text-ink-soft/70 italic">Libre</div>
                  ) : (
                    entries.map((e) => (
                      <button
                        key={e.id}
                        onClick={() => setSelected(e)}
                        className={`w-full min-h-11 text-left rounded-xl border px-3 py-2.5 text-xs transition hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue ${
                          STATUS_COLOR[e.status] || STATUS_COLOR.scheduled
                        }`}
                      >
                        <div className="font-semibold">
                          {e.course_title || `Cours #${e.course_id}`}
                        </div>
                        <div className="opacity-80 mt-0.5">
                          {e.timeslot_label} · {e.room_name}
                        </div>
                        <div className="opacity-70">{e.teacher_name}</div>
                      </button>
                    ))
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {selected ? (
        <div
          className="fixed inset-0 bg-ink/55 grid place-items-center p-4 z-50"
          role="presentation"
          onMouseDown={() => setSelected(null)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="schedule-detail-title"
            className="w-full max-w-md"
            onMouseDown={(event) => event.stopPropagation()}
          >
          <Card className="w-full p-5 sm:p-6">
            <h3 id="schedule-detail-title" className="text-xl font-[family-name:var(--font-display)] mb-3">
              Séance #{selected.id}
            </h3>
            <dl className="text-sm space-y-2 mb-5">
              <div className="flex justify-between gap-4">
                <dt className="text-ink-soft">Cours</dt>
                <dd>{selected.course_title}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-ink-soft">Enseignant</dt>
                <dd>{selected.teacher_name}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-ink-soft">Groupe</dt>
                <dd>{selected.group_name}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-ink-soft">Salle</dt>
                <dd>{selected.room_name}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-ink-soft">Créneau</dt>
                <dd>{selected.timeslot_label}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-ink-soft">Date</dt>
                <dd>{selected.entry_date}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-ink-soft">Statut</dt>
                <dd>{STATUS_LABEL[selected.status] || selected.status}</dd>
              </div>
            </dl>
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" onClick={() => setSelected(null)}>
                Fermer
              </Button>
              {selected.status === "scheduled" ? (
                <Button
                  variant="danger"
                  onClick={() => cancel.mutate(selected.id)}
                >
                  Annuler la séance
                </Button>
              ) : null}
            </div>
          </Card>
          </div>
        </div>
      ) : null}
    </div>
  );
}

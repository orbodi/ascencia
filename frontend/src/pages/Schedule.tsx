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
  scheduled: "bg-accent-soft border-accent/30 text-accent",
  cancelled: "bg-red-50 border-red-200 text-red-700",
  confirmed: "bg-emerald-100 border-emerald-300 text-emerald-800",
  rescheduled: "bg-amber-50 border-amber-200 text-amber-800",
};

export function SchedulePage() {
  const qc = useQueryClient();
  const [weekStart, setWeekStart] = useState(() =>
    mondayOf(new Date("2026-08-03"))
  );
  const [selected, setSelected] = useState<Entry | null>(null);

  const weekParam = fmt(weekStart);
  const { data = [], isLoading } = useQuery({
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
        subtitle="Grille des séances (cliquer pour détail)"
        actions={
          <div className="flex gap-2">
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
              onClick={() => setWeekStart(mondayOf(new Date("2026-08-03")))}
            >
              Semaine démo
            </Button>
            <Button
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
      {isLoading ? (
        <p className="text-ink-soft">Chargement…</p>
      ) : (
        <div className="grid md:grid-cols-5 gap-3">
          {days.map((d) => {
            const key = fmt(d);
            const entries = byDate[key] || [];
            return (
              <Card key={key} className="p-3 min-h-56">
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
                        className={`w-full text-left rounded-xl border px-2.5 py-2 text-xs ${
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
        <div className="fixed inset-0 bg-ink/40 grid place-items-center p-4 z-50">
          <Card className="w-full max-w-md p-6">
            <h3 className="text-xl font-[family-name:var(--font-display)] mb-3">
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
                <dd>{selected.status}</dd>
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
      ) : null}
    </div>
  );
}

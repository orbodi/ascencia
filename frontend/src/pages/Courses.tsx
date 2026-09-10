import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, PageHeader } from "../components/ui";

type Course = {
  id: number;
  title: string;
  teacher_name?: string;
  group_name?: string;
  planned_minutes: number;
  duration_minutes: number;
  scheduled_sessions?: number;
  planned_hours?: string;
  hours_done?: string;
  hours_remaining?: string;
  semester: number;
  priority: number;
  prerequisite_course_id: number | null;
};

function progressPct(c: Course): number {
  const done = (c.scheduled_sessions || 0) * c.duration_minutes;
  if (!c.planned_minutes) return 0;
  return Math.min(100, Math.round((done / c.planned_minutes) * 100));
}

export function CoursesPage() {
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery({
    queryKey: ["courses"],
    queryFn: () => api<Course[]>("/admin/courses"),
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/courses/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["courses"] }),
  });

  return (
    <div>
      <PageHeader
        title="Suivi des cours"
        subtitle="Heures faites / prévues par matière"
      />
      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-mist text-left">
            <tr>
              <th className="px-4 py-3">Cours</th>
              <th className="px-4 py-3">Prof</th>
              <th className="px-4 py-3">Groupe</th>
              <th className="px-4 py-3">Règles</th>
              <th className="px-4 py-3">Progression</th>
              <th className="px-4 py-3">Prévu</th>
              <th className="px-4 py-3">Fait</th>
              <th className="px-4 py-3">Restant</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={9} className="px-4 py-4 text-ink-soft">
                  Chargement…
                </td>
              </tr>
            ) : (
              data.map((c) => {
                const pct = progressPct(c);
                return (
                  <tr key={c.id} className="border-t border-line">
                    <td className="px-4 py-3 font-medium">{c.title}</td>
                    <td className="px-4 py-3">{c.teacher_name}</td>
                    <td className="px-4 py-3">{c.group_name}</td>
                    <td className="px-4 py-3 text-xs text-ink-soft">S{c.semester} · priorité {c.priority}{c.prerequisite_course_id ? ` · prérequis #${c.prerequisite_course_id}` : ""}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-28 rounded-full bg-mist overflow-hidden">
                          <div
                            className="h-full bg-accent"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="text-xs text-ink-soft">{pct}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">{c.planned_hours}</td>
                    <td className="px-4 py-3">{c.hours_done}</td>
                    <td className="px-4 py-3">{c.hours_remaining}</td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        variant="ghost"
                        onClick={() => remove.mutate(c.id)}
                      >
                        Supprimer
                      </Button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

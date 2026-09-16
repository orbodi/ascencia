import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, Input, PageHeader, Select } from "../components/ui";

type Course = {
  id: number;
  title: string;
  teacher_id: number;
  group_id: number;
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

type Teacher = { id: number; name: string; is_active: boolean };
type Group = { id: number; name: string };

const empty = {
  title: "",
  teacher_id: "",
  group_id: "",
  duration_hours: 2,
  planned_hours: 12,
  semester: 1,
  priority: 0,
  prerequisite_course_id: "",
};

function hoursToMinutes(hours: number): number {
  return Math.round(Number(hours) * 60);
}

function minutesToHours(minutes: number): number {
  return Math.round((Number(minutes) / 60) * 100) / 100;
}

function progressPct(c: Course): number {
  const done = (c.scheduled_sessions || 0) * c.duration_minutes;
  if (!c.planned_minutes) return 0;
  return Math.min(100, Math.round((done / c.planned_minutes) * 100));
}

export function CoursesPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(empty);
  const [localError, setLocalError] = useState<string | null>(null);
  const { data = [], isLoading } = useQuery({
    queryKey: ["courses"],
    queryFn: () => api<Course[]>("/admin/courses"),
  });
  const { data: teachers = [] } = useQuery({
    queryKey: ["teachers"],
    queryFn: () => api<Teacher[]>("/admin/teachers"),
    enabled: open,
  });
  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => api<Group[]>("/admin/groups"),
    enabled: open,
  });

  const save = useMutation({
    mutationFn: () =>
      api(editingId ? `/admin/courses/${editingId}` : "/admin/courses", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify({
          title: form.title.trim(),
          teacher_id: Number(form.teacher_id),
          group_id: Number(form.group_id),
          duration_minutes: hoursToMinutes(form.duration_hours),
          planned_minutes: hoursToMinutes(form.planned_hours),
          semester: Number(form.semester),
          priority: Number(form.priority),
          prerequisite_course_id: form.prerequisite_course_id
            ? Number(form.prerequisite_course_id)
            : null,
        }),
      }),
    onSuccess: () => {
      closeModal();
      void qc.invalidateQueries({ queryKey: ["courses"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/courses/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["courses"] }),
  });

  function closeModal() {
    setOpen(false);
    setEditingId(null);
    setForm(empty);
    setLocalError(null);
    save.reset();
  }

  function openCreate() {
    setEditingId(null);
    setForm(empty);
    setLocalError(null);
    save.reset();
    setOpen(true);
  }

  function openEdit(c: Course) {
    setEditingId(c.id);
    setForm({
      title: c.title,
      teacher_id: String(c.teacher_id),
      group_id: String(c.group_id),
      duration_hours: minutesToHours(c.duration_minutes),
      planned_hours: minutesToHours(c.planned_minutes),
      semester: c.semester,
      priority: c.priority,
      prerequisite_course_id: c.prerequisite_course_id
        ? String(c.prerequisite_course_id)
        : "",
    });
    setLocalError(null);
    save.reset();
    setOpen(true);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLocalError(null);
    if (!form.title.trim()) {
      setLocalError("L'intitulé est obligatoire");
      return;
    }
    if (!form.teacher_id || !form.group_id) {
      setLocalError("Choisissez un enseignant et un groupe");
      return;
    }
    if (form.planned_hours < form.duration_hours) {
      setLocalError(
        "Le volume prévu doit être au moins égal à la durée d'une séance"
      );
      return;
    }
    if (form.duration_hours <= 0 || form.planned_hours <= 0) {
      setLocalError("Les durées doivent être positives");
      return;
    }
    save.mutate();
  }

  const activeTeachers = teachers.filter((t) => t.is_active !== false);
  const teacherOptions =
    editingId != null
      ? teachers.filter(
          (t) => t.is_active !== false || String(t.id) === form.teacher_id
        )
      : activeTeachers;

  const sessionsEstimate = useMemo(() => {
    if (!form.duration_hours) return 0;
    return Math.floor(form.planned_hours / form.duration_hours);
  }, [form.duration_hours, form.planned_hours]);

  const canCreate = activeTeachers.length > 0 && groups.length > 0;

  return (
    <div>
      <PageHeader
        title="Suivi des cours"
        subtitle="Heures faites / prévues par matière"
        actions={<Button onClick={openCreate}>Ajouter</Button>}
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
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-4 text-ink-soft">
                  Aucun cours. Cliquez sur Ajouter pour en créer un.
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
                    <td className="px-4 py-3 text-xs text-ink-soft">
                      S{c.semester} · priorité {c.priority}
                      {c.prerequisite_course_id
                        ? ` · prérequis #${c.prerequisite_course_id}`
                        : ""}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-2 w-28 overflow-hidden rounded-full bg-mist">
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
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button variant="ghost" onClick={() => openEdit(c)}>
                          Modifier
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() => {
                            if (
                              window.confirm(
                                `Supprimer le cours « ${c.title} » ?`
                              )
                            ) {
                              remove.mutate(c.id);
                            }
                          }}
                        >
                          Supprimer
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </Card>

      {open ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-ink/55 p-4"
          role="presentation"
          onMouseDown={closeModal}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="course-form-title"
            className="w-full max-w-lg"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <Card className="w-full p-5 sm:p-6">
              <h3
                id="course-form-title"
                className="mb-4 text-xl font-[family-name:var(--font-display)]"
              >
                {editingId ? "Modifier le cours" : "Nouveau cours"}
              </h3>
              {!canCreate && !editingId ? (
                <p className="mb-3 text-sm text-warn">
                  {activeTeachers.length === 0
                    ? "Ajoutez d'abord un enseignant actif."
                    : "Ajoutez d'abord un groupe."}
                </p>
              ) : null}
              <form className="space-y-3" onSubmit={onSubmit}>
                <Input
                  label="Intitulé"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  required
                  autoFocus
                  placeholder="Algorithmique"
                />
                <Select
                  label="Enseignant"
                  value={form.teacher_id}
                  onChange={(e) =>
                    setForm({ ...form, teacher_id: e.target.value })
                  }
                  required
                >
                  <option value="">Choisir…</option>
                  {teacherOptions.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                      {t.is_active === false ? " (archivé)" : ""}
                    </option>
                  ))}
                </Select>
                <Select
                  label="Groupe"
                  value={form.group_id}
                  onChange={(e) =>
                    setForm({ ...form, group_id: e.target.value })
                  }
                  required
                >
                  <option value="">Choisir…</option>
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </Select>
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Durée séance (h)"
                    type="number"
                    min={0.25}
                    max={12}
                    step={0.25}
                    value={form.duration_hours}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        duration_hours: Number(e.target.value),
                      })
                    }
                    required
                  />
                  <Input
                    label="Volume prévu (h)"
                    type="number"
                    min={0.25}
                    step={0.25}
                    value={form.planned_hours}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        planned_hours: Number(e.target.value),
                      })
                    }
                    required
                  />
                </div>
                <p className="text-xs text-ink-soft -mt-1">
                  Environ {sessionsEstimate} séance
                  {sessionsEstimate > 1 ? "s" : ""} sur le semestre.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <Select
                    label="Semestre"
                    value={form.semester}
                    onChange={(e) =>
                      setForm({ ...form, semester: Number(e.target.value) })
                    }
                  >
                    <option value={1}>S1</option>
                    <option value={2}>S2</option>
                  </Select>
                  <Input
                    label="Priorité"
                    type="number"
                    min={0}
                    max={100}
                    value={form.priority}
                    onChange={(e) =>
                      setForm({ ...form, priority: Number(e.target.value) })
                    }
                  />
                </div>
                <Select
                  label="Prérequis (optionnel)"
                  value={form.prerequisite_course_id}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      prerequisite_course_id: e.target.value,
                    })
                  }
                >
                  <option value="">Aucun</option>
                  {data
                    .filter((c) => c.id !== editingId)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title}
                        {c.group_name ? ` — ${c.group_name}` : ""}
                      </option>
                    ))}
                </Select>
                {localError || save.isError ? (
                  <p className="text-sm text-warn">
                    {localError ||
                      (save.error as Error)?.message ||
                      "Enregistrement impossible"}
                  </p>
                ) : null}
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="ghost" onClick={closeModal}>
                    Annuler
                  </Button>
                  <Button
                    type="submit"
                    disabled={
                      save.isPending || (!editingId && !canCreate)
                    }
                  >
                    {save.isPending
                      ? "Enregistrement…"
                      : editingId
                        ? "Enregistrer"
                        : "Ajouter"}
                  </Button>
                </div>
              </form>
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  );
}

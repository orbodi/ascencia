import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, Input, PageHeader, Select } from "../components/ui";

type Level = { id: number; code: string; label: string };

type Course = {
  id: number;
  title: string;
  group_id: number;
  group_name?: string;
  semester: number;
  duration_minutes: number;
};

type Group = {
  id: number;
  name: string;
  academic_level_id: number | null;
};

type WeekItem = {
  id?: number;
  course_id: number;
  course_title?: string | null;
  sessions_count: number;
  duration_minutes?: number | null;
};

type CurriculumPlan = {
  id: number;
  academic_level_id: number;
  academic_level_code?: string | null;
  academic_level_label?: string | null;
  semester: number;
  week_count: number;
  weeks: { week_index: number; items: WeekItem[] }[];
  volume_warnings: string[];
};

const createEmpty = { levelId: "", semester: 1, weekCount: 6 };

export function CurriculumPage() {
  const qc = useQueryClient();
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [weekIndex, setWeekIndex] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState(createEmpty);
  const [addCourseId, setAddCourseId] = useState("");
  const [addSessions, setAddSessions] = useState(1);
  const [draftItems, setDraftItems] = useState<WeekItem[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const { data: plans = [], isLoading } = useQuery({
    queryKey: ["curriculum-plans"],
    queryFn: () => api<CurriculumPlan[]>("/admin/curriculum-plans"),
  });
  const { data: levels = [] } = useQuery({
    queryKey: ["levels"],
    queryFn: () => api<Level[]>("/admin/levels"),
  });
  const { data: courses = [] } = useQuery({
    queryKey: ["courses"],
    queryFn: () => api<Course[]>("/admin/courses"),
  });
  const { data: groups = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => api<Group[]>("/admin/groups"),
  });

  const selected =
    plans.find((p) => p.id === selectedPlanId) || plans[0] || null;

  useEffect(() => {
    if (!selectedPlanId && plans[0]) setSelectedPlanId(plans[0].id);
  }, [plans, selectedPlanId]);

  useEffect(() => {
    if (!selected) {
      setDraftItems([]);
      return;
    }
    const week = selected.weeks.find((w) => w.week_index === weekIndex);
    setDraftItems(week ? week.items.map((i) => ({ ...i })) : []);
    if (weekIndex > selected.week_count) setWeekIndex(1);
  }, [selected, weekIndex]);

  const groupLevel = useMemo(() => {
    const map = new Map<number, number | null>();
    for (const g of groups) map.set(g.id, g.academic_level_id);
    return map;
  }, [groups]);

  const eligibleCourses = useMemo(() => {
    if (!selected) return [];
    return courses.filter(
      (c) =>
        c.semester === selected.semester &&
        groupLevel.get(c.group_id) === selected.academic_level_id
    );
  }, [courses, selected, groupLevel]);

  const createPlan = useMutation({
    mutationFn: () =>
      api<CurriculumPlan>("/admin/curriculum-plans", {
        method: "POST",
        body: JSON.stringify({
          academic_level_id: Number(createForm.levelId),
          semester: Number(createForm.semester),
          week_count: Number(createForm.weekCount),
        }),
      }),
    onSuccess: (plan) => {
      setMsg("Programme créé");
      setSelectedPlanId(plan.id);
      setWeekIndex(1);
      closeCreateModal();
      void qc.invalidateQueries({ queryKey: ["curriculum-plans"] });
    },
    onError: (err: Error) => setLocalError(err.message),
  });

  const saveWeek = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Aucun programme");
      return api<CurriculumPlan>(
        `/admin/curriculum-plans/${selected.id}/weeks/${weekIndex}`,
        {
          method: "PUT",
          body: JSON.stringify({
            items: draftItems.map((i) => ({
              course_id: i.course_id,
              sessions_count: i.sessions_count,
            })),
          }),
        }
      );
    },
    onSuccess: (plan) => {
      setMsg(
        plan.volume_warnings?.length
          ? `Semaine ${weekIndex} enregistrée (avertissements volume).`
          : `Semaine ${weekIndex} enregistrée.`
      );
      void qc.invalidateQueries({ queryKey: ["curriculum-plans"] });
    },
    onError: (err: Error) => setMsg(err.message),
  });

  const removePlan = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/curriculum-plans/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setSelectedPlanId(null);
      setMsg("Programme supprimé");
      void qc.invalidateQueries({ queryKey: ["curriculum-plans"] });
    },
  });

  function closeCreateModal() {
    setCreateOpen(false);
    setCreateForm(createEmpty);
    setLocalError(null);
    createPlan.reset();
  }

  function openCreate() {
    setCreateForm(createEmpty);
    setLocalError(null);
    createPlan.reset();
    setCreateOpen(true);
  }

  function onCreate(e: FormEvent) {
    e.preventDefault();
    setLocalError(null);
    if (!createForm.levelId) {
      setLocalError("Choisissez un parcours");
      return;
    }
    if (createForm.weekCount < 1 || createForm.weekCount > 52) {
      setLocalError("Le nombre de semaines doit être entre 1 et 52");
      return;
    }
    createPlan.mutate();
  }

  function addItem() {
    const courseId = Number(addCourseId);
    if (!courseId) return;
    if (draftItems.some((i) => i.course_id === courseId)) {
      setMsg("Ce cours est déjà dans la semaine");
      return;
    }
    if (addSessions < 1) {
      setMsg("Le nombre de séances doit être au moins 1");
      return;
    }
    const course = eligibleCourses.find((c) => c.id === courseId);
    setDraftItems([
      ...draftItems,
      {
        course_id: courseId,
        course_title: course?.title,
        sessions_count: addSessions,
        duration_minutes: course?.duration_minutes,
      },
    ]);
    setAddCourseId("");
    setAddSessions(1);
    setMsg(null);
  }

  return (
    <div>
      <PageHeader
        title="Programme pédagogique"
        subtitle="Pré-définir les cours à programmer par semaine et par parcours"
        actions={<Button onClick={openCreate}>Ajouter</Button>}
      />

      {msg ? (
        <Card className="mb-4 border-brand-blue/20 p-3 text-sm">{msg}</Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <Card className="h-fit p-5">
          <h2 className="mb-3 font-semibold">Programmes</h2>
          {isLoading ? (
            <p className="text-sm text-ink-soft">Chargement…</p>
          ) : plans.length === 0 ? (
            <p className="text-sm text-ink-soft">
              Aucun programme. Cliquez sur Ajouter pour en créer un.
            </p>
          ) : (
            <ul className="space-y-2">
              {plans.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className={`w-full rounded-xl border px-3 py-2 text-left text-sm transition ${
                      selected?.id === p.id
                        ? "border-brand-blue bg-brand-blue/5"
                        : "border-line hover:border-brand-blue/40"
                    }`}
                    onClick={() => {
                      setSelectedPlanId(p.id);
                      setWeekIndex(1);
                      setMsg(null);
                    }}
                  >
                    <div className="font-medium">
                      {p.academic_level_code || p.academic_level_id} · S
                      {p.semester}
                    </div>
                    <div className="text-xs text-ink-soft">
                      {p.week_count} semaines
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card className="p-5 sm:p-6">
          {!selected ? (
            <p className="text-ink-soft">
              Créez un programme pour un parcours (ex. B1 Info), puis renseignez
              chaque semaine.
            </p>
          ) : (
            <>
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-[family-name:var(--font-display)] text-2xl">
                    {selected.academic_level_label ||
                      selected.academic_level_code}{" "}
                    · Semestre {selected.semester}
                  </h2>
                  <p className="mt-1 text-sm text-ink-soft">
                    Intentions de cours — le moteur placera créneaux et salles
                    selon les disponibilités.
                  </p>
                </div>
                <Button
                  variant="ghost"
                  onClick={() => {
                    if (
                      window.confirm(
                        "Supprimer ce programme et toutes ses semaines ?"
                      )
                    ) {
                      removePlan.mutate(selected.id);
                    }
                  }}
                >
                  Supprimer
                </Button>
              </div>

              {selected.volume_warnings?.length ? (
                <div className="mb-4 rounded-xl border border-warn/30 bg-warn/5 p-3 text-sm">
                  {selected.volume_warnings.map((w) => (
                    <div key={w}>{w}</div>
                  ))}
                </div>
              ) : null}

              <div className="mb-4 flex flex-wrap gap-2">
                {Array.from(
                  { length: selected.week_count },
                  (_, i) => i + 1
                ).map((n) => {
                  const count =
                    selected.weeks.find((w) => w.week_index === n)?.items
                      .length || 0;
                  return (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setWeekIndex(n)}
                      className={`min-h-11 rounded-xl border px-3 text-sm font-medium ${
                        weekIndex === n
                          ? "border-brand-blue bg-brand-blue text-white"
                          : "border-line bg-white text-ink hover:border-brand-blue/40"
                      }`}
                    >
                      S{n}
                      {count ? (
                        <span className="ml-1 opacity-80">({count})</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>

              <h3 className="mb-3 font-semibold">Semaine {weekIndex}</h3>

              {eligibleCourses.length === 0 ? (
                <p className="mb-4 text-sm text-warn">
                  Aucun cours éligible pour ce parcours / semestre. Ajoutez des
                  cours rattachés à un groupe de ce parcours.
                </p>
              ) : (
                <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_100px_auto]">
                  <Select
                    label="Cours"
                    value={addCourseId}
                    onChange={(e) => setAddCourseId(e.target.value)}
                  >
                    <option value="">Ajouter un cours…</option>
                    {eligibleCourses
                      .filter(
                        (c) => !draftItems.some((d) => d.course_id === c.id)
                      )
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.title}
                          {c.group_name ? ` — ${c.group_name}` : ""}
                        </option>
                      ))}
                  </Select>
                  <Input
                    label="Séances"
                    type="number"
                    min={1}
                    max={20}
                    value={addSessions}
                    onChange={(e) => setAddSessions(Number(e.target.value))}
                  />
                  <div className="flex items-end">
                    <Button
                      type="button"
                      onClick={addItem}
                      disabled={!addCourseId}
                    >
                      Ajouter
                    </Button>
                  </div>
                </div>
              )}

              <table className="mb-4 w-full text-sm">
                <thead className="bg-mist text-left">
                  <tr>
                    <th className="px-3 py-2">Cours</th>
                    <th className="px-3 py-2">Séances</th>
                    <th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {draftItems.length === 0 ? (
                    <tr>
                      <td colSpan={3} className="px-3 py-4 text-ink-soft">
                        Aucun cours pour cette semaine.
                      </td>
                    </tr>
                  ) : (
                    draftItems.map((item) => (
                      <tr key={item.course_id} className="border-t border-line">
                        <td className="px-3 py-2 font-medium">
                          {item.course_title || `#${item.course_id}`}
                        </td>
                        <td className="px-3 py-2">
                          <input
                            type="number"
                            min={1}
                            max={20}
                            className="w-20 rounded-lg border border-line px-2 py-1"
                            value={item.sessions_count}
                            onChange={(e) =>
                              setDraftItems(
                                draftItems.map((d) =>
                                  d.course_id === item.course_id
                                    ? {
                                        ...d,
                                        sessions_count: Number(e.target.value),
                                      }
                                    : d
                                )
                              )
                            }
                          />
                        </td>
                        <td className="px-3 py-2 text-right">
                          <Button
                            variant="ghost"
                            onClick={() =>
                              setDraftItems(
                                draftItems.filter(
                                  (d) => d.course_id !== item.course_id
                                )
                              )
                            }
                          >
                            Retirer
                          </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>

              <Button
                disabled={saveWeek.isPending}
                onClick={() => {
                  setMsg(null);
                  saveWeek.mutate();
                }}
              >
                {saveWeek.isPending
                  ? "Enregistrement…"
                  : `Enregistrer la semaine ${weekIndex}`}
              </Button>
            </>
          )}
        </Card>
      </div>

      {createOpen ? (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-ink/55 p-4"
          role="presentation"
          onMouseDown={closeCreateModal}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="curriculum-create-title"
            className="w-full max-w-lg"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <Card className="w-full p-5 sm:p-6">
              <h3
                id="curriculum-create-title"
                className="mb-4 text-xl font-[family-name:var(--font-display)]"
              >
                Nouveau programme
              </h3>
              {levels.length === 0 ? (
                <p className="mb-3 text-sm text-warn">
                  Ajoutez d&apos;abord un parcours (Niveaux / Parcours).
                </p>
              ) : null}
              <form className="space-y-3" onSubmit={onCreate}>
                <Select
                  label="Parcours"
                  value={createForm.levelId}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, levelId: e.target.value })
                  }
                  required
                  autoFocus
                >
                  <option value="">Choisir…</option>
                  {levels.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.label}
                    </option>
                  ))}
                </Select>
                <div className="grid grid-cols-2 gap-3">
                  <Select
                    label="Semestre"
                    value={createForm.semester}
                    onChange={(e) =>
                      setCreateForm({
                        ...createForm,
                        semester: Number(e.target.value),
                      })
                    }
                  >
                    <option value={1}>S1</option>
                    <option value={2}>S2</option>
                  </Select>
                  <Input
                    label="Nb semaines"
                    type="number"
                    min={1}
                    max={52}
                    value={createForm.weekCount}
                    onChange={(e) =>
                      setCreateForm({
                        ...createForm,
                        weekCount: Number(e.target.value),
                      })
                    }
                  />
                </div>
                {localError || createPlan.isError ? (
                  <p className="text-sm text-warn">
                    {localError ||
                      (createPlan.error as Error)?.message ||
                      "Création impossible"}
                  </p>
                ) : null}
                <div className="flex justify-end gap-2 pt-2">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={closeCreateModal}
                  >
                    Annuler
                  </Button>
                  <Button
                    type="submit"
                    disabled={createPlan.isPending || levels.length === 0}
                  >
                    {createPlan.isPending ? "Création…" : "Ajouter"}
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

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, getToken } from "../lib/api";
import {
  Button,
  Card,
  ConfirmDialog,
  Input,
  Modal,
  PageHeader,
  Select,
} from "../components/ui";

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

type Course = { id: number; title: string; group_name?: string };
type Room = { id: number; name: string; capacity: number };
type TimeSlot = {
  id: number;
  day_of_week: number;
  start_time: string;
  end_time: string;
  label: string;
};

type PdfFetchResult = {
  blob: Blob;
  filename: string;
  mediaType: string;
};

const entryEmpty = {
  course_id: "",
  room_id: "",
  timeslot_id: "",
  entry_date: "",
};

const slotEmpty = {
  day_of_week: 0,
  start_time: "08:00",
  end_time: "10:00",
  label: "",
};

const DAY_LABELS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];

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

function dayOfWeekMondayBased(isoDate: string): number {
  const d = new Date(`${isoDate}T12:00:00`);
  return (d.getDay() + 6) % 7;
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

function filenameFromDisposition(
  header: string | null,
  fallback: string
): string {
  if (!header) return fallback;
  const utf = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf?.[1]) return decodeURIComponent(utf[1].trim());
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim() || fallback;
}

function formatApiError(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed = JSON.parse(err.message);
      if (parsed?.conflicts && Array.isArray(parsed.conflicts)) {
        return parsed.conflicts
          .map((c: { message?: string }) => c.message || "Conflit")
          .join(" · ");
      }
    } catch {
      /* plain string detail */
    }
    if (err.message.includes("[object Object]")) {
      return "Conflit de planning détecté";
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return "Action impossible";
}

async function fetchWeekPdf(
  weekStart: string,
  options: { preview?: boolean } = {}
): Promise<PdfFetchResult> {
  const params = new URLSearchParams({ week_start: weekStart });
  if (options.preview) params.set("preview", "true");
  const response = await fetch(`/admin/schedule/export/pdf?${params}`, {
    headers: { Authorization: `Bearer ${getToken() || ""}` },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail || "Export PDF impossible");
  }
  const blob = await response.blob();
  return {
    blob,
    filename: filenameFromDisposition(
      response.headers.get("Content-Disposition"),
      `EDT_SEMAINE_${weekStart}.pdf`
    ),
    mediaType: response.headers.get("Content-Type") || blob.type,
  };
}

async function downloadWeekPdf(weekStart: string) {
  const { blob, filename } = await fetchWeekPdf(weekStart);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function SchedulePage() {
  const qc = useQueryClient();
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const [selected, setSelected] = useState<Entry | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState(entryEmpty);
  const [localError, setLocalError] = useState<string | null>(null);
  const [entryActionError, setEntryActionError] = useState<string | null>(null);
  const [confirmDeleteEntry, setConfirmDeleteEntry] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewName, setPreviewName] = useState<string | null>(null);
  const [slotsOpen, setSlotsOpen] = useState(false);
  const [slotForm, setSlotForm] = useState(slotEmpty);
  const [editingSlotId, setEditingSlotId] = useState<number | null>(null);
  const [slotError, setSlotError] = useState<string | null>(null);
  const [confirmDeleteSlot, setConfirmDeleteSlot] = useState<TimeSlot | null>(
    null
  );
  const [presetsMessage, setPresetsMessage] = useState<string | null>(null);

  const weekParam = fmt(weekStart);
  const { data = [], isLoading, error, refetch } = useQuery({
    queryKey: ["schedule", weekParam],
    queryFn: () => api<Entry[]>(`/admin/schedule?week_start=${weekParam}`),
  });
  const { data: courses = [] } = useQuery({
    queryKey: ["courses"],
    queryFn: () => api<Course[]>("/admin/courses"),
    enabled: createOpen,
  });
  const { data: rooms = [] } = useQuery({
    queryKey: ["rooms"],
    queryFn: () => api<Room[]>("/admin/rooms"),
    enabled: createOpen,
  });
  const { data: timeslots = [] } = useQuery({
    queryKey: ["timeslots"],
    queryFn: () => api<TimeSlot[]>("/admin/timeslots"),
    enabled: createOpen || slotsOpen,
  });

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const closePreview = () => {
    setPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return null;
    });
    setPreviewName(null);
  };

  const create = useMutation({
    mutationFn: () =>
      api("/admin/schedule", {
        method: "POST",
        body: JSON.stringify({
          course_id: Number(form.course_id),
          room_id: Number(form.room_id),
          timeslot_id: Number(form.timeslot_id),
          entry_date: form.entry_date,
          status: "scheduled",
        }),
      }),
    onSuccess: () => {
      closeCreateModal();
      void qc.invalidateQueries({ queryKey: ["schedule"] });
    },
    onError: (err: unknown) => setLocalError(formatApiError(err)),
  });

  const cancel = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/schedule/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      setSelected(null);
      void qc.invalidateQueries({ queryKey: ["schedule"] });
    },
    onError: (err: unknown) => setEntryActionError(formatApiError(err)),
  });

  const deleteEntry = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/schedule/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setSelected(null);
      setConfirmDeleteEntry(false);
      void qc.invalidateQueries({ queryKey: ["schedule"] });
    },
    onError: (err: unknown) => {
      setConfirmDeleteEntry(false);
      setEntryActionError(formatApiError(err));
    },
  });

  const saveSlot = useMutation({
    mutationFn: () =>
      api(
        editingSlotId ? `/admin/timeslots/${editingSlotId}` : "/admin/timeslots",
        {
          method: editingSlotId ? "PATCH" : "POST",
          body: JSON.stringify(slotForm),
        }
      ),
    onSuccess: () => {
      setSlotForm(slotEmpty);
      setEditingSlotId(null);
      setSlotError(null);
      void qc.invalidateQueries({ queryKey: ["timeslots"] });
    },
    onError: (err: unknown) => setSlotError(formatApiError(err)),
  });

  const removeSlot = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/timeslots/${id}`, { method: "DELETE" }),
    onSuccess: (_data, id) => {
      if (editingSlotId === id) {
        setEditingSlotId(null);
        setSlotForm(slotEmpty);
      }
      setSlotError(null);
      setConfirmDeleteSlot(null);
      void qc.invalidateQueries({ queryKey: ["timeslots"] });
    },
    onError: (err: unknown) => {
      setConfirmDeleteSlot(null);
      setSlotError(formatApiError(err));
    },
  });

  const applyPresets = useMutation({
    mutationFn: () =>
      api<TimeSlot[]>("/admin/timeslots/apply-standard-presets", {
        method: "POST",
        body: JSON.stringify({ days: [0, 1, 2, 3, 4] }),
      }),
    onSuccess: (rows) => {
      setSlotError(null);
      setPresetsMessage(
        `${rows.length} créneau(x) disponible(s) sur Lundi-Vendredi ` +
          `(matin 08h-12h commun, après-midi 13h-17h Bachelor 1-2, ` +
          `soir 18h-22h Bachelor 3/Master 1-2). Les créneaux existants ` +
          `n'ont pas été modifiés.`
      );
      void qc.invalidateQueries({ queryKey: ["timeslots"] });
    },
    onError: (err: unknown) => {
      setPresetsMessage(null);
      setSlotError(formatApiError(err));
    },
  });

  function closeSlotsModal() {
    setSlotsOpen(false);
    setEditingSlotId(null);
    setSlotForm(slotEmpty);
    setSlotError(null);
    setConfirmDeleteSlot(null);
    setPresetsMessage(null);
    saveSlot.reset();
  }

  function onSlotSubmit(e: FormEvent) {
    e.preventDefault();
    setSlotError(null);
    if (!slotForm.label.trim()) {
      setSlotError("Le libellé est obligatoire");
      return;
    }
    if (slotForm.end_time <= slotForm.start_time) {
      setSlotError("L'heure de fin doit être postérieure à l'heure de début");
      return;
    }
    saveSlot.mutate();
  }

  const exportPdf = useMutation({
    mutationFn: () => downloadWeekPdf(weekParam),
    onMutate: () => setPdfError(null),
    onError: (err: Error) =>
      setPdfError(err.message || "Export PDF impossible"),
  });

  const previewPdf = useMutation({
    mutationFn: () => fetchWeekPdf(weekParam, { preview: true }),
    onMutate: () => setPdfError(null),
    onSuccess: ({ blob, filename, mediaType }) => {
      if (!mediaType.includes("pdf")) {
        setPdfError(
          "Aperçu disponible uniquement pour un PDF (un groupe). Utilisez Exporter PDF pour le ZIP."
        );
        return;
      }
      setPreviewUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return URL.createObjectURL(blob);
      });
      setPreviewName(filename);
    },
    onError: (err: Error) =>
      setPdfError(err.message || "Aperçu PDF impossible"),
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

  const slotsForDate = useMemo(() => {
    if (!form.entry_date) return timeslots;
    const dow = dayOfWeekMondayBased(form.entry_date);
    return timeslots.filter((s) => s.day_of_week === dow);
  }, [timeslots, form.entry_date]);

  function closeCreateModal() {
    setCreateOpen(false);
    setForm(entryEmpty);
    setLocalError(null);
    create.reset();
  }

  function openCreate(defaultDate?: string) {
    setForm({
      ...entryEmpty,
      entry_date: defaultDate || weekParam,
    });
    setLocalError(null);
    create.reset();
    setCreateOpen(true);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLocalError(null);
    if (
      !form.course_id ||
      !form.room_id ||
      !form.timeslot_id ||
      !form.entry_date
    ) {
      setLocalError("Renseignez cours, salle, créneau et date");
      return;
    }
    create.mutate();
  }

  const pdfBusy = exportPdf.isPending || previewPdf.isPending;
  const canCreate =
    courses.length > 0 && rooms.length > 0 && timeslots.length > 0;

  return (
    <div>
      <PageHeader
        title="Planning semaine"
        subtitle={`Du ${days[0].toLocaleDateString("fr-FR", { day: "2-digit", month: "long" })} au ${days[4].toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" })}`}
        actions={
          <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto sm:flex-wrap">
            <Button onClick={() => openCreate()}>Ajouter</Button>
            <Button variant="ghost" onClick={() => setSlotsOpen(true)}>
              Créneaux
            </Button>
            <Button
              variant="ghost"
              onClick={() => previewPdf.mutate()}
              disabled={pdfBusy || isLoading}
            >
              {previewPdf.isPending ? "Aperçu…" : "Aperçu PDF"}
            </Button>
            <Button
              onClick={() => exportPdf.mutate()}
              disabled={pdfBusy || isLoading}
            >
              {exportPdf.isPending ? "Export…" : "Exporter PDF"}
            </Button>
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
      {pdfError ? (
        <Card className="mb-4 border-warn/30 p-3 text-sm text-warn">
          {pdfError}
        </Card>
      ) : null}
      {!isLoading && !error ? (
        <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-lg bg-brand-blue-soft px-3 py-1.5 font-semibold text-brand-blue">
            {data.filter((entry) => entry.status === "scheduled").length}{" "}
            séance(s) planifiée(s)
          </span>
          <span className="rounded-lg bg-red-50 px-3 py-1.5 font-semibold text-red-700">
            {data.filter((entry) => entry.status === "cancelled").length}{" "}
            annulée(s)
          </span>
          <span className="text-ink-soft">
            Sélectionnez une séance pour consulter son détail, ou Ajouter pour
            en créer une.
          </span>
        </div>
      ) : null}
      {isLoading ? (
        <p className="text-ink-soft">Chargement…</p>
      ) : error ? (
        <Card className="border-warn/30 p-5">
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
              <Card key={key} className="min-h-40 p-3 xl:min-h-56">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-xs uppercase tracking-wide text-ink-soft">
                    {d.toLocaleDateString("fr-FR", {
                      weekday: "short",
                      day: "2-digit",
                      month: "short",
                    })}
                  </div>
                  <button
                    type="button"
                    className="text-xs font-semibold text-accent hover:underline"
                    onClick={() => openCreate(key)}
                  >
                    +
                  </button>
                </div>
                <div className="space-y-2">
                  {entries.length === 0 ? (
                    <div className="text-xs italic text-ink-soft/70">Libre</div>
                  ) : (
                    entries.map((e) => (
                      <button
                        key={e.id}
                        onClick={() => {
                          setEntryActionError(null);
                          setSelected(e);
                        }}
                        className={`w-full min-h-11 rounded-xl border px-3 py-2.5 text-left text-xs transition hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue ${
                          STATUS_COLOR[e.status] || STATUS_COLOR.scheduled
                        }`}
                      >
                        <div className="break-words font-semibold">
                          {e.course_title || `Cours #${e.course_id}`}
                        </div>
                        <div className="mt-0.5 opacity-80">
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

      <Modal
        open={!!selected}
        onClose={() => {
          setSelected(null);
          setEntryActionError(null);
          setConfirmDeleteEntry(false);
        }}
        title={selected ? `Séance #${selected.id}` : "Séance"}
        titleId="schedule-detail-title"
      >
              {selected ? (
                <>
              <dl className="mb-5 space-y-2 text-sm">
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
              {entryActionError ? (
                <p className="mb-3 text-sm text-warn">{entryActionError}</p>
              ) : null}
              <div className="flex flex-wrap justify-end gap-2">
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSelected(null);
                    setEntryActionError(null);
                    setConfirmDeleteEntry(false);
                  }}
                >
                  Fermer
                </Button>
                {selected.status === "scheduled" ? (
                  <Button
                    variant="danger"
                    onClick={() => {
                      setEntryActionError(null);
                      if (
                        window.confirm(
                          `Annuler la séance « ${selected.course_title} » ?`
                        )
                      ) {
                        cancel.mutate(selected.id);
                      }
                    }}
                  >
                    Annuler la séance
                  </Button>
                ) : null}
                <Button
                  variant="danger"
                  onClick={() => {
                    setEntryActionError(null);
                    setConfirmDeleteEntry(true);
                  }}
                >
                  Supprimer
                </Button>
              </div>
                </>
              ) : null}
      </Modal>

      <ConfirmDialog
        open={confirmDeleteEntry}
        title="Supprimer la séance"
        message={`Supprimer définitivement la séance « ${selected?.course_title} » ? Cette action est irréversible (contrairement à l'annulation, la séance ne sera plus conservée dans l'historique).`}
        confirmLabel="Supprimer"
        pending={deleteEntry.isPending}
        onCancel={() => setConfirmDeleteEntry(false)}
        onConfirm={() => {
          if (selected) deleteEntry.mutate(selected.id);
        }}
      />

      <Modal
        open={createOpen}
        onClose={closeCreateModal}
        title="Nouvelle séance"
        titleId="schedule-create-title"
      >
              {!canCreate ? (
                <p className="mb-3 text-sm text-warn">
                  Vérifiez qu&apos;il existe des cours, salles et créneaux.
                </p>
              ) : null}
              <form className="space-y-3" onSubmit={onSubmit}>
                <Select
                  label="Cours"
                  value={form.course_id}
                  onChange={(e) =>
                    setForm({ ...form, course_id: e.target.value })
                  }
                  required
                  autoFocus
                >
                  <option value="">Choisir…</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                      {c.group_name ? ` — ${c.group_name}` : ""}
                    </option>
                  ))}
                </Select>
                <Input
                  label="Date"
                  type="date"
                  value={form.entry_date}
                  min={weekParam}
                  max={fmt(days[4])}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      entry_date: e.target.value,
                      timeslot_id: "",
                    })
                  }
                  required
                />
                <Select
                  label="Créneau"
                  value={form.timeslot_id}
                  onChange={(e) =>
                    setForm({ ...form, timeslot_id: e.target.value })
                  }
                  required
                >
                  <option value="">Choisir…</option>
                  {slotsForDate.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label} ({s.start_time}–{s.end_time})
                    </option>
                  ))}
                </Select>
                <Select
                  label="Salle"
                  value={form.room_id}
                  onChange={(e) =>
                    setForm({ ...form, room_id: e.target.value })
                  }
                  required
                >
                  <option value="">Choisir…</option>
                  {rooms.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} ({r.capacity} places)
                    </option>
                  ))}
                </Select>
                {localError ? (
                  <p className="text-sm text-warn">{localError}</p>
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
                    disabled={create.isPending || !canCreate}
                  >
                    {create.isPending ? "Ajout…" : "Ajouter"}
                  </Button>
                </div>
              </form>
      </Modal>

      <Modal
        open={slotsOpen}
        onClose={closeSlotsModal}
        title="Créneaux horaires"
        titleId="timeslots-title"
        wide
      >
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-mist/60 p-3">
          <p className="text-sm text-ink-soft">
            Plages standard de l'établissement : matin 08h-12h (commun),
            après-midi 13h-17h (Bachelor 1-2), soir 18h-22h (Bachelor 3,
            Master 1-2) — Lundi à Vendredi.
          </p>
          <Button
            type="button"
            variant="ghost"
            disabled={applyPresets.isPending}
            onClick={() => {
              setSlotError(null);
              applyPresets.mutate();
            }}
          >
            {applyPresets.isPending
              ? "Génération…"
              : "Générer les plages standard"}
          </Button>
        </div>
        {presetsMessage ? (
          <p className="mb-4 rounded-lg bg-accent/10 p-2 text-sm text-accent">
            {presetsMessage}
          </p>
        ) : null}
        <div className="grid gap-5 sm:grid-cols-[260px_1fr]">
          <form className="space-y-3" onSubmit={onSlotSubmit}>
            <h4 className="text-sm font-semibold">
              {editingSlotId ? "Modifier le créneau" : "Nouveau créneau"}
            </h4>
            <Select
              label="Jour"
              value={slotForm.day_of_week}
              onChange={(e) =>
                setSlotForm({ ...slotForm, day_of_week: Number(e.target.value) })
              }
            >
              {DAY_LABELS.map((label, idx) => (
                <option key={idx} value={idx}>
                  {label}
                </option>
              ))}
            </Select>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Début"
                type="time"
                value={slotForm.start_time}
                onChange={(e) =>
                  setSlotForm({ ...slotForm, start_time: e.target.value })
                }
                required
              />
              <Input
                label="Fin"
                type="time"
                value={slotForm.end_time}
                onChange={(e) =>
                  setSlotForm({ ...slotForm, end_time: e.target.value })
                }
                required
              />
            </div>
            <Input
              label="Libellé"
              placeholder="Mardi 08h-10h"
              value={slotForm.label}
              onChange={(e) => setSlotForm({ ...slotForm, label: e.target.value })}
              required
            />
            {slotError ? (
              <p className="text-sm text-warn">{slotError}</p>
            ) : null}
            <div className="flex gap-2">
              <Button
                className="flex-1"
                type="submit"
                disabled={saveSlot.isPending}
              >
                {saveSlot.isPending
                  ? "Enregistrement…"
                  : editingSlotId
                    ? "Enregistrer"
                    : "Ajouter"}
              </Button>
              {editingSlotId ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setEditingSlotId(null);
                    setSlotForm(slotEmpty);
                    setSlotError(null);
                  }}
                >
                  Annuler
                </Button>
              ) : null}
            </div>
          </form>
          <div className="max-h-96 overflow-y-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead className="bg-mist text-left">
                <tr>
                  <th className="px-3 py-2">Jour</th>
                  <th className="px-3 py-2">Horaire</th>
                  <th className="px-3 py-2">Libellé</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {timeslots.length === 0 ? (
                  <tr>
                    <td className="px-3 py-3 text-ink-soft" colSpan={4}>
                      Aucun créneau.
                    </td>
                  </tr>
                ) : (
                  timeslots
                    .slice()
                    .sort(
                      (a, b) =>
                        a.day_of_week - b.day_of_week ||
                        a.start_time.localeCompare(b.start_time)
                    )
                    .map((s) => (
                      <tr key={s.id} className="border-t border-line">
                        <td className="px-3 py-2">
                          {DAY_LABELS[s.day_of_week] ?? s.day_of_week}
                        </td>
                        <td className="px-3 py-2">
                          {s.start_time}–{s.end_time}
                        </td>
                        <td className="px-3 py-2">{s.label}</td>
                        <td className="px-3 py-2 text-right">
                          <div className="flex justify-end gap-1.5">
                            <Button
                              variant="ghost"
                              onClick={() => {
                                setEditingSlotId(s.id);
                                setSlotForm({
                                  day_of_week: s.day_of_week,
                                  start_time: s.start_time,
                                  end_time: s.end_time,
                                  label: s.label,
                                });
                                setSlotError(null);
                              }}
                            >
                              Modifier
                            </Button>
                            <Button
                              variant="ghost"
                              onClick={() => {
                                setSlotError(null);
                                setConfirmDeleteSlot(s);
                              }}
                            >
                              Supprimer
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDeleteSlot !== null}
        title="Supprimer le créneau"
        message={`Supprimer le créneau « ${confirmDeleteSlot?.label} » ? Cette action est bloquée si des séances utilisent encore ce créneau.`}
        confirmLabel="Supprimer"
        pending={removeSlot.isPending}
        onCancel={() => setConfirmDeleteSlot(null)}
        onConfirm={() => {
          if (confirmDeleteSlot) removeSlot.mutate(confirmDeleteSlot.id);
        }}
      />

      {previewUrl ? (
        <div
          className="fixed inset-0 z-50 bg-ink/60 p-3 sm:p-6"
          role="presentation"
          onMouseDown={closePreview}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="pdf-preview-title"
            className="mx-auto flex h-full max-w-6xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 border-b border-line/60 px-4 py-3">
              <h3
                id="pdf-preview-title"
                className="truncate text-sm font-semibold sm:text-base"
              >
                Aperçu — {previewName || "planning.pdf"}
              </h3>
              <div className="flex shrink-0 gap-2">
                <Button
                  variant="ghost"
                  onClick={() => {
                    if (!previewUrl) return;
                    const anchor = document.createElement("a");
                    anchor.href = previewUrl;
                    anchor.download = previewName || "planning.pdf";
                    anchor.click();
                  }}
                >
                  Télécharger
                </Button>
                <Button variant="ghost" onClick={closePreview}>
                  Fermer
                </Button>
              </div>
            </div>
            <iframe
              title="Aperçu PDF planning"
              src={previewUrl}
              className="min-h-0 w-full flex-1 bg-mist"
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

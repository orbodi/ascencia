import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getToken } from "../lib/api";
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

type PdfFetchResult = {
  blob: Blob;
  filename: string;
  mediaType: string;
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
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewName, setPreviewName] = useState<string | null>(null);

  const weekParam = fmt(weekStart);
  const { data = [], isLoading, error, refetch } = useQuery({
    queryKey: ["schedule", weekParam],
    queryFn: () =>
      api<Entry[]>(`/admin/schedule?week_start=${weekParam}`),
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

  const cancel = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/schedule/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      setSelected(null);
      void qc.invalidateQueries({ queryKey: ["schedule"] });
    },
  });

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

  const pdfBusy = exportPdf.isPending || previewPdf.isPending;

  return (
    <div>
      <PageHeader
        title="Planning semaine"
        subtitle={`Du ${days[0].toLocaleDateString("fr-FR", { day: "2-digit", month: "long" })} au ${days[4].toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" })}`}
        actions={
          <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto sm:flex-wrap">
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
            Sélectionnez une séance pour consulter son détail.
          </span>
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
              <h3
                id="schedule-detail-title"
                className="text-xl font-[family-name:var(--font-display)] mb-3"
              >
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

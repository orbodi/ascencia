import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, PageHeader } from "../components/ui";

type Change = {
  id: number;
  entry_id: number;
  before_json: Record<string, unknown>;
  after_json: Record<string, unknown>;
  status: string;
  proposed_by: string;
  created_at?: string | null;
};

const STATUS_LABEL: Record<string, string> = {
  proposed: "En attente",
  approved: "Approuvée",
  rejected: "Rejetée",
  applied: "Appliquée",
};

function str(v: unknown, fallback = "?"): string {
  if (v === null || v === undefined || v === "") return fallback;
  return String(v);
}

function fmtDate(iso: unknown): string {
  const s = str(iso, "");
  if (!s) return "?";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("fr-FR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

/** Résumé lisible d'une proposition de report / changement. */
function summarizeChange(c: Change): string {
  const before = c.before_json || {};
  const after = c.after_json || {};

  const course = str(before.course_title || after.course_title, "cours");
  const teacher = str(before.teacher_name || after.teacher_name, "enseignant");
  const group = str(before.group_name || after.group_name, "groupe");

  const beforeDate = fmtDate(before.entry_date);
  const afterDate = fmtDate(after.entry_date);
  const beforeSlot = str(before.timeslot_label, "créneau ?");
  const afterSlot = str(after.timeslot_label, beforeSlot);
  const beforeRoom = str(before.room_name, "salle ?");
  const afterRoomId = after.room_id;
  const beforeRoomId = before.room_id;
  const afterRoom =
    after.room_name != null
      ? str(after.room_name)
      : afterRoomId !== beforeRoomId
        ? `salle #${afterRoomId}`
        : beforeRoom;

  const dateChanged = str(before.entry_date) !== str(after.entry_date);
  const slotChanged =
    before.timeslot_id !== after.timeslot_id ||
    str(before.timeslot_label) !== str(after.timeslot_label);
  const roomChanged =
    before.room_id !== after.room_id ||
    (after.room_name != null && str(before.room_name) !== str(after.room_name));

  const who = c.proposed_by === "agent" ? "Ascencia" : c.proposed_by;

  if (!dateChanged && !slotChanged && !roomChanged) {
    return `${who} a signalé une mise à jour pour « ${course} » (${teacher}, ${group}) — séance #${c.entry_id}.`;
  }

  const parts: string[] = [
    `${who} propose de reporter « ${course} » (${teacher} · ${group}).`,
    `Actuellement : ${beforeDate}, ${beforeSlot}, ${beforeRoom}.`,
  ];

  const news: string[] = [];
  if (dateChanged) news.push(afterDate);
  else news.push(beforeDate);
  if (slotChanged) news.push(afterSlot);
  else news.push(beforeSlot);
  if (roomChanged) news.push(afterRoom);
  else news.push(beforeRoom);

  parts.push(`Nouveau créneau proposé : ${news.join(", ")}.`);
  return parts.join(" ");
}

export function ChangesPage() {
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery({
    queryKey: ["changes"],
    queryFn: () => api<Change[]>("/admin/changes"),
  });

  const approve = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/changes/${id}/approve`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["changes"] }),
  });
  const applyChange = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/changes/${id}/apply`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["changes"] });
      void qc.invalidateQueries({ queryKey: ["schedule"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const reject = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/changes/${id}/reject`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["changes"] }),
  });

  return (
    <div>
      <PageHeader
        title="Validations"
        subtitle="Circuit supervisé : proposition, approbation humaine, puis application au planning"
      />
      <Card className="mb-5 overflow-hidden border-brand-blue/20 bg-brand-blue-soft/40 p-4">
        <ol className="grid gap-3 text-sm sm:grid-cols-3">
          {["1. Proposition contrôlée", "2. Approbation humaine", "3. Application au planning"].map((step) => (
            <li key={step} className="rounded-xl bg-white/80 px-3 py-2 font-semibold text-ink">{step}</li>
          ))}
        </ol>
      </Card>
      {approve.error || applyChange.error || reject.error ? (
        <Card className="mb-4 border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {String((approve.error || applyChange.error || reject.error) instanceof Error
            ? (approve.error || applyChange.error || reject.error as Error).message
            : "L’opération n’a pas abouti.")}
        </Card>
      ) : null}
      <div className="space-y-3">
        {isLoading ? (
          <Card className="p-5 text-ink-soft text-sm">Chargement…</Card>
        ) : data.length === 0 ? (
          <Card className="p-5 text-ink-soft text-sm">
            Aucune notification pour le moment.
          </Card>
        ) : (
          data.map((c) => (
            <Card key={c.id} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-accent bg-accent-soft px-2 py-0.5 rounded-lg">
                      #{c.id}
                    </span>
                    <span className="text-xs text-ink-soft">
                      Séance #{c.entry_id}
                    </span>
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-lg ${
                        c.status === "proposed"
                          ? "bg-amber-50 text-amber-800"
                          : c.status === "rejected"
                            ? "bg-red-50 text-red-700"
                            : "bg-accent-soft text-accent"
                      }`}
                    >
                      {STATUS_LABEL[c.status] || c.status}
                    </span>
                    {c.created_at ? (
                      <span className="text-xs text-ink-soft">
                        {new Date(c.created_at).toLocaleString("fr-FR")}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-sm text-ink leading-relaxed">
                    {summarizeChange(c)}
                  </p>
                </div>
                {c.status === "proposed" ? (
                  <div className="flex gap-2 shrink-0">
                    <Button onClick={() => approve.mutate(c.id)}>
                      Approuver
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => reject.mutate(c.id)}
                    >
                      Rejeter
                    </Button>
                  </div>
                ) : null}
                {c.status === "approved" ? (
                  <div className="shrink-0">
                    <Button
                      disabled={applyChange.isPending}
                      onClick={() => {
                        if (confirm("Appliquer ce changement au planning officiel ?")) {
                          applyChange.mutate(c.id);
                        }
                      }}
                    >
                      Appliquer au planning
                    </Button>
                  </div>
                ) : null}
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}

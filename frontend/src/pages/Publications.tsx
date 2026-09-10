import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getToken } from "../lib/api";
import { Button, Card, PageHeader } from "../components/ui";

type Entry = { course_title: string; teacher_name: string; group_name: string; room_name: string; timeslot_label: string; entry_date: string };
type Publication = {
  id: number; version_number: string; week_start: string; week_end: string;
  status: "draft" | "published" | "archived"; snapshot_json: Entry[];
  generation_report: { engine: string; generated_count: number; unscheduled_count: number; skipped_complete_count: number; skipped_existing_count: number; notice: string };
  created_by: string; published_by?: string | null; xlsx_path?: string | null;
};
type Campaign = {
  id: number; status: "open" | "ready" | "requires_revision" | "completed";
  deadline_at: string; counts: { pending: number; confirmed: number; unavailable: number };
  requests: Array<{ id: number; teacher_name: string; status: string; sent_channels: string[]; response_text?: string | null }>;
};
type Distribution = { sent_count: number; failed_count: number; skipped_count: number };

function nextMondayIso(): string {
  const value = new Date();
  const day = (value.getDay() + 6) % 7;
  value.setDate(value.getDate() - day + 7);
  return value.toISOString().slice(0, 10);
}

const STATUS_LABEL = { draft: "Brouillon à contrôler", published: "Version publiée", archived: "Version archivée" };

async function downloadExcel(item: Publication) {
  const response = await fetch(`/admin/publications/${item.id}/xlsx`, { headers: { Authorization: `Bearer ${getToken() || ""}` } });
  if (!response.ok) throw new Error("Le fichier Excel n’est pas disponible.");
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `planning_${item.version_number}.xlsx`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function PublicationWorkflow({ item, onChanged }: { item: Publication; onChanged: () => void }) {
  const qc = useQueryClient();
  const [result, setResult] = useState<Distribution | null>(null);
  const campaignQuery = useQuery({
    queryKey: ["presence-campaign", item.id],
    queryFn: () => api<{ campaign: Campaign | null }>(`/admin/presence-campaigns?publication_id=${item.id}`),
    enabled: item.status === "draft",
  });
  const deliveries = useQuery({
    queryKey: ["deliveries", item.id],
    queryFn: () => api<{ deliveries: Array<{ id: number; status: string }> }>(`/admin/publications/${item.id}/deliveries`),
    enabled: item.status === "published",
  });
  const createCampaign = useMutation({
    mutationFn: () => api("/admin/presence-campaigns", { method: "POST", body: JSON.stringify({ publication_id: item.id, channels: ["email", "whatsapp"] }) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["presence-campaign", item.id] }),
  });
  const sendCampaign = useMutation({
    mutationFn: (id: number) => api(`/admin/presence-campaigns/${id}/send`, { method: "POST" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["presence-campaign", item.id] }),
  });
  const publish = useMutation({
    mutationFn: () => api<{ publication: Publication; distribution: Distribution }>(`/admin/publications/${item.id}/publish`, { method: "POST", body: JSON.stringify({ force_presence_override: false }) }),
    onSuccess: (data) => { setResult(data.distribution); onChanged(); },
  });
  const redistribute = useMutation({
    mutationFn: () => api<Distribution>(`/admin/publications/${item.id}/redistribute`, { method: "POST" }),
    onSuccess: (data) => { setResult(data); void deliveries.refetch(); },
  });
  const campaign = campaignQuery.data?.campaign;
  const error = createCampaign.error || sendCampaign.error || publish.error || redistribute.error;

  return <div className="mb-4 rounded-xl border border-line bg-white p-4">
    {item.status === "draft" ? <>
      <h3 className="font-bold text-ink">Collecte et validation des disponibilités</h3>
      {!campaign ? <div className="mt-3 flex flex-wrap items-center gap-3"><p className="text-sm text-ink-soft">Créez les demandes avant toute publication.</p><Button onClick={() => createCampaign.mutate()} disabled={createCampaign.isPending}>Créer la campagne</Button></div> : <>
        <div className="mt-3 flex flex-wrap gap-2 text-xs"><span className="rounded-lg bg-paper px-2.5 py-1">En attente : {campaign.counts.pending}</span><span className="rounded-lg bg-emerald-50 px-2.5 py-1 text-emerald-800">Confirmés : {campaign.counts.confirmed}</span><span className="rounded-lg bg-red-50 px-2.5 py-1 text-red-700">Indisponibles : {campaign.counts.unavailable}</span></div>
        <div className="mt-3 grid gap-2 md:grid-cols-2">{campaign.requests.map((request) => <div key={request.id} className="rounded-lg bg-paper px-3 py-2 text-xs"><b>{request.teacher_name}</b> · {request.status}<br /><span className="text-ink-soft">{request.sent_channels.join(" + ") || "pas encore envoyé"}{request.response_text ? ` · ${request.response_text}` : ""}</span></div>)}</div>
        <div className="mt-4 flex flex-wrap gap-2"><Button variant="ghost" onClick={() => sendCampaign.mutate(campaign.id)} disabled={sendCampaign.isPending}>{campaign.requests.some((request) => request.sent_channels.length) ? "Relancer" : "Envoyer les demandes"}</Button><Button disabled={publish.isPending || campaign.status !== "ready"} onClick={() => { if (confirm(`Publier ${item.version_number}, créer les PDF et les diffuser ?`)) publish.mutate(); }}>Publier et diffuser</Button></div>
        {campaign.status === "requires_revision" ? <p className="mt-3 text-xs font-semibold text-red-700">Les disponibilités reçues ont créé de nouvelles contraintes. Générez une nouvelle version : le moteur les appliquera automatiquement.</p> : null}
        {campaign.status === "open" ? <p className="mt-3 text-xs text-ink-soft">La publication sera autorisée lorsque tous les enseignants auront confirmé.</p> : null}
      </>}
    </> : <div className="flex flex-wrap items-center gap-2"><Button onClick={() => void downloadExcel(item)}>Télécharger l’Excel</Button><Button variant="ghost" onClick={() => redistribute.mutate()} disabled={redistribute.isPending}>Relancer la diffusion PDF</Button><span className="text-xs text-ink-soft">{deliveries.data?.deliveries.length || 0} tentative(s) enregistrée(s)</span></div>}
    {result ? <p className="mt-3 rounded-lg bg-brand-blue-soft p-2 text-xs text-brand-blue">Diffusion : {result.sent_count} envoyée(s), {result.failed_count} échec(s), {result.skipped_count} ignorée(s).</p> : null}
    {error ? <p className="mt-3 text-sm text-red-700">{error instanceof Error ? error.message : "L’opération n’a pas abouti."}</p> : null}
  </div>;
}

export function PublicationsPage() {
  const qc = useQueryClient();
  const [weekStart, setWeekStart] = useState(nextMondayIso);
  const [expanded, setExpanded] = useState<number | null>(null);
  const { data = [], isLoading } = useQuery({ queryKey: ["publications"], queryFn: () => api<Publication[]>("/admin/publications") });
  const generate = useMutation({ mutationFn: () => api<Publication>("/admin/publications/generate", { method: "POST", body: JSON.stringify({ week_start: weekStart }) }), onSuccess: (item) => { setExpanded(item.id); void qc.invalidateQueries({ queryKey: ["publications"] }); } });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["publications"] }); void qc.invalidateQueries({ queryKey: ["schedule"] }); void qc.invalidateQueries({ queryKey: ["dashboard"] }); };

  return <div>
    <PageHeader title="Génération & publication" subtitle="Brouillon sous contraintes, confirmation des enseignants, validation puis diffusion traçable" />
    <Card className="mb-6 p-5 sm:p-6"><div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end"><label className="text-sm font-semibold text-ink">Semaine à générer<input type="date" value={weekStart} onChange={(event) => setWeekStart(event.target.value)} className="mt-2 block min-h-11 w-full rounded-xl border border-line bg-white px-3 py-2 outline-none focus:border-accent focus:ring-2 focus:ring-accent/15" /></label><Button disabled={generate.isPending || !weekStart} onClick={() => generate.mutate()}>{generate.isPending ? "Calcul en cours…" : "Générer un brouillon"}</Button></div><p className="mt-4 rounded-xl bg-brand-blue-soft/60 p-3 text-xs leading-relaxed text-brand-blue">Le moteur contrôle les conflits, capacités et disponibilités. La diffusion reste bloquée tant que les confirmations ne sont pas traitées.</p></Card>
    {generate.error ? <Card className="mb-4 border-red-200 bg-red-50 p-4 text-sm text-red-700">{generate.error.message}</Card> : null}
    <div className="space-y-4">{isLoading ? <Card className="p-5 text-sm text-ink-soft">Chargement des versions…</Card> : data.length === 0 ? <Card className="p-6 text-center text-sm text-ink-soft">Aucune version générée.</Card> : data.map((item) => {
      const report = item.generation_report; const isOpen = expanded === item.id;
      return <Card key={item.id} className="overflow-hidden"><div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-bold text-ink">{item.version_number}</h2><span className={`rounded-lg px-2 py-1 text-[11px] font-bold ${item.status === "published" ? "bg-emerald-100 text-emerald-800" : "bg-amber-50 text-amber-800"}`}>{STATUS_LABEL[item.status]}</span></div><p className="mt-1 text-sm text-ink-soft">Semaine du {new Date(item.week_start).toLocaleDateString("fr-FR")} · créée par {item.created_by}</p><div className="mt-3 flex flex-wrap gap-2 text-xs"><span className="rounded-lg bg-brand-blue-soft px-2.5 py-1 font-semibold text-brand-blue">{report.generated_count} séance(s) proposée(s)</span><span className="rounded-lg bg-red-50 px-2.5 py-1 font-semibold text-red-700">{report.unscheduled_count} non placée(s)</span><span className="rounded-lg bg-paper px-2.5 py-1 text-ink-soft">Moteur : {report.engine}</span></div></div><Button variant="ghost" onClick={() => setExpanded(isOpen ? null : item.id)}>{isOpen ? "Masquer" : "Contrôler"}</Button></div>
        {isOpen ? <div className="border-t border-line bg-paper/60 p-4 sm:p-5"><PublicationWorkflow item={item} onChanged={refresh} /><div className="grid gap-3 md:grid-cols-2">{item.snapshot_json.map((entry, index) => <div key={`${entry.entry_date}-${entry.course_title}-${index}`} className="rounded-xl border border-line bg-white p-3 text-sm"><div className="font-bold text-ink">{entry.course_title}</div><div className="mt-1 text-xs leading-relaxed text-ink-soft">{new Date(entry.entry_date).toLocaleDateString("fr-FR", { weekday: "long", day: "2-digit", month: "long" })} · {entry.timeslot_label}<br />{entry.group_name} · {entry.teacher_name} · {entry.room_name}</div></div>)}</div></div> : null}
      </Card>;
    })}</div>
  </div>;
}

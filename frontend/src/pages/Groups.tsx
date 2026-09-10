import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, Input, PageHeader, Select } from "../components/ui";

type Group = {
  id: number;
  name: string;
  whatsapp_group_id: string | null;
  student_count: number;
  academic_level_id: number | null;
  distribution_recipients: string[];
};

type Level = { id: number; code: string; label: string };

const empty = {
  name: "",
  whatsapp_group_id: "",
  student_count: 0,
  academic_level_id: "",
  distribution_recipients: "",
};

export function GroupsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(empty);
  const [editingId, setEditingId] = useState<number | null>(null);
  const { data = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => api<Group[]>("/admin/groups"),
  });
  const { data: levels = [] } = useQuery({
    queryKey: ["levels"],
    queryFn: () => api<Level[]>("/admin/levels"),
  });

  const save = useMutation({
    mutationFn: () =>
      api(editingId ? `/admin/groups/${editingId}` : "/admin/groups", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify({
          name: form.name,
          whatsapp_group_id: form.whatsapp_group_id || null,
          student_count: Number(form.student_count),
          academic_level_id: form.academic_level_id
            ? Number(form.academic_level_id)
            : null,
          distribution_recipients: form.distribution_recipients
            .split(/[\n,;]+/)
            .map((value) => value.trim())
            .filter(Boolean),
        }),
      }),
    onSuccess: () => {
      setForm(empty);
      setEditingId(null);
      void qc.invalidateQueries({ queryKey: ["groups"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/groups/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["groups"] }),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  const levelMap = Object.fromEntries(levels.map((l) => [l.id, l.label]));

  return (
    <div>
      <PageHeader title="Groupes" subtitle="Promotions et effectifs" />
      <div className="grid lg:grid-cols-[340px_1fr] gap-6">
        <Card className="p-5 h-fit">
          <h2 className="font-semibold mb-4">{editingId ? "Modifier le groupe" : "Nouveau groupe"}</h2>
          <form className="space-y-3" onSubmit={onSubmit}>
            <Input
              label="Nom"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
            <Select
              label="Parcours"
              value={form.academic_level_id}
              onChange={(e) =>
                setForm({ ...form, academic_level_id: e.target.value })
              }
            >
              <option value="">—</option>
              {levels.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.label}
                </option>
              ))}
            </Select>
            <Input
              label="Effectif"
              type="number"
              value={form.student_count}
              onChange={(e) =>
                setForm({ ...form, student_count: Number(e.target.value) })
              }
            />
            <Input
              label="Identifiant de groupe (facultatif)"
              value={form.whatsapp_group_id}
              onChange={(e) =>
                setForm({ ...form, whatsapp_group_id: e.target.value })
              }
            />
            <label className="block text-sm font-semibold text-ink">
              Destinataires WhatsApp
              <textarea
                className="mt-2 block min-h-24 w-full rounded-xl border border-line bg-white px-3 py-2 font-normal outline-none focus:border-accent focus:ring-2 focus:ring-accent/15"
                placeholder="+22890000000, +22891000000"
                value={form.distribution_recipients}
                onChange={(e) => setForm({ ...form, distribution_recipients: e.target.value })}
              />
              <span className="mt-1 block text-xs font-normal text-ink-soft">Numéros séparés par une virgule ou une ligne.</span>
            </label>
            <Button className="w-full" disabled={save.isPending}>{editingId ? "Enregistrer" : "Ajouter"}</Button>
            {editingId ? <Button type="button" variant="ghost" className="w-full" onClick={() => { setEditingId(null); setForm(empty); }}>Annuler</Button> : null}
          </form>
        </Card>
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-mist text-left">
              <tr>
                <th className="px-4 py-3">Nom</th>
                <th className="px-4 py-3">Parcours</th>
                <th className="px-4 py-3">Effectif</th>
                <th className="px-4 py-3">Diffusion</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((g) => (
                <tr key={g.id} className="border-t border-line">
                  <td className="px-4 py-3 font-medium">{g.name}</td>
                  <td className="px-4 py-3">
                    {g.academic_level_id
                      ? levelMap[g.academic_level_id] || g.academic_level_id
                      : "—"}
                  </td>
                  <td className="px-4 py-3">{g.student_count}</td>
                  <td className="px-4 py-3">{g.distribution_recipients.length} numéro(s)</td>
                  <td className="px-4 py-3 text-right">
                    <Button variant="ghost" onClick={() => {
                      setEditingId(g.id);
                      setForm({
                        name: g.name,
                        whatsapp_group_id: g.whatsapp_group_id || "",
                        student_count: g.student_count,
                        academic_level_id: g.academic_level_id ? String(g.academic_level_id) : "",
                        distribution_recipients: g.distribution_recipients.join(", "),
                      });
                    }}>
                      Modifier
                    </Button>
                    <Button variant="ghost" onClick={() => remove.mutate(g.id)}>
                      Supprimer
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

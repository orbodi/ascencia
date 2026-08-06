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
};

type Level = { id: number; code: string; label: string };

const empty = {
  name: "",
  whatsapp_group_id: "",
  student_count: 0,
  academic_level_id: "",
};

export function GroupsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(empty);
  const { data = [] } = useQuery({
    queryKey: ["groups"],
    queryFn: () => api<Group[]>("/admin/groups"),
  });
  const { data: levels = [] } = useQuery({
    queryKey: ["levels"],
    queryFn: () => api<Level[]>("/admin/levels"),
  });

  const create = useMutation({
    mutationFn: () =>
      api("/admin/groups", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          whatsapp_group_id: form.whatsapp_group_id || null,
          student_count: Number(form.student_count),
          academic_level_id: form.academic_level_id
            ? Number(form.academic_level_id)
            : null,
        }),
      }),
    onSuccess: () => {
      setForm(empty);
      void qc.invalidateQueries({ queryKey: ["groups"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/groups/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["groups"] }),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  const levelMap = Object.fromEntries(levels.map((l) => [l.id, l.label]));

  return (
    <div>
      <PageHeader title="Groupes" subtitle="Promotions et effectifs" />
      <div className="grid lg:grid-cols-[340px_1fr] gap-6">
        <Card className="p-5 h-fit">
          <h2 className="font-semibold mb-4">Nouveau groupe</h2>
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
              label="WhatsApp group id"
              value={form.whatsapp_group_id}
              onChange={(e) =>
                setForm({ ...form, whatsapp_group_id: e.target.value })
              }
            />
            <Button className="w-full">Ajouter</Button>
          </form>
        </Card>
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-mist text-left">
              <tr>
                <th className="px-4 py-3">Nom</th>
                <th className="px-4 py-3">Parcours</th>
                <th className="px-4 py-3">Effectif</th>
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
                  <td className="px-4 py-3 text-right">
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

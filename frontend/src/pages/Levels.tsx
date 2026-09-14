import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, Input, PageHeader, Select } from "../components/ui";

type Level = {
  id: number;
  code: string;
  label: string;
  degree: string;
  year: number;
  speciality: string | null;
};

const empty = {
  code: "",
  label: "",
  degree: "L",
  year: 1,
  speciality: "",
};

export function LevelsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(empty);
  const [editingId, setEditingId] = useState<number | null>(null);
  const { data = [], isLoading } = useQuery({
    queryKey: ["levels"],
    queryFn: () => api<Level[]>("/admin/levels"),
  });

  const save = useMutation({
    mutationFn: () =>
      api(editingId ? `/admin/levels/${editingId}` : "/admin/levels", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify({
          ...form,
          speciality: form.speciality || null,
          year: Number(form.year),
        }),
      }),
    onSuccess: () => {
      setForm(empty);
      setEditingId(null);
      void qc.invalidateQueries({ queryKey: ["levels"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/levels/${id}`, { method: "DELETE" }),
    onSuccess: (_data, id) => {
      if (editingId === id) {
        setEditingId(null);
        setForm(empty);
      }
      void qc.invalidateQueries({ queryKey: ["levels"] });
    },
  });

  function resetForm() {
    setEditingId(null);
    setForm(empty);
    save.reset();
  }

  function startEdit(l: Level) {
    setEditingId(l.id);
    setForm({
      code: l.code,
      label: l.label,
      degree: l.degree,
      year: l.year,
      speciality: l.speciality || "",
    });
    save.reset();
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  return (
    <div>
      <PageHeader
        title="Niveaux / Parcours"
        subtitle="L1–L3, M1–M2 et spécialités"
      />
      <div className="grid lg:grid-cols-[340px_1fr] gap-6">
        <Card className="p-5 h-fit">
          <h2 className="font-semibold mb-4">
            {editingId ? "Modifier le parcours" : "Nouveau parcours"}
          </h2>
          <form className="space-y-3" onSubmit={onSubmit}>
            <Input
              label="Code"
              placeholder="L3-INFO"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              required
            />
            <Input
              label="Libellé"
              placeholder="L3 Informatique"
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
              required
            />
            <Select
              label="Degré"
              value={form.degree}
              onChange={(e) => setForm({ ...form, degree: e.target.value })}
            >
              <option value="L">Licence</option>
              <option value="M">Master</option>
              <option value="D">Doctorat</option>
            </Select>
            <Input
              label="Année"
              type="number"
              min={1}
              max={3}
              value={form.year}
              onChange={(e) =>
                setForm({ ...form, year: Number(e.target.value) })
              }
            />
            <Input
              label="Spécialité"
              value={form.speciality}
              onChange={(e) =>
                setForm({ ...form, speciality: e.target.value })
              }
            />
            {save.isError ? (
              <p className="text-sm text-warn">
                {(save.error as Error)?.message || "Enregistrement impossible"}
              </p>
            ) : null}
            <Button className="w-full" disabled={save.isPending}>
              {save.isPending
                ? "Enregistrement…"
                : editingId
                  ? "Enregistrer"
                  : "Ajouter"}
            </Button>
            {editingId ? (
              <Button
                type="button"
                variant="ghost"
                className="w-full"
                onClick={resetForm}
              >
                Annuler
              </Button>
            ) : null}
          </form>
        </Card>
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-mist text-left">
              <tr>
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Libellé</th>
                <th className="px-4 py-3">Degré</th>
                <th className="px-4 py-3">Année</th>
                <th className="px-4 py-3">Spécialité</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td className="px-4 py-4 text-ink-soft" colSpan={6}>
                    Chargement…
                  </td>
                </tr>
              ) : data.length === 0 ? (
                <tr>
                  <td className="px-4 py-4 text-ink-soft" colSpan={6}>
                    Aucun parcours
                  </td>
                </tr>
              ) : (
                data.map((l) => (
                  <tr key={l.id} className="border-t border-line">
                    <td className="px-4 py-3 font-medium">{l.code}</td>
                    <td className="px-4 py-3">{l.label}</td>
                    <td className="px-4 py-3">{l.degree}</td>
                    <td className="px-4 py-3">{l.year}</td>
                    <td className="px-4 py-3">{l.speciality || "—"}</td>
                    <td className="px-4 py-3 text-right">
                      <Button variant="ghost" onClick={() => startEdit(l)}>
                        Modifier
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => remove.mutate(l.id)}
                      >
                        Supprimer
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

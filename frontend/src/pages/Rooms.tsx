import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, Input, PageHeader } from "../components/ui";

type Room = { id: number; name: string; capacity: number };

const empty = { name: "", capacity: 30 };

export function RoomsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(empty);
  const [editingId, setEditingId] = useState<number | null>(null);
  const { data = [] } = useQuery({
    queryKey: ["rooms"],
    queryFn: () => api<Room[]>("/admin/rooms"),
  });

  const save = useMutation({
    mutationFn: () =>
      api(editingId ? `/admin/rooms/${editingId}` : "/admin/rooms", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify({
          name: form.name,
          capacity: Number(form.capacity),
        }),
      }),
    onSuccess: () => {
      setForm(empty);
      setEditingId(null);
      void qc.invalidateQueries({ queryKey: ["rooms"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/rooms/${id}`, { method: "DELETE" }),
    onSuccess: (_data, id) => {
      if (editingId === id) {
        setEditingId(null);
        setForm(empty);
      }
      void qc.invalidateQueries({ queryKey: ["rooms"] });
    },
  });

  function resetForm() {
    setEditingId(null);
    setForm(empty);
    save.reset();
  }

  function startEdit(r: Room) {
    setEditingId(r.id);
    setForm({ name: r.name, capacity: r.capacity });
    save.reset();
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  return (
    <div>
      <PageHeader title="Salles" subtitle="Capacités et salles disponibles" />
      <div className="grid lg:grid-cols-[340px_1fr] gap-6">
        <Card className="p-5 h-fit">
          <h2 className="font-semibold mb-4">
            {editingId ? "Modifier la salle" : "Nouvelle salle"}
          </h2>
          <form className="space-y-3" onSubmit={onSubmit}>
            <Input
              label="Nom"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
            <Input
              label="Capacité"
              type="number"
              value={form.capacity}
              onChange={(e) =>
                setForm({ ...form, capacity: Number(e.target.value) })
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
                <th className="px-4 py-3">Nom</th>
                <th className="px-4 py-3">Capacité</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className="border-t border-line">
                  <td className="px-4 py-3 font-medium">{r.name}</td>
                  <td className="px-4 py-3">{r.capacity}</td>
                  <td className="px-4 py-3 text-right">
                    <Button variant="ghost" onClick={() => startEdit(r)}>
                      Modifier
                    </Button>
                    <Button variant="ghost" onClick={() => remove.mutate(r.id)}>
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

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, Input, PageHeader } from "../components/ui";

type Room = { id: number; name: string; capacity: number };

export function RoomsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ name: "", capacity: 30 });
  const { data = [] } = useQuery({
    queryKey: ["rooms"],
    queryFn: () => api<Room[]>("/admin/rooms"),
  });

  const create = useMutation({
    mutationFn: () =>
      api("/admin/rooms", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          capacity: Number(form.capacity),
        }),
      }),
    onSuccess: () => {
      setForm({ name: "", capacity: 30 });
      void qc.invalidateQueries({ queryKey: ["rooms"] });
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/rooms/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["rooms"] }),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  return (
    <div>
      <PageHeader title="Salles" subtitle="Capacités et salles disponibles" />
      <div className="grid lg:grid-cols-[340px_1fr] gap-6">
        <Card className="p-5 h-fit">
          <h2 className="font-semibold mb-4">Nouvelle salle</h2>
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
            <Button className="w-full">Ajouter</Button>
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

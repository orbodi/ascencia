import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, Input, PageHeader } from "../components/ui";

type Teacher = {
  id: number;
  name: string;
  email: string;
  phone_whatsapp: string | null;
  is_active: boolean;
};

const empty = { name: "", email: "", phone_whatsapp: "", is_active: true };

export function TeachersPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(empty);
  const { data = [], isLoading } = useQuery({
    queryKey: ["teachers"],
    queryFn: () => api<Teacher[]>("/admin/teachers"),
  });

  const create = useMutation({
    mutationFn: () =>
      api("/admin/teachers", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          phone_whatsapp: form.phone_whatsapp || null,
        }),
      }),
    onSuccess: () => {
      setForm(empty);
      void qc.invalidateQueries({ queryKey: ["teachers"] });
    },
  });

  const archive = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/teachers/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["teachers"] }),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  return (
    <div>
      <PageHeader title="Enseignants" subtitle="Référentiel des professeurs" />
      <div className="grid lg:grid-cols-[340px_1fr] gap-6">
        <Card className="p-5 h-fit">
          <h2 className="font-semibold mb-4">Nouvel enseignant</h2>
          <form className="space-y-3" onSubmit={onSubmit}>
            <Input
              label="Nom complet"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
            <Input
              label="Email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required
            />
            <Input
              label="WhatsApp"
              placeholder="+336..."
              value={form.phone_whatsapp}
              onChange={(e) =>
                setForm({ ...form, phone_whatsapp: e.target.value })
              }
            />
            <Button className="w-full" disabled={create.isPending}>
              Ajouter
            </Button>
          </form>
        </Card>
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-mist text-left">
              <tr>
                <th className="px-4 py-3">Nom</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">WhatsApp</th>
                <th className="px-4 py-3">Statut</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-4 text-ink-soft">
                    Chargement…
                  </td>
                </tr>
              ) : (
                data.map((t) => (
                  <tr key={t.id} className="border-t border-line">
                    <td className="px-4 py-3 font-medium">{t.name}</td>
                    <td className="px-4 py-3">{t.email}</td>
                    <td className="px-4 py-3">{t.phone_whatsapp || "—"}</td>
                    <td className="px-4 py-3">
                      {t.is_active ? (
                        <span className="text-accent">Actif</span>
                      ) : (
                        <span className="text-ink-soft">Archivé</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {t.is_active ? (
                        <Button
                          variant="ghost"
                          onClick={() => archive.mutate(t.id)}
                        >
                          Archiver
                        </Button>
                      ) : null}
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

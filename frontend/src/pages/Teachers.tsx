import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, Input, PageHeader, Select } from "../components/ui";

type Teacher = {
  id: number;
  name: string;
  email: string;
  phone_whatsapp: string | null;
  is_active: boolean;
};

type OutreachResult = {
  ok: boolean;
  targeted?: number;
  delivered_ok?: number;
  form_url?: string;
  error?: string;
  detail?: string;
};

const empty = { name: "", email: "", phone_whatsapp: "", is_active: true };

export function TeachersPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(empty);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [channel, setChannel] = useState<"both" | "whatsapp" | "email">("both");
  const [outreachMsg, setOutreachMsg] = useState<string | null>(null);
  const { data = [], isLoading } = useQuery({
    queryKey: ["teachers"],
    queryFn: () => api<Teacher[]>("/admin/teachers"),
  });

  const save = useMutation({
    mutationFn: () =>
      api(editingId ? `/admin/teachers/${editingId}` : "/admin/teachers", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify({
          ...form,
          phone_whatsapp: form.phone_whatsapp || null,
        }),
      }),
    onSuccess: () => {
      setForm(empty);
      setEditingId(null);
      void qc.invalidateQueries({ queryKey: ["teachers"] });
    },
  });

  const archive = useMutation({
    mutationFn: (id: number) =>
      api(`/admin/teachers/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["teachers"] }),
  });

  const sendForm = useMutation({
    mutationFn: (payload: {
      teacher_id?: number;
      channel: string;
    }) =>
      api<OutreachResult>("/admin/outreach/availability-form/send", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (result, variables) => {
      const scope = variables.teacher_id
        ? "1 enseignant"
        : `${result.targeted ?? 0} enseignant(s)`;
      setOutreachMsg(
        result.ok
          ? `Formulaire envoyé (${scope}, ${result.delivered_ok}/${result.targeted} OK).`
          : `Envoi partiel ou en échec (${result.delivered_ok ?? 0}/${result.targeted ?? 0}). Vérifiez mock WhatsApp/e-mail et les numéros.`
      );
    },
    onError: (err: Error) => {
      setOutreachMsg(err.message || "Envoi impossible");
    },
  });

  function resetForm() {
    setEditingId(null);
    setForm(empty);
    save.reset();
  }

  function startEdit(t: Teacher) {
    setEditingId(t.id);
    setForm({
      name: t.name,
      email: t.email,
      phone_whatsapp: t.phone_whatsapp || "",
      is_active: t.is_active,
    });
    save.reset();
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  const activeCount = data.filter((t) => t.is_active).length;

  return (
    <div>
      <PageHeader
        title="Enseignants"
        subtitle="Référentiel et collecte des disponibilités"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={channel}
              onChange={(e) =>
                setChannel(e.target.value as "both" | "whatsapp" | "email")
              }
              aria-label="Canal d'envoi"
            >
              <option value="both">E-mail + WhatsApp</option>
              <option value="whatsapp">WhatsApp</option>
              <option value="email">E-mail</option>
            </Select>
            <Button
              disabled={sendForm.isPending || activeCount === 0}
              onClick={() => {
                setOutreachMsg(null);
                if (
                  !window.confirm(
                    `Envoyer le formulaire de disponibilités à ${activeCount} enseignant(s) actif(s) ?`
                  )
                ) {
                  return;
                }
                sendForm.mutate({ channel });
              }}
            >
              {sendForm.isPending
                ? "Envoi…"
                : "Contacter pour le planning"}
            </Button>
          </div>
        }
      />

      {outreachMsg ? (
        <Card className="mb-4 border-brand-blue/20 p-3 text-sm text-ink">
          {outreachMsg}
        </Card>
      ) : null}

      <div className="grid lg:grid-cols-[340px_1fr] gap-6">
        <Card className="p-5 h-fit">
          <h2 className="font-semibold mb-4">
            {editingId ? "Modifier l'enseignant" : "Nouvel enseignant"}
          </h2>
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
            {editingId ? (
              <Select
                label="Statut"
                value={form.is_active ? "1" : "0"}
                onChange={(e) =>
                  setForm({ ...form, is_active: e.target.value === "1" })
                }
              >
                <option value="1">Actif</option>
                <option value="0">Archivé</option>
              </Select>
            ) : null}
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
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button variant="ghost" onClick={() => startEdit(t)}>
                          Modifier
                        </Button>
                        {t.is_active ? (
                          <Button
                            variant="ghost"
                            disabled={sendForm.isPending}
                            onClick={() => {
                              setOutreachMsg(null);
                              sendForm.mutate({
                                teacher_id: t.id,
                                channel,
                              });
                            }}
                          >
                            Formulaire
                          </Button>
                        ) : null}
                        {t.is_active ? (
                          <Button
                            variant="ghost"
                            onClick={() => archive.mutate(t.id)}
                          >
                            Archiver
                          </Button>
                        ) : null}
                      </div>
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

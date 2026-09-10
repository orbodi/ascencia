import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Button, Card, Input, PageHeader, Select, TextArea } from "../components/ui";

type ConfigItem = {
  key: string;
  value: string;
  description?: string | null;
};

const MODELS = [
  "gemini-3.5-flash-lite",
  "gemini-3.6-flash",
  "gemini-3.5-flash",
  "gemini-3.1-flash-lite",
];

export function ConfigPage() {
  const qc = useQueryClient();
  const { data = [] } = useQuery({
    queryKey: ["config"],
    queryFn: () => api<ConfigItem[]>("/admin/config"),
  });

  const nameRow = data.find((c) => c.key === "agent_display_name");
  const promptRow = data.find((c) => c.key === "agent_system_prompt");
  const modelRow = data.find((c) => c.key === "gemini_model");
  const daysRow = data.find((c) => c.key === "reminder_days_ahead");
  const formUrlRow = data.find((c) => c.key === "availability_form_url");

  const [agentName, setAgentName] = useState("Ascencia");
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState(MODELS[0]);
  const [days, setDays] = useState("3");
  const [formUrl, setFormUrl] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (nameRow) setAgentName(nameRow.value);
    if (promptRow) setPrompt(promptRow.value);
    if (modelRow) setModel(modelRow.value);
    if (daysRow) setDays(daysRow.value);
    if (formUrlRow) setFormUrl(formUrlRow.value);
  }, [nameRow, promptRow, modelRow, daysRow, formUrlRow]);

  const save = useMutation({
    mutationFn: async () => {
      const name = agentName.trim() || "Ascencia";
      await api(`/admin/config/agent_display_name`, {
        method: "PUT",
        body: JSON.stringify({ value: name }),
      });
      await api(`/admin/config/agent_system_prompt`, {
        method: "PUT",
        body: JSON.stringify({ value: prompt }),
      });
      await api(`/admin/config/gemini_model`, {
        method: "PUT",
        body: JSON.stringify({ value: model }),
      });
      await api(`/admin/config/reminder_days_ahead`, {
        method: "PUT",
        body: JSON.stringify({ value: days }),
      });
      await api(`/admin/config/availability_form_url`, {
        method: "PUT",
        body: JSON.stringify({ value: formUrl.trim() }),
      });
    },
    onSuccess: () => {
      setSaved(true);
      void qc.invalidateQueries({ queryKey: ["config"] });
      setTimeout(() => setSaved(false), 2000);
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  return (
    <div>
      <PageHeader
        title="Config IA"
        subtitle="Identité, comportement, formulaire de collecte et modèle IA"
      />
      <Card className="p-6 max-w-4xl">
        <form className="space-y-5" onSubmit={onSubmit}>
          <Input
            label="Nom de l'assistant IA"
            value={agentName}
            onChange={(e) => setAgentName(e.target.value)}
            placeholder="Ascencia"
            required
          />
          <p className="text-xs text-ink-soft -mt-3">
            Utilisé dans le chat, les rappels WhatsApp et le prompt (placeholder{" "}
            <code className="font-mono">{"{agent_name}"}</code>).
          </p>
          <TextArea
            label="System prompt"
            rows={16}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <div className="grid sm:grid-cols-2 gap-4">
            <Select
              label="Modèle Gemini"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {[model, ...MODELS.filter((m) => m !== model)].map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </Select>
            <Input
              label="Rappels (jours avant)"
              type="number"
              min={1}
              max={14}
              value={days}
              onChange={(e) => setDays(e.target.value)}
            />
          </div>
          <Input
            label="Lien du formulaire de disponibilités"
            type="url"
            value={formUrl}
            onChange={(e) => setFormUrl(e.target.value)}
            placeholder="https://forms.example.com/disponibilites"
          />
          <p className="text-xs text-ink-soft -mt-3">
            L’agent peut transmettre ce formulaire par e-mail ou WhatsApp après validation explicite d’un administrateur.
          </p>
          <div className="flex items-center gap-3">
            <Button disabled={save.isPending}>
              {save.isPending ? "Enregistrement…" : "Enregistrer"}
            </Button>
            {saved ? (
              <span className="text-sm text-accent">Enregistré ✓</span>
            ) : null}
          </div>
        </form>
      </Card>
    </div>
  );
}

import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ChatMessageContent } from "../components/ChatMessageContent";
import { Button, Card, PageHeader } from "../components/ui";

type Msg = { role: "user" | "assistant"; content: string; id?: number };
type ConfigItem = { key: string; value: string };
type HistoryResponse = {
  messages: { id: number; role: string; content: string }[];
};

function welcomeMsg(agentName: string): Msg {
  return {
    role: "assistant",
    content: `Bonjour, je suis **${agentName}**, votre assistant de gestion des emplois du temps.\n\nPosez une question — ex. : *Alice Martin absente le 2026-08-05*, ou *planning de la semaine*.`,
  };
}

export function ChatPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const { data: config = [] } = useQuery({
    queryKey: ["config"],
    queryFn: () => api<ConfigItem[]>("/admin/config"),
  });
  const agentName =
    config.find((c) => c.key === "agent_display_name")?.value?.trim() ||
    "Ascencia";

  const {
    data: history,
    isLoading: historyLoading,
    isFetched: historyFetched,
  } = useQuery({
    queryKey: ["chat-history", user?.username],
    queryFn: () => api<HistoryResponse>("/admin/chat/history?limit=200"),
    enabled: !!user,
  });

  const [messages, setMessages] = useState<Msg[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!historyFetched || hydrated) return;
    const fromDb = (history?.messages || [])
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        content: m.content,
      }));
    setMessages(fromDb.length > 0 ? fromDb : [welcomeMsg(agentName)]);
    setHydrated(true);
  }, [historyFetched, history, agentName, hydrated]);

  useEffect(() => {
    if (!hydrated) return;
    bottomRef.current?.scrollIntoView({ behavior: "auto" });
  }, [hydrated, messages.length]);

  const clearHistory = useMutation({
    mutationFn: () => api("/admin/chat/history", { method: "DELETE" }),
    onSuccess: () => {
      setMessages([welcomeMsg(agentName)]);
      void qc.invalidateQueries({ queryKey: ["chat-history"] });
    },
  });

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const data = await api<{ reply: string }>("/admin/chat", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          channel: "backoffice",
          external_user_id: `bo:${user?.username || "admin"}`,
        }),
      });
      setMessages((m) => [
        ...m,
        { role: "assistant", content: data.reply || "(pas de réponse)" },
      ]);
      void qc.invalidateQueries({ queryKey: ["chat-history"] });
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `Erreur: ${err instanceof Error ? err.message : "inconnue"}`,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      <PageHeader
        title={`Chat ${agentName}`}
        subtitle="Historique conservé en base — survit au rechargement"
        actions={
          <Button
            variant="ghost"
            disabled={clearHistory.isPending || messages.length === 0}
            onClick={() => {
              if (confirm("Effacer l'historique de conversation ?")) {
                clearHistory.mutate();
              }
            }}
          >
            Nouvelle conversation
          </Button>
        }
      />
      <Card className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-auto p-4 space-y-4 bg-[linear-gradient(180deg,rgba(243,247,245,0.5)_0%,rgba(226,236,231,0.65)_100%)]">
          {historyLoading && !hydrated ? (
            <p className="text-sm text-ink-soft">Chargement de l'historique…</p>
          ) : (
            messages.map((m, i) => (
              <div
                key={m.id ?? `local-${i}`}
                className={`flex ${
                  m.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`rounded-2xl px-4 py-3 text-sm shadow-sm ${
                    m.role === "user"
                      ? "max-w-[min(92%,28rem)] bg-accent text-white rounded-br-md"
                      : "max-w-[min(96%,52rem)] w-full bg-white border border-line text-ink rounded-bl-md"
                  }`}
                >
                  {m.role === "assistant" ? (
                    <div className="text-[10px] uppercase tracking-wider text-accent font-semibold mb-2">
                      {agentName}
                    </div>
                  ) : null}
                  <ChatMessageContent content={m.content} variant={m.role} />
                </div>
              </div>
            ))
          )}
          {busy ? (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-bl-md border border-line bg-white px-4 py-3 text-sm text-ink-soft shadow-sm">
                <span className="inline-flex gap-1 items-center">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse"
                    style={{ animationDelay: "150ms" }}
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse"
                    style={{ animationDelay: "300ms" }}
                  />
                  <span className="ml-2">{agentName} réfléchit…</span>
                </span>
              </div>
            </div>
          ) : null}
          <div ref={bottomRef} />
        </div>
        <form
          onSubmit={send}
          className="border-t border-line p-3 flex gap-2 bg-white"
        >
          <input
            className="flex-1 rounded-xl border border-line px-3 py-2.5 outline-none focus:border-accent"
            placeholder="Écrire un message…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
          />
          <Button disabled={busy || !input.trim()}>
            {busy ? "…" : "Envoyer"}
          </Button>
        </form>
      </Card>
    </div>
  );
}

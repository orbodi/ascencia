import { useQuery } from "@tanstack/react-query";
import { getToken } from "../lib/api";
import { Card, PageHeader } from "../components/ui";

export function HistoryPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["history"],
    queryFn: async () => {
      const apiToken = import.meta.env.VITE_API_TOKEN || "change-me";
      const token = getToken();
      const res = await fetch("/history/teacher-actions?kind=all", {
        headers: {
          "X-API-Token": apiToken,
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
  });

  return (
    <div>
      <PageHeader
        title="Historique"
        subtitle="Confirmations, reports et rappels"
      />
      <Card className="p-5">
        {isLoading ? (
          <p className="text-ink-soft">Chargement…</p>
        ) : error ? (
          <p className="text-warn">Impossible de charger l'historique</p>
        ) : (
          <pre className="text-xs overflow-auto whitespace-pre-wrap">
            {JSON.stringify(data, null, 2)}
          </pre>
        )}
      </Card>
    </div>
  );
}

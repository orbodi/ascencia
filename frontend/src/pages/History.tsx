import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Card, PageHeader } from "../components/ui";

export function HistoryPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["history"],
    queryFn: () => api("/admin/history/teacher-actions?kind=all"),
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

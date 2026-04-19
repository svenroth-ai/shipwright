import { useQuery } from "@tanstack/react-query";
import { getDiagnostics, type DiagnosticsSnapshot } from "../lib/externalApi";

export function useDiagnostics() {
  return useQuery<DiagnosticsSnapshot>({
    queryKey: ["diagnostics"],
    queryFn: getDiagnostics,
    refetchInterval: 30_000,
  });
}

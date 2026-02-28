import { useQuery } from "@tanstack/react-query";

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => fetchApi("/api/health") });
}

export function useStats() {
  return useQuery({ queryKey: ["stats"], queryFn: () => fetchApi("/api/stats") });
}

export function useCoverage() {
  return useQuery({ queryKey: ["coverage"], queryFn: () => fetchApi("/api/coverage") });
}

export function useChangelog() {
  return useQuery({ queryKey: ["changelog"], queryFn: () => fetchApi("/api/changelog") });
}

export function useScores() {
  return useQuery({ queryKey: ["scores"], queryFn: () => fetchApi("/api/scores") });
}

export function useDepGraph() {
  return useQuery({ queryKey: ["depgraph"], queryFn: () => fetchApi("/api/depgraph") });
}

export function useDoctor() {
  return useQuery({ queryKey: ["doctor"], queryFn: () => fetchApi("/api/doctor") });
}

export function useTodos() {
  return useQuery({ queryKey: ["todos"], queryFn: () => fetchApi("/api/todos") });
}

export function useTriage() {
  return useQuery({ queryKey: ["triage"], queryFn: () => fetchApi("/api/triage") });
}

export function usePlan() {
  return useQuery({ queryKey: ["plan"], queryFn: () => fetchApi("/api/plan") });
}

export function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: () => fetchApi("/api/sessions") });
}

export function useReplay(session: number) {
  return useQuery({
    queryKey: ["replay", session],
    queryFn: () => fetchApi(`/api/replay/${session}`),
    enabled: session > 0,
  });
}

export function useDiff(session: number) {
  return useQuery({
    queryKey: ["diff", session],
    queryFn: () => fetchApi(`/api/diff/${session}`),
    enabled: session > 0,
  });
}

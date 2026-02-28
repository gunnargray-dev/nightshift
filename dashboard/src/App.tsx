import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Overview } from "./views/Overview";
import { Sessions } from "./views/Sessions";
import { Health } from "./views/Health";
import { Coverage } from "./views/Coverage";
import { Dependencies } from "./views/Dependencies";
import { BrainView } from "./views/BrainView";
import { Diagnostics } from "./views/Diagnostics";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 30_000,
      staleTime: 10_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="flex h-screen">
          <Sidebar />
          <main className="flex-1 overflow-y-auto p-8">
            <Routes>
              <Route path="/" element={<Navigate to="/overview" replace />} />
              <Route path="/overview" element={<Overview />} />
              <Route path="/sessions" element={<Sessions />} />
              <Route path="/health" element={<Health />} />
              <Route path="/coverage" element={<Coverage />} />
              <Route path="/dependencies" element={<Dependencies />} />
              <Route path="/brain" element={<BrainView />} />
              <Route path="/diagnostics" element={<Diagnostics />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

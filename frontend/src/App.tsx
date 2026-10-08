import { useState } from "react";
import type { SessionRun } from "./api/types";
import { AppShell, type PageId } from "./components/layout/AppShell";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ResearchPage } from "./pages/ResearchPage";
import { RunsPage } from "./pages/RunsPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  const [page, setPage] = useState<PageId>("research");
  const [runs, setRuns] = useState<SessionRun[]>([]);
  const addRun = (run: SessionRun) => setRuns((current) => [run, ...current.filter((item) => item.runId !== run.runId)]);
  return (
    <AppShell page={page} onNavigate={setPage}>
      {page === "research" && <ResearchPage onRunComplete={addRun} />}
      {page === "documents" && <DocumentsPage />}
      {page === "runs" && <RunsPage runs={runs} />}
      {page === "settings" && <SettingsPage />}
    </AppShell>
  );
}

import { BookOpen, FileText, FlaskConical, Settings, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export type PageId = "research" | "documents" | "runs" | "settings";

const items: { id: PageId; label: string; icon: LucideIcon }[] = [
  { id: "research", label: "Research", icon: FlaskConical },
  { id: "documents", label: "Documents", icon: FileText },
  { id: "runs", label: "Runs", icon: BookOpen },
  { id: "settings", label: "Settings", icon: Settings },
];

export function AppShell({ page, onNavigate, children }: {
  page: PageId;
  onNavigate: (page: PageId) => void;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-canvas text-ink lg:flex">
      <aside className="border-b border-line bg-white lg:fixed lg:inset-y-0 lg:w-64 lg:border-b-0 lg:border-r">
        <div className="flex h-18 items-center gap-3 px-5 py-4 lg:px-6 lg:py-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-sm">
            <FlaskConical className="h-5 w-5" />
          </div>
          <div>
            <div className="font-bold tracking-tight">AgentEvidence</div>
            <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">Research Workspace</div>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 lg:block lg:space-y-1 lg:px-4 lg:pt-4">
          {items.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => onNavigate(id)}
              className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors lg:w-full ${
                page === id ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-50 hover:text-ink"
              }`}
            >
              <Icon className="h-[18px] w-[18px]" />
              {label}
            </button>
          ))}
        </nav>
        <div className="hidden border-t border-line p-5 lg:absolute lg:inset-x-0 lg:bottom-0 lg:block">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Local workspace
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 lg:ml-64">
        <div className="mx-auto max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</div>
      </main>
    </div>
  );
}

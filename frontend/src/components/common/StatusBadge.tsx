import { AlertTriangle, CheckCircle2, Circle, LoaderCircle, XCircle } from "lucide-react";

interface Props {
  status: string;
  label?: string;
}

export function StatusBadge({ status, label }: Props) {
  const style = status === "success" || status === "completed"
    ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : status === "evidence_insufficient"
      ? "bg-amber-50 text-amber-800 border-amber-200"
      : status === "error" || status === "failed"
        ? "bg-rose-50 text-rose-700 border-rose-200"
        : status === "running" || status === "processing"
          ? "bg-blue-50 text-blue-700 border-blue-200"
          : "bg-slate-50 text-slate-600 border-slate-200";
  const Icon = status === "success" || status === "completed"
    ? CheckCircle2
    : status === "evidence_insufficient"
      ? AlertTriangle
      : status === "error" || status === "failed"
        ? XCircle
        : status === "running" || status === "processing"
          ? LoaderCircle
          : Circle;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${style}`}>
      <Icon className={`h-3.5 w-3.5 ${status === "running" || status === "processing" ? "animate-spin" : ""}`} />
      {label ?? status.replaceAll("_", " ")}
    </span>
  );
}

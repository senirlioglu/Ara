"use client";

export type ViewMode = "liste" | "afis";

interface Props {
  mode: ViewMode;
  hasPoster: boolean;
  hasList: boolean;
  onChange: (m: ViewMode) => void;
}

export function ModeToggle({ mode, hasPoster, hasList, onChange }: Props) {
  if (!hasPoster && !hasList) return null;
  if (hasPoster && !hasList) return null;
  if (!hasPoster && hasList) return null;

  return (
    <div className="inline-flex p-1 rounded-card bg-white border border-slate-200 shadow-sm">
      <button
        onClick={() => onChange("liste")}
        className={
          "px-4 py-1.5 rounded-md text-sm font-medium transition " +
          (mode === "liste"
            ? "bg-gradient-to-r from-brand-start to-brand-end text-white"
            : "text-ink-700 hover:bg-slate-100")
        }
      >
        Liste
      </button>
      <button
        onClick={() => onChange("afis")}
        className={
          "px-4 py-1.5 rounded-md text-sm font-medium transition " +
          (mode === "afis"
            ? "bg-gradient-to-r from-brand-start to-brand-end text-white"
            : "text-ink-700 hover:bg-slate-100")
        }
      >
        Afiş
      </button>
    </div>
  );
}

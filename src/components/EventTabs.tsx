"use client";

import type { HalkgunuEvent } from "@/lib/types";
import { formatShortDate } from "@/lib/format";

interface Props {
  events: HalkgunuEvent[];
  activeEventId: string | null;
  onSelect: (eventId: string) => void;
}

export function EventTabs({ events, activeEventId, onSelect }: Props) {
  if (events.length === 0) {
    return (
      <div className="text-center text-ink-500 py-6">
        Şu an aktif bir Halk Günü etkinliği yok.
      </div>
    );
  }
  return (
    <div className="flex gap-2 overflow-x-auto pb-2 -mx-4 px-4 snap-x">
      {events.map((ev) => {
        const isActive = ev.event_id === activeEventId;
        return (
          <button
            key={ev.event_id}
            onClick={() => onSelect(ev.event_id)}
            className={
              "snap-start whitespace-nowrap px-4 py-2 rounded-card text-sm font-medium transition " +
              (isActive
                ? "bg-gradient-to-r from-brand-start to-brand-end text-white shadow-brand"
                : "bg-white text-ink-700 hover:bg-slate-100 border border-slate-200")
            }
          >
            <div className="text-xs opacity-80">{formatShortDate(ev.event_date)}</div>
            <div>{ev.event_name}</div>
          </button>
        );
      })}
    </div>
  );
}

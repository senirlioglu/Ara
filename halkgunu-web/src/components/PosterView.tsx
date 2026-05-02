"use client";

import { useEffect, useMemo, useState } from "react";
import { listEventMappings, listEventPages } from "@/lib/api";
import { posterImageUrl } from "@/lib/supabase";
import type { HalkgunuMapping, HalkgunuPage } from "@/lib/types";

interface Props {
  eventId: string;
  onProductClick: (urunKod: string) => void;
}

export function PosterView({ eventId, onProductClick }: Props) {
  const [pages, setPages] = useState<HalkgunuPage[]>([]);
  const [mappings, setMappings] = useState<HalkgunuMapping[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([listEventPages(eventId), listEventMappings(eventId)])
      .then(([p, m]) => {
        if (cancelled) return;
        setPages(p);
        setMappings(m);
        setActiveIdx(0);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  const activePage = pages[activeIdx];

  const pageMappings = useMemo(() => {
    if (!activePage) return [];
    return mappings.filter(
      (m) =>
        m.flyer_filename === activePage.flyer_filename &&
        m.page_no === activePage.page_no,
    );
  }, [mappings, activePage]);

  if (loading) {
    return <div className="text-center py-10 text-ink-500">Yükleniyor…</div>;
  }
  if (error) {
    return <div className="text-center py-10 text-rose-600">Hata: {error}</div>;
  }
  if (pages.length === 0) {
    return (
      <div className="text-center py-10 text-ink-500">
        Bu etkinlik için afiş henüz yüklenmemiş.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {pages.length > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-2">
          {pages.map((p, i) => (
            <button
              key={p.id}
              onClick={() => setActiveIdx(i)}
              className={
                "shrink-0 w-20 h-24 rounded-md overflow-hidden border-2 transition " +
                (i === activeIdx
                  ? "border-brand-start shadow-brand"
                  : "border-slate-200 hover:border-slate-400")
              }
              title={p.title || `Sayfa ${i + 1}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={posterImageUrl(p.image_path)}
                alt={p.title || `Sayfa ${i + 1}`}
                className="w-full h-full object-cover"
                loading="lazy"
              />
            </button>
          ))}
        </div>
      )}

      <div className="relative w-full bg-white rounded-card overflow-hidden shadow-sm border border-slate-200">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={posterImageUrl(activePage.image_path)}
          alt={activePage.title || ""}
          className="w-full h-auto block"
        />
        {pageMappings.map((m) => (
          <button
            key={m.mapping_id}
            type="button"
            onClick={() => m.urun_kodu && onProductClick(m.urun_kodu)}
            disabled={!m.urun_kodu}
            className="absolute border-2 border-brand-start/70 hover:border-brand-end hover:bg-brand-start/10 transition cursor-pointer rounded-sm"
            style={{
              left: `${m.x0 * 100}%`,
              top: `${m.y0 * 100}%`,
              width: `${(m.x1 - m.x0) * 100}%`,
              height: `${(m.y1 - m.y0) * 100}%`,
            }}
            title={m.urun_kodu ? `${m.urun_kodu} — ${m.urun_aciklamasi ?? ""}` : ""}
          />
        ))}
      </div>
    </div>
  );
}

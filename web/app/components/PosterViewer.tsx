"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { PosterPage, Hotspot } from "@/lib/types";
import { getPosterImageUrl } from "@/lib/api";

interface PosterViewerProps {
  pages: PosterPage[];
  mappings: Hotspot[];
  onHotspotClick?: (urunKodu: string) => void;
}

export default function PosterViewer({
  pages,
  mappings,
  onHotspotClick,
}: PosterViewerProps) {
  const [currentIdx, setCurrentIdx] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const total = pages.length;
  const page = pages[currentIdx];

  // Get hotspots for current page
  const pageHotspots = mappings.filter(
    (m) =>
      m.flyer_filename === page?.flyer_filename && m.page_no === page?.page_no
  );

  const goNext = useCallback(() => {
    setCurrentIdx((i) => (i + 1) % total);
  }, [total]);

  const goPrev = useCallback(() => {
    setCurrentIdx((i) => (i - 1 + total) % total);
  }, [total]);

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goPrev();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goNext, goPrev]);

  // Swipe support
  const touchStartX = useRef(0);
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
  };
  const handleTouchEnd = (e: React.TouchEvent) => {
    const dx = e.changedTouches[0].clientX - touchStartX.current;
    if (Math.abs(dx) > 50) {
      if (dx < 0) goNext();
      else goPrev();
    }
  };

  if (!page) return null;

  const imageUrl = getPosterImageUrl(page.image_path);

  return (
    <div className="relative w-full" ref={containerRef}>
      {/* Image + hotspots */}
      <div
        className="relative w-full"
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl}
          alt={page.title || `Sayfa ${currentIdx + 1}`}
          className="w-full h-auto rounded-xl"
          draggable={false}
        />

        {/* Hotspot overlays */}
        {pageHotspots.map((hs) => (
          <button
            key={hs.mapping_id}
            onClick={() => onHotspotClick?.(hs.urun_kodu)}
            className="absolute border-2 border-primary/40 bg-primary/10
                       hover:bg-primary/20 hover:border-primary/60
                       rounded-md transition-colors cursor-pointer
                       flex items-center justify-center"
            style={{
              left: `${hs.x0 * 100}%`,
              top: `${hs.y0 * 100}%`,
              width: `${(hs.x1 - hs.x0) * 100}%`,
              height: `${(hs.y1 - hs.y0) * 100}%`,
            }}
            aria-label={`Ürün: ${hs.urun_kodu}`}
          >
            <span className="text-xs bg-white/90 text-gray-700 px-1.5 py-0.5 rounded font-medium opacity-0 hover:opacity-100 transition-opacity">
              {hs.urun_kodu}
            </span>
          </button>
        ))}
      </div>

      {/* Navigation arrows */}
      {total > 1 && (
        <>
          <button
            onClick={goPrev}
            className="absolute left-2 top-1/2 -translate-y-1/2 w-10 h-10
                       bg-black/30 hover:bg-black/50 text-white rounded-full
                       flex items-center justify-center backdrop-blur-sm transition-colors"
            aria-label="Önceki sayfa"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            onClick={goNext}
            className="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10
                       bg-black/30 hover:bg-black/50 text-white rounded-full
                       flex items-center justify-center backdrop-blur-sm transition-colors"
            aria-label="Sonraki sayfa"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </>
      )}

      {/* Page indicator */}
      {total > 1 && (
        <div className="flex items-center justify-center gap-1.5 mt-3">
          {total <= 20 ? (
            pages.map((_, i) => (
              <button
                key={i}
                onClick={() => setCurrentIdx(i)}
                className={`w-2 h-2 rounded-full transition-all ${
                  i === currentIdx
                    ? "bg-primary w-4"
                    : "bg-gray-300 hover:bg-gray-400"
                }`}
                aria-label={`Sayfa ${i + 1}`}
              />
            ))
          ) : (
            <span className="text-sm text-gray-500 font-medium">
              {currentIdx + 1} / {total}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

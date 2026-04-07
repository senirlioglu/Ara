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

  // Smooth swipe support with tracking
  const touchRef = useRef({ startX: 0, startY: 0, startTime: 0, tracking: false });
  const [swipeOffset, setSwipeOffset] = useState(0);

  const handleTouchStart = (e: React.TouchEvent) => {
    touchRef.current = {
      startX: e.touches[0].clientX,
      startY: e.touches[0].clientY,
      startTime: Date.now(),
      tracking: true,
    };
    setSwipeOffset(0);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (!touchRef.current.tracking) return;
    const dx = e.touches[0].clientX - touchRef.current.startX;
    const dy = e.touches[0].clientY - touchRef.current.startY;

    // If vertical scroll is dominant, stop tracking horizontal swipe
    if (Math.abs(dy) > Math.abs(dx) && Math.abs(dx) < 10) {
      touchRef.current.tracking = false;
      setSwipeOffset(0);
      return;
    }

    // Prevent vertical scroll when swiping horizontally
    if (Math.abs(dx) > 10) {
      e.preventDefault();
    }

    setSwipeOffset(dx);
  };

  const handleTouchEnd = () => {
    if (!touchRef.current.tracking) return;
    const dx = swipeOffset;
    const elapsed = Date.now() - touchRef.current.startTime;
    const velocity = Math.abs(dx) / elapsed;

    // Swipe threshold: either enough distance or fast enough
    if (Math.abs(dx) > 40 || (velocity > 0.3 && Math.abs(dx) > 15)) {
      if (dx < 0) goNext();
      else goPrev();
    }

    touchRef.current.tracking = false;
    setSwipeOffset(0);
  };

  if (!page) return null;

  const imageUrl = getPosterImageUrl(page.image_path);

  return (
    <div className="relative w-full overflow-hidden" ref={containerRef}>
      {/* Image + hotspots — swipeable */}
      <div
        className="relative w-full transition-transform duration-200 ease-out"
        style={{
          transform: swipeOffset ? `translateX(${swipeOffset}px)` : undefined,
          transition: swipeOffset ? "none" : "transform 0.2s ease-out",
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl}
          alt={page.title || `Sayfa ${currentIdx + 1}`}
          className="w-full h-auto rounded-xl select-none"
          draggable={false}
        />

        {/* Hotspot overlays — invisible, only magnifier icon on press */}
        {pageHotspots.map((hs) => (
          <button
            key={hs.mapping_id}
            onClick={() => onHotspotClick?.(hs.urun_kodu)}
            className="absolute bg-transparent cursor-pointer
                       active:bg-white/20 transition-colors
                       flex items-center justify-center group"
            style={{
              left: `${hs.x0 * 100}%`,
              top: `${hs.y0 * 100}%`,
              width: `${(hs.x1 - hs.x0) * 100}%`,
              height: `${(hs.y1 - hs.y0) * 100}%`,
            }}
            aria-label={`Ürün: ${hs.urun_kodu}`}
          >
            {/* Magnifier icon — semi-transparent, like Streamlit */}
            <span className="w-8 h-8 bg-black/40 rounded-full flex items-center justify-center
                            opacity-60 group-hover:opacity-90 group-active:opacity-100 transition-opacity">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
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

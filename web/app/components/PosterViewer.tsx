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
  const [transitioning, setTransitioning] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const total = pages.length;
  const page = pages[currentIdx];

  // Reset to first page when pages change (week switch)
  const pagesKey = pages.map((p) => p.id).join(",");
  useEffect(() => {
    setCurrentIdx(0);
    setTransitioning(false);
  }, [pagesKey]);

  const pageHotspots = transitioning
    ? []
    : mappings.filter(
        (m) =>
          m.flyer_filename === page?.flyer_filename && m.page_no === page?.page_no
      );

  // Swipe state
  const touchState = useRef({
    startX: 0,
    startY: 0,
    startTime: 0,
    isDragging: false,
    dirLocked: false,
    isHorizontal: false,
  });

  const changePage = useCallback((idx: number) => {
    if (idx < 0 || idx >= total || idx === currentIdx) return;
    setTransitioning(true);
    // Brief fade-out, then switch
    setTimeout(() => {
      setCurrentIdx(idx);
      // Fade-in after state update
      setTimeout(() => setTransitioning(false), 50);
    }, 150);
  }, [total, currentIdx]);

  const goNext = useCallback(() => changePage((currentIdx + 1) % total), [changePage, currentIdx, total]);
  const goPrev = useCallback(() => changePage((currentIdx - 1 + total) % total), [changePage, currentIdx, total]);

  // Keyboard
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goPrev();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goNext, goPrev]);

  // Touch: swipe detection with direction lock
  const handleTouchStart = (e: React.TouchEvent) => {
    const ts = touchState.current;
    if (total <= 1) return;

    ts.startX = e.touches[0].clientX;
    ts.startY = e.touches[0].clientY;
    ts.startTime = Date.now();
    ts.isDragging = false;
    ts.dirLocked = false;
    ts.isHorizontal = false;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    const ts = touchState.current;
    if (total <= 1) return;

    const dx = e.touches[0].clientX - ts.startX;
    const dy = e.touches[0].clientY - ts.startY;

    if (!ts.dirLocked && (Math.abs(dx) > 4 || Math.abs(dy) > 4)) {
      ts.dirLocked = true;
      ts.isHorizontal = Math.abs(dx) > Math.abs(dy);
    }

    if (ts.isHorizontal) {
      e.preventDefault();
      ts.isDragging = true;
    }
  };

  const handleTouchEnd = () => {
    const ts = touchState.current;
    if (!ts.isDragging || !ts.isHorizontal) return;

    const dx = ts.isDragging
      ? (event as unknown as TouchEvent)?.changedTouches?.[0]?.clientX
        ? (event as unknown as TouchEvent).changedTouches[0].clientX - ts.startX
        : 0
      : 0;

    // Use stored start position for calculation
    ts.isDragging = false;
  };

  // Simplified touch end using a ref to track last position
  const lastTouchX = useRef(0);

  const handleTouchMoveTracked = (e: React.TouchEvent) => {
    lastTouchX.current = e.touches[0].clientX;
    handleTouchMove(e);
  };

  const handleTouchEndTracked = () => {
    const ts = touchState.current;
    if (!ts.isHorizontal) return;

    const dx = lastTouchX.current - ts.startX;
    const elapsed = Date.now() - ts.startTime;
    const velocity = Math.abs(dx) / (elapsed || 1);

    if (Math.abs(dx) > 40 || (velocity > 0.3 && Math.abs(dx) > 15)) {
      if (dx < 0) goNext();
      else goPrev();
    }

    ts.isDragging = false;
  };

  if (!page) return null;

  const imageUrl = getPosterImageUrl(page.image_path);

  return (
    <div className="relative w-full" ref={wrapRef}>
      {/* Image + hotspots with fade transition */}
      <div
        className="relative w-full overflow-hidden rounded-xl"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMoveTracked}
        onTouchEnd={handleTouchEndTracked}
      >
        <div
          className="transition-opacity duration-150 ease-in-out"
          style={{ opacity: transitioning ? 0 : 1 }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={imageUrl}
            alt={page.title || `Sayfa ${currentIdx + 1}`}
            className="w-full h-auto select-none"
            draggable={false}
          />

          {/* Hotspots */}
          <div className="absolute inset-0">
            {pageHotspots.map((hs) => {
              const w = (hs.x1 - hs.x0) * 100;
              const h = (hs.y1 - hs.y0) * 100;
              const shorter = Math.min(w, h);
              const iconSize = Math.max(4, Math.min(8, shorter * 0.35));

              return (
                <button
                  key={hs.mapping_id}
                  onClick={() => {
                    if (touchState.current.isDragging) return;
                    onHotspotClick?.(hs.urun_kodu);
                  }}
                  className="absolute bg-transparent border-none cursor-pointer"
                  style={{
                    left: `${hs.x0 * 100}%`,
                    top: `${hs.y0 * 100}%`,
                    width: `${w}%`,
                    height: `${h}%`,
                    touchAction: "manipulation",
                    WebkitTapHighlightColor: "transparent",
                  }}
                  aria-label={`Ürün: ${hs.urun_kodu}`}
                >
                  <span
                    className="absolute bottom-0.5 right-0.5 rounded-full
                               bg-white/75 text-gray-700 flex items-center justify-center
                               shadow-sm hover:bg-white/95 active:bg-red-500 active:text-white
                               transition-all"
                    style={{
                      width: `${iconSize}vw`,
                      height: `${iconSize}vw`,
                      maxWidth: "34px",
                      maxHeight: "34px",
                      minWidth: "16px",
                      minHeight: "16px",
                    }}
                  >
                    <svg
                      className="w-[55%] h-[55%]"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2.5}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <circle cx="10" cy="10" r="6" />
                      <line x1="14.5" y1="14.5" x2="20" y2="20" />
                    </svg>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Navigation arrows */}
      {total > 1 && (
        <>
          <button
            onClick={goPrev}
            className="absolute left-1 top-1/2 -translate-y-1/2 w-9 h-9
                       bg-[rgba(30,58,95,0.85)] hover:bg-[rgba(30,58,95,1)] text-white rounded-full
                       flex items-center justify-center shadow-md transition-colors z-10"
            aria-label="Önceki sayfa"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            onClick={goNext}
            className="absolute right-1 top-1/2 -translate-y-1/2 w-9 h-9
                       bg-[rgba(30,58,95,0.85)] hover:bg-[rgba(30,58,95,1)] text-white rounded-full
                       flex items-center justify-center shadow-md transition-colors z-10"
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
        <div className="flex flex-col items-center gap-1 mt-2">
          {total <= 20 && (
            <div className="flex gap-1.5">
              {pages.map((_, i) => (
                <button
                  key={i}
                  onClick={() => changePage(i)}
                  className={`w-2 h-2 rounded-full transition-all ${
                    i === currentIdx
                      ? "bg-[#1e3a5f] scale-125"
                      : "bg-gray-300 hover:bg-gray-400"
                  }`}
                  aria-label={`Sayfa ${i + 1}`}
                />
              ))}
            </div>
          )}
          <span className="text-xs text-muted-foreground">
            {currentIdx + 1} / {total}
          </span>
        </div>
      )}
    </div>
  );
}

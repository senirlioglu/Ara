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
  const animatingRef = useRef(false);
  const currentRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const total = pages.length;
  const page = pages[currentIdx];

  // Reset to first page when pages change (week switch)
  const pagesKey = pages.map((p) => p.id).join(",");
  useEffect(() => {
    setCurrentIdx(0);
    animatingRef.current = false;
  }, [pagesKey]);

  // Preload adjacent images so they're cached before swipe
  useEffect(() => {
    if (total <= 1) return;
    const preload = (idx: number) => {
      const p = pages[idx];
      if (!p) return;
      const img = new Image();
      img.src = getPosterImageUrl(p.image_path);
    };
    preload((currentIdx + 1) % total);
    if (currentIdx > 0) preload(currentIdx - 1);
  }, [currentIdx, total, pages]);

  const pageHotspots = mappings.filter(
    (m) =>
      m.flyer_filename === page?.flyer_filename && m.page_no === page?.page_no
  );

  // Core slide function: two-layer slide with no React state during animation
  const slideTo = useCallback((idx: number, direction: "left" | "right") => {
    if (animatingRef.current || idx < 0 || idx >= total || idx === currentIdx) return;
    const curEl = currentRef.current;
    const nxtEl = nextRef.current;
    if (!curEl || !nxtEl) return;

    animatingRef.current = true;
    const nextPage = pages[idx];
    if (!nextPage) return;

    const nextUrl = getPosterImageUrl(nextPage.image_path);

    // Hide hotspots
    const hotspotEl = curEl.querySelector("[data-hotspots]") as HTMLElement;
    if (hotspotEl) hotspotEl.style.visibility = "hidden";

    // Preload next image, then animate
    const nxtImg = nxtEl.querySelector("img") as HTMLImageElement;
    const startAnim = () => {
      const startPos = direction === "left" ? "100%" : "-100%";
      const endPos = direction === "left" ? "-100%" : "100%";

      nxtEl.style.display = "block";
      nxtEl.style.transform = `translateX(${startPos})`;
      nxtEl.style.transition = "none";
      curEl.style.transition = "none";
      curEl.style.transform = "translateX(0)";

      // Force reflow then animate
      void nxtEl.offsetWidth;

      nxtEl.style.transition = "transform 0.3s ease";
      curEl.style.transition = "transform 0.3s ease";
      nxtEl.style.transform = "translateX(0)";
      curEl.style.transform = `translateX(${endPos})`;
    };

    // If image already cached, start immediately
    if (nxtImg.src === nextUrl && nxtImg.complete) {
      startAnim();
    } else {
      nxtImg.onload = () => startAnim();
      nxtImg.onerror = () => startAnim(); // fallback: animate even if load fails
      nxtImg.src = nextUrl;
    }

    const cleanup = () => {
      curEl.removeEventListener("transitionend", cleanup);
      // Commit: update React state, reset positions
      curEl.style.transition = "none";
      curEl.style.transform = "";
      nxtEl.style.display = "none";
      nxtEl.style.transform = "";
      nxtEl.style.transition = "";
      setCurrentIdx(idx);
      animatingRef.current = false;
    };

    curEl.addEventListener("transitionend", cleanup, { once: true });

    // Safety timeout in case transitionend doesn't fire
    setTimeout(() => {
      if (animatingRef.current) cleanup();
    }, 400);
  }, [total, currentIdx, pages]);

  const goNext = useCallback(() => slideTo((currentIdx + 1) % total, "left"), [slideTo, currentIdx, total]);
  const goPrev = useCallback(() => slideTo((currentIdx - 1 + total) % total, "right"), [slideTo, currentIdx, total]);

  // Keyboard
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goPrev();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goNext, goPrev]);

  // Swipe
  const touchState = useRef({ startX: 0, startY: 0, startTime: 0, lastX: 0, dirLocked: false, isHorizontal: false });

  const handleTouchStart = (e: React.TouchEvent) => {
    if (animatingRef.current || total <= 1) return;
    const ts = touchState.current;
    ts.startX = e.touches[0].clientX;
    ts.startY = e.touches[0].clientY;
    ts.lastX = e.touches[0].clientX;
    ts.startTime = Date.now();
    ts.dirLocked = false;
    ts.isHorizontal = false;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (animatingRef.current || total <= 1) return;
    const ts = touchState.current;
    const dx = e.touches[0].clientX - ts.startX;
    const dy = e.touches[0].clientY - ts.startY;
    ts.lastX = e.touches[0].clientX;
    if (!ts.dirLocked && (Math.abs(dx) > 4 || Math.abs(dy) > 4)) {
      ts.dirLocked = true;
      ts.isHorizontal = Math.abs(dx) > Math.abs(dy);
    }
    if (ts.isHorizontal) e.preventDefault();
  };

  const handleTouchEnd = () => {
    if (animatingRef.current || total <= 1) return;
    const ts = touchState.current;
    if (!ts.isHorizontal) return;
    const dx = ts.lastX - ts.startX;
    const elapsed = Date.now() - ts.startTime;
    const velocity = Math.abs(dx) / (elapsed || 1);
    if (Math.abs(dx) > 40 || (velocity > 0.3 && Math.abs(dx) > 15)) {
      if (dx < 0) goNext();
      else goPrev();
    }
  };

  if (!page) return null;

  const currentUrl = getPosterImageUrl(page.image_path);

  return (
    <div className="relative w-full" ref={wrapRef}>
      <div
        className="relative w-full overflow-hidden rounded-xl"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Current page */}
        <div ref={currentRef} className="relative w-full" style={{ willChange: "transform" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={currentUrl} alt={page.title || `Sayfa ${currentIdx + 1}`} className="w-full h-auto select-none" draggable={false} />
          {/* Hotspots */}
          <div className="absolute inset-0" data-hotspots>
            {pageHotspots.map((hs) => {
              const w = (hs.x1 - hs.x0) * 100;
              const h = (hs.y1 - hs.y0) * 100;
              const shorter = Math.min(w, h);
              const iconSize = Math.max(4, Math.min(8, shorter * 0.35));
              return (
                <button
                  key={hs.mapping_id}
                  onClick={() => onHotspotClick?.(hs.urun_kodu)}
                  className="absolute bg-transparent border-none cursor-pointer"
                  style={{
                    left: `${hs.x0 * 100}%`, top: `${hs.y0 * 100}%`,
                    width: `${w}%`, height: `${h}%`,
                    touchAction: "manipulation",
                    WebkitTapHighlightColor: "transparent",
                  }}
                  aria-label={`Ürün: ${hs.urun_kodu}`}
                >
                  <span
                    className="absolute bottom-0.5 right-0.5 rounded-full bg-white/75 text-gray-700 flex items-center justify-center shadow-sm"
                    style={{ width: `${iconSize}vw`, height: `${iconSize}vw`, maxWidth: "34px", maxHeight: "34px", minWidth: "16px", minHeight: "16px" }}
                  >
                    <svg className="w-[55%] h-[55%]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="10" cy="10" r="6" /><line x1="14.5" y1="14.5" x2="20" y2="20" />
                    </svg>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Next page (hidden, used during slide) */}
        <div ref={nextRef} className="absolute inset-0 w-full" style={{ display: "none", willChange: "transform" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="" alt="" className="w-full h-auto select-none" draggable={false} />
        </div>
      </div>

      {/* Navigation arrows */}
      {total > 1 && (
        <>
          <button onClick={goPrev} className="absolute left-1 top-1/2 -translate-y-1/2 w-9 h-9 bg-[rgba(30,58,95,0.85)] hover:bg-[rgba(30,58,95,1)] text-white rounded-full flex items-center justify-center shadow-md transition-colors z-10" aria-label="Önceki sayfa">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
          </button>
          <button onClick={goNext} className="absolute right-1 top-1/2 -translate-y-1/2 w-9 h-9 bg-[rgba(30,58,95,0.85)] hover:bg-[rgba(30,58,95,1)] text-white rounded-full flex items-center justify-center shadow-md transition-colors z-10" aria-label="Sonraki sayfa">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
          </button>
        </>
      )}

      {/* Page indicator */}
      {total > 1 && (
        <div className="flex flex-col items-center gap-1 mt-2">
          {total <= 20 && (
            <div className="flex gap-1.5">
              {pages.map((_, i) => (
                <button key={i} onClick={() => { if (i !== currentIdx) slideTo(i, i > currentIdx ? "left" : "right"); }}
                  className={`w-2 h-2 rounded-full transition-all ${i === currentIdx ? "bg-[#1e3a5f] scale-125" : "bg-gray-300 hover:bg-gray-400"}`}
                  aria-label={`Sayfa ${i + 1}`} />
              ))}
            </div>
          )}
          <span className="text-xs text-muted-foreground">{currentIdx + 1} / {total}</span>
        </div>
      )}
    </div>
  );
}

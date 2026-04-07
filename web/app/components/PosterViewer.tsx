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
  const wrapRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  const total = pages.length;
  const page = pages[currentIdx];

  const pageHotspots = mappings.filter(
    (m) =>
      m.flyer_filename === page?.flyer_filename && m.page_no === page?.page_no
  );

  // Refs for swipe state (no re-renders during gesture)
  const touchState = useRef({
    startX: 0,
    startY: 0,
    startTime: 0,
    isDragging: false,
    dragOffset: 0,
    dirLocked: false,
    isHorizontal: false,
    isSliding: false,
  });

  const goTo = useCallback((idx: number) => {
    if (idx < 0 || idx >= total) return;
    setCurrentIdx(idx);
  }, [total]);

  // Slide animation (3-phase like Streamlit)
  const slideTo = useCallback((idx: number) => {
    const ts = touchState.current;
    const track = trackRef.current;
    const wrap = wrapRef.current;
    if (ts.isSliding || !track || !wrap) return;
    if (idx < 0 || idx >= total || idx === currentIdx) return;

    const direction = idx > currentIdx ? -1 : 1;
    const wrapW = wrap.clientWidth;
    ts.isSliding = true;

    // Phase 1: slide out
    track.style.transition = "transform 0.3s ease";
    track.style.transform = `translateX(${direction * wrapW}px)`;

    const onEnd = () => {
      track.removeEventListener("transitionend", onEnd);
      // Phase 2: reposition off-screen, load new page
      track.style.transition = "none";
      track.style.transform = `translateX(${-direction * wrapW}px)`;
      setCurrentIdx(idx);

      // Phase 3: slide in
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          track.style.transition = "transform 0.3s ease";
          track.style.transform = "translateX(0)";
          const onEnd2 = () => {
            track.removeEventListener("transitionend", onEnd2);
            track.style.transition = "";
            track.style.transform = "";
            ts.isSliding = false;
          };
          track.addEventListener("transitionend", onEnd2);
        });
      });
    };
    track.addEventListener("transitionend", onEnd);
  }, [total, currentIdx]);

  const goNext = useCallback(() => slideTo((currentIdx + 1) % total), [slideTo, currentIdx, total]);
  const goPrev = useCallback(() => slideTo((currentIdx - 1 + total) % total), [slideTo, currentIdx, total]);

  // Keyboard
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goPrev();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goNext, goPrev]);

  // Touch handlers
  const handleTouchStart = (e: React.TouchEvent) => {
    const ts = touchState.current;
    if (ts.isSliding || total <= 1) return;
    const track = trackRef.current;
    if (!track) return;

    ts.startX = e.touches[0].clientX;
    ts.startY = e.touches[0].clientY;
    ts.startTime = Date.now();
    ts.isDragging = false;
    ts.dragOffset = 0;
    ts.dirLocked = false;
    ts.isHorizontal = false;

    track.style.transition = "";
    track.style.transform = "";
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    const ts = touchState.current;
    const track = trackRef.current;
    if (ts.isSliding || total <= 1 || !track) return;

    const dx = e.touches[0].clientX - ts.startX;
    const dy = e.touches[0].clientY - ts.startY;

    // Lock direction on first significant move
    if (!ts.dirLocked && (Math.abs(dx) > 4 || Math.abs(dy) > 4)) {
      ts.dirLocked = true;
      ts.isHorizontal = Math.abs(dx) > Math.abs(dy);
    }
    if (!ts.isHorizontal) return;

    // Prevent vertical scroll when swiping horizontally
    e.preventDefault();

    ts.isDragging = true;
    ts.dragOffset = dx;

    // Resistance at edges
    if ((currentIdx === 0 && dx > 0) || (currentIdx === total - 1 && dx < 0)) {
      ts.dragOffset = dx * 0.25;
    }

    track.style.transform = `translateX(${ts.dragOffset}px)`;
  };

  const handleTouchEnd = () => {
    const ts = touchState.current;
    const track = trackRef.current;
    const wrap = wrapRef.current;
    if (ts.isSliding || !ts.isDragging || !track || !wrap) {
      if (track) {
        track.style.transform = "";
      }
      return;
    }

    const wrapW = wrap.clientWidth;
    const threshold = wrapW * 0.08;
    const elapsed = Date.now() - ts.startTime;
    const velocity = Math.abs(ts.dragOffset) / (elapsed || 1);
    const shouldSlide = Math.abs(ts.dragOffset) > threshold || (velocity > 0.3 && Math.abs(ts.dragOffset) > 15);

    if (shouldSlide) {
      const direction = ts.dragOffset > 0 ? 1 : -1;
      const targetIdx = currentIdx - direction;

      if (targetIdx >= 0 && targetIdx < total) {
        ts.isSliding = true;

        track.style.transition = "transform 0.3s ease";
        track.style.transform = `translateX(${direction * wrapW}px)`;

        const onEnd = () => {
          track.removeEventListener("transitionend", onEnd);
          track.style.transition = "none";
          track.style.transform = `translateX(${-direction * wrapW}px)`;
          setCurrentIdx(targetIdx);

          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              track.style.transition = "transform 0.3s ease";
              track.style.transform = "translateX(0)";
              const onEnd2 = () => {
                track.removeEventListener("transitionend", onEnd2);
                track.style.transition = "";
                track.style.transform = "";
                ts.isSliding = false;
              };
              track.addEventListener("transitionend", onEnd2);
            });
          });
        };
        track.addEventListener("transitionend", onEnd);
      } else {
        snapBack(track);
      }
    } else {
      snapBack(track);
    }

    // Delay reset so hotspot click handlers can check isDragging
    setTimeout(() => { ts.isDragging = false; }, 0);
    ts.dragOffset = 0;
  };

  function snapBack(track: HTMLDivElement) {
    track.style.transition = "transform 0.3s ease";
    track.style.transform = "translateX(0)";
    const onSnap = () => {
      track.removeEventListener("transitionend", onSnap);
      track.style.transition = "";
      track.style.transform = "";
    };
    track.addEventListener("transitionend", onSnap);
  }

  if (!page) return null;

  const imageUrl = getPosterImageUrl(page.image_path);

  return (
    <div className="relative w-full" ref={wrapRef}>
      {/* Slide track — swipeable */}
      <div
        ref={trackRef}
        className="relative w-full overflow-hidden rounded-xl"
        style={{ touchAction: "pan-y", willChange: "transform" }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl}
          alt={page.title || `Sayfa ${currentIdx + 1}`}
          className="w-full h-auto select-none"
          draggable={false}
        />

        {/* Hotspots — invisible areas with magnifier in bottom-right */}
        {pageHotspots.map((hs) => {
          const w = (hs.x1 - hs.x0) * 100;
          const h = (hs.y1 - hs.y0) * 100;
          // Dynamic icon size based on hotspot dimensions (matches Streamlit)
          const shorter = Math.min(w, h);
          const iconSize = Math.max(4, Math.min(8, shorter * 0.35));

          return (
            <button
              key={hs.mapping_id}
              onClick={() => {
                if (touchState.current.isDragging || touchState.current.isSliding) return;
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
              {/* Magnifier icon — bottom-right, white semi-transparent */}
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
                  onClick={() => goTo(i)}
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
          <span className="text-xs text-gray-500">
            {currentIdx + 1} / {total}
          </span>
        </div>
      )}
    </div>
  );
}

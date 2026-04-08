"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import useEmblaCarousel from "embla-carousel-react";
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
  const [emblaRef, emblaApi] = useEmblaCarousel({
    loop: false,
    dragFree: false,
    containScroll: "trimSnaps",
  });
  const [currentIdx, setCurrentIdx] = useState(0);

  const total = pages.length;

  // Reset carousel when pages change (week switch)
  const pagesKey = pages.map((p) => p.id).join(",");
  useEffect(() => {
    if (emblaApi) {
      emblaApi.scrollTo(0, true); // instant scroll to first
      setCurrentIdx(0);
    }
  }, [pagesKey, emblaApi]);

  // Track current slide
  useEffect(() => {
    if (!emblaApi) return;
    const onSelect = () => setCurrentIdx(emblaApi.selectedScrollSnap());
    emblaApi.on("select", onSelect);
    return () => { emblaApi.off("select", onSelect); };
  }, [emblaApi]);

  const goNext = useCallback(() => emblaApi?.scrollNext(), [emblaApi]);
  const goPrev = useCallback(() => emblaApi?.scrollPrev(), [emblaApi]);
  const goTo = useCallback((idx: number) => emblaApi?.scrollTo(idx), [emblaApi]);

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") goNext();
      else if (e.key === "ArrowLeft") goPrev();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goNext, goPrev]);

  // Precompute image URLs
  const imageUrls = useMemo(
    () => pages.map((p) => getPosterImageUrl(p.image_path)),
    [pages]
  );

  // Get hotspots for a specific page
  const getPageHotspots = useCallback(
    (page: PosterPage) =>
      mappings.filter(
        (m) => m.flyer_filename === page.flyer_filename && m.page_no === page.page_no
      ),
    [mappings]
  );

  if (total === 0) return null;

  return (
    <div className="relative w-full">
      {/* Embla viewport */}
      <div className="overflow-hidden rounded-xl" ref={emblaRef}>
        <div className="flex">
          {pages.map((pg, i) => {
            const hotspots = getPageHotspots(pg);
            return (
              <div key={pg.id} className="flex-[0_0_100%] min-w-0 relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={imageUrls[i]}
                  alt={pg.title || `Sayfa ${i + 1}`}
                  className="w-full h-auto select-none"
                  draggable={false}
                  loading={i <= 1 ? "eager" : "lazy"}
                />

                {/* Hotspots — only render on current/adjacent slides for performance */}
                {Math.abs(i - currentIdx) <= 1 && hotspots.map((hs) => {
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
                        className="absolute bottom-0.5 right-0.5 rounded-full bg-white/75 text-gray-700
                                   flex items-center justify-center shadow-sm"
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
            );
          })}
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
          <span className="text-xs text-muted-foreground">
            {currentIdx + 1} / {total}
          </span>
        </div>
      )}
    </div>
  );
}

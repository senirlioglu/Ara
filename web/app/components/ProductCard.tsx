"use client";

import { useState, useMemo } from "react";
import type { ProductCard as ProductCardType, StoreStock } from "@/lib/types";
import { sortStoresByDistance, haversineKm, formatDistance } from "@/lib/distance";
import { analytics } from "@/lib/analytics";

function formatPrice(price: number): string {
  if (!price) return "";
  return (
    price.toLocaleString("tr-TR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }) + " \u20BA"
  );
}

function getStockLevel(adet: number) {
  if (adet <= 0)
    return { label: "Yok", badgeClass: "bg-gray-400 text-white", linkClass: "text-blue-600" };
  if (adet <= 2)
    return { label: "Düşük", badgeClass: "bg-red-400 text-white", linkClass: "text-blue-600" };
  if (adet <= 5)
    return { label: "Orta", badgeClass: "bg-yellow-500 text-white", linkClass: "text-red-500" };
  return { label: "Yüksek", badgeClass: "bg-green-500 text-white", linkClass: "text-red-500" };
}

function mapsUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`;
}

type SortMode = "distance" | "stock";

interface ProductCardProps {
  product: ProductCardType;
  userLat?: number | null;
  userLon?: number | null;
  locationStatus?: string;
  onRequestLocation?: () => void;
}

export default function ProductCard({
  product,
  userLat,
  userLon,
  locationStatus,
  onRequestLocation,
}: ProductCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [sortModeOverride, setSortModeOverride] = useState<SortMode | null>(null);
  const { urun_kod, urun_ad, fiyat, stoklu_magaza, toplam_stok, magazalar } = product;

  const hasStock = stoklu_magaza > 0;
  const priceStr = formatPrice(fiyat);
  const hasLocation = !!(userLat && userLon);
  const sortMode: SortMode = sortModeOverride ?? (hasLocation ? "distance" : "stock");

  const sortedMagazalar = useMemo(() => {
    if (sortMode === "distance" && hasLocation) {
      return sortStoresByDistance(magazalar, userLat!, userLon!);
    }
    return [...magazalar].sort((a, b) => b.stok_adet - a.stok_adet);
  }, [magazalar, sortMode, hasLocation, userLat, userLon]);

  const getStoreDist = (m: StoreStock): string | null => {
    if (!hasLocation || !m.latitude || !m.longitude) return null;
    const km = haversineKm(userLat!, userLon!, m.latitude, m.longitude);
    return formatDistance(km);
  };

  const handleSortClick = (mode: SortMode) => {
    if (mode === "distance" && !hasLocation) {
      if (locationStatus === "denied") {
        alert("Konum izni gerekli. Tarayıcı ayarlarından konum iznini açın.");
      } else if (onRequestLocation) {
        onRequestLocation();
      }
      return;
    }
    analytics.sortChange(mode);
    setSortModeOverride(mode);
  };

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden shadow-card">
      {/* Header */}
      <button
        onClick={() => {
          if (!expanded) analytics.productExpand(urun_kod, urun_ad);
          setExpanded(!expanded);
        }}
        className="w-full flex items-start justify-between gap-3 p-4 text-left"
      >
        <div className="flex-1 min-w-0">
          <h3 className="font-bold text-foreground text-base leading-snug mb-2">
            {urun_ad}
          </h3>
          {priceStr && (
            <span className="inline-block px-3 py-1 bg-red-500 text-white text-sm font-bold rounded-lg mb-2">
              {priceStr}
            </span>
          )}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground flex-wrap">
            <span>{urun_kod}</span>
            <span>·</span>
            <span className="font-semibold text-foreground">
              {hasStock ? `${stoklu_magaza} mağaza` : "Stokta yok"}
            </span>
            {toplam_stok > 0 && (
              <>
                <span>·</span>
                <span className="inline-flex px-2 py-0.5 bg-green-500 text-white rounded text-xs font-semibold">
                  Bölge Stok: {toplam_stok}
                </span>
              </>
            )}
          </div>
        </div>
        <div className="shrink-0 mt-1 text-muted-foreground">
          <svg
            className={`h-5 w-5 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Detail */}
      {expanded && (
        <div className="border-t border-border px-4 pb-4">
          {/* Sort controls */}
          <div className="flex items-center gap-2 py-3">
            <span className="text-xs text-muted-foreground">Sırala:</span>
            <button
              onClick={() => handleSortClick("distance")}
              className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                sortMode === "distance" && hasLocation
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted/50"
              }`}
            >
              <svg className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
              </svg>
              Yakınlık
            </button>
            <button
              onClick={() => handleSortClick("stock")}
              className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                sortMode === "stock"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted/50"
              }`}
            >
              📦 Stok
            </button>
          </div>

          {/* Store list */}
          {sortedMagazalar.length === 0 ? (
            <p className="text-sm text-destructive font-semibold">
              Bu ürün hiçbir mağazada stokta yok!
            </p>
          ) : (
            <div className="space-y-2.5">
              {sortedMagazalar.map((m) => {
                const level = getStockLevel(m.stok_adet);
                const dist = getStoreDist(m);
                return (
                  <div
                    key={m.magaza_kod}
                    className="border border-border rounded-lg p-3 bg-background"
                  >
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-bold text-sm text-foreground">
                            {m.magaza_ad || m.magaza_kod}
                          </h4>
                          {dist && (
                            <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                              {dist}
                            </span>
                          )}
                        </div>
                        {m.latitude && m.longitude && (
                          <a
                            href={mapsUrl(m.latitude, m.longitude)}
                            onClick={() => analytics.directionsClick(m.magaza_ad || "", m.magaza_kod)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className={`text-xs font-medium flex items-center gap-0.5 mt-0.5 ${level.linkClass}`}
                          >
                            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor">
                              <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
                            </svg>
                            Yol tarifi
                          </a>
                        )}
                      </div>
                      <span className={`text-xs font-bold px-2.5 py-1 rounded ${level.badgeClass}`}>
                        {level.label}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      SM: {m.sm_kod || "-"} · BS: {m.bs_kod || "-"} · {m.magaza_kod}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

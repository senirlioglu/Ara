"use client";

import { useState, useMemo } from "react";
import type { ProductCard as ProductCardType, StoreStock } from "@/lib/types";
import { sortStoresByDistance, haversineKm, formatDistance } from "@/lib/distance";

function formatPrice(price: number): string {
  if (!price) return "";
  return (
    price.toLocaleString("tr-TR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }) + " \u20BA"
  );
}

function getStockLevel(adet: number): {
  label: string;
  badgeClass: string;
  rowClass: string;
} {
  if (adet <= 0)
    return { label: "Yok", badgeClass: "bg-gray-400 text-white", rowClass: "bg-gray-50 border-gray-200" };
  if (adet <= 2)
    return { label: "Düşük", badgeClass: "bg-red-500 text-white", rowClass: "bg-red-50 border-red-200" };
  if (adet <= 5)
    return { label: "Orta", badgeClass: "bg-amber-500 text-white", rowClass: "bg-amber-200/60 border-amber-300" };
  return { label: "Yüksek", badgeClass: "bg-green-600 text-white", rowClass: "bg-green-50 border-green-200" };
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
  const [sortMode, setSortMode] = useState<SortMode>(
    userLat && userLon ? "distance" : "stock"
  );
  const { urun_kod, urun_ad, fiyat, stoklu_magaza, toplam_stok, magazalar } =
    product;

  const hasStock = stoklu_magaza > 0;
  const priceStr = formatPrice(fiyat);
  const hasLocation = !!(userLat && userLon);

  // Sort stores based on selected mode
  const sortedMagazalar = useMemo(() => {
    if (sortMode === "distance" && hasLocation) {
      return sortStoresByDistance(magazalar, userLat!, userLon!);
    }
    // Stock sort: highest first
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
    setSortMode(mode);
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-4 flex items-center gap-3 text-left active:bg-gray-50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <p className="text-base font-bold text-gray-900 leading-snug">
            {urun_ad}
          </p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {priceStr && (
              <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-extrabold text-white bg-red-600">
                {priceStr}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            <span className="text-sm text-gray-400">{urun_kod}</span>
            <span className="text-sm text-gray-300">&middot;</span>
            <span className="text-sm text-gray-600 font-medium">
              {hasStock ? `${stoklu_magaza} mağaza` : "Stokta yok"}
            </span>
            {toplam_stok > 0 && (
              <>
                <span className="text-sm text-gray-300">&middot;</span>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold text-white bg-gradient-to-r from-violet-500 to-purple-500">
                  Bölge Stok: {toplam_stok}
                </span>
              </>
            )}
          </div>
        </div>
        <svg
          className={`w-6 h-6 text-gray-400 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Detail — expandable */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-100">
          {/* Sort controls */}
          <div className="flex items-center gap-2 mt-3">
            <span className="text-xs text-gray-400 font-medium">Sırala:</span>
            <button
              onClick={() => handleSortClick("distance")}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
                sortMode === "distance" && hasLocation
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
            >
              📍 Yakınlık
            </button>
            <button
              onClick={() => handleSortClick("stock")}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${
                sortMode === "stock"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200"
              }`}
            >
              📦 Stok
            </button>
          </div>

          {/* Store list */}
          {sortedMagazalar.length === 0 ? (
            <p className="mt-4 text-base text-red-500 font-semibold">
              Bu ürün hiçbir mağazada stokta yok!
            </p>
          ) : (
            <div className="mt-3 space-y-2.5">
              {sortedMagazalar.map((m) => {
                const level = getStockLevel(m.stok_adet);
                const dist = getStoreDist(m);
                return (
                  <div
                    key={m.magaza_kod}
                    className={`flex items-center gap-3 p-3.5 rounded-xl border ${level.rowClass}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-base font-bold text-gray-900 leading-snug truncate">
                          {m.magaza_ad || m.magaza_kod}
                        </p>
                        {dist && (
                          <span className="shrink-0 text-xs text-blue-600 font-semibold bg-blue-50 px-2 py-0.5 rounded-full">
                            {dist}
                          </span>
                        )}
                      </div>
                      {m.latitude && m.longitude && (
                        <a
                          href={mapsUrl(m.latitude, m.longitude)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 mt-1 text-sm text-red-500 font-medium"
                        >
                          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
                          </svg>
                          Yol tarifi
                        </a>
                      )}
                      <p className="text-xs text-gray-500 mt-1">
                        SM: {m.sm_kod || "-"} &middot; BS: {m.bs_kod || "-"} &middot; {m.magaza_kod}
                      </p>
                    </div>
                    <span
                      className={`${level.badgeClass} text-sm font-bold px-3.5 py-1.5 rounded-full shrink-0`}
                    >
                      {level.label}
                    </span>
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

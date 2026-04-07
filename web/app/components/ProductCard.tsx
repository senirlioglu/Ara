"use client";

import { useState } from "react";
import type { ProductCard as ProductCardType } from "@/lib/types";

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
  className: string;
} {
  if (adet <= 0) return { label: "Yok", className: "stock-none" };
  if (adet <= 2) return { label: "Az", className: "stock-low" };
  if (adet <= 5) return { label: "Orta", className: "stock-medium" };
  return { label: "Yeterli", className: "stock-high" };
}

function mapsUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`;
}

export default function ProductCard({ product }: { product: ProductCardType }) {
  const [expanded, setExpanded] = useState(false);
  const { urun_kod, urun_ad, fiyat, stoklu_magaza, toplam_stok, magazalar } =
    product;

  const hasStock = stoklu_magaza > 0;
  const priceStr = formatPrice(fiyat);

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3.5 flex items-center gap-3 text-left active:bg-gray-50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">
            {urun_ad}
          </p>
          <div className="flex items-center gap-2 mt-1.5">
            {priceStr && (
              <span className="text-lg font-extrabold text-red-600">
                {priceStr}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-gray-400">{urun_kod}</span>
            <span className="text-xs text-gray-300">&middot;</span>
            <span className="text-xs text-gray-500">
              {hasStock ? `${stoklu_magaza} mağaza` : "Stokta yok"}
            </span>
            {toplam_stok > 0 && (
              <>
                <span className="text-xs text-gray-300">&middot;</span>
                <span className="text-xs text-gray-500">
                  Toplam: {toplam_stok}
                </span>
              </>
            )}
          </div>
        </div>
        <svg
          className={`w-5 h-5 text-gray-400 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
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
          {/* Store list */}
          {magazalar.length === 0 ? (
            <p className="mt-3 text-sm text-red-500 font-medium">
              Bu ürün hiçbir mağazada stokta yok!
            </p>
          ) : (
            <div className="mt-3 space-y-2">
              {magazalar.map((m) => {
                const level = getStockLevel(m.stok_adet);
                return (
                  <div
                    key={m.magaza_kod}
                    className="flex items-center gap-3 p-3 rounded-xl bg-gray-50"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-800 truncate">
                        {m.magaza_ad || m.magaza_kod}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">
                        SM: {m.sm_kod || "-"} &middot; BS: {m.bs_kod || "-"} &middot;{" "}
                        {m.magaza_kod}
                      </p>
                    </div>
                    <span
                      className={`${level.className} text-white text-xs font-bold px-2.5 py-1 rounded-full`}
                    >
                      {m.stok_adet}
                    </span>
                    {m.latitude && m.longitude && (
                      <a
                        href={mapsUrl(m.latitude, m.longitude)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-lg"
                        aria-label="Haritada göster"
                      >
                        📍
                      </a>
                    )}
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

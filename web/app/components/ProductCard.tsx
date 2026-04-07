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
  color: string;
  className: string;
} {
  if (adet <= 0) return { label: "Yok", color: "#95a5a6", className: "stock-none" };
  if (adet <= 2) return { label: "Az", color: "#e74c3c", className: "stock-low" };
  if (adet <= 5) return { label: "Orta", color: "#f39c12", className: "stock-medium" };
  return { label: "Yeterli", color: "#27ae60", className: "stock-high" };
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
        className="w-full px-4 py-3 flex items-center gap-3 text-left active:bg-gray-50 transition-colors"
      >
        <span className="text-xl">{hasStock ? "\uD83D\uDCE6" : "\u274C"}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">
            {urun_kod} &middot; {urun_ad}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            {hasStock
              ? `${stoklu_magaza} mağaza`
              : "Stokta yok"}
            {priceStr && ` \u00B7 ${priceStr}`}
          </p>
        </div>
        <svg
          className={`w-5 h-5 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`}
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
        <div className="px-4 pb-4 border-t border-gray-50">
          {/* Badges */}
          <div className="flex gap-2 mt-3 flex-wrap">
            {priceStr && (
              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold text-white bg-gradient-to-r from-emerald-500 to-teal-500">
                {priceStr}
              </span>
            )}
            {toplam_stok > 0 && (
              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold text-white bg-gradient-to-r from-violet-500 to-purple-500">
                Toplam Stok: {toplam_stok}
              </span>
            )}
          </div>

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
                    className="flex items-center gap-3 p-2.5 rounded-xl bg-gray-50"
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

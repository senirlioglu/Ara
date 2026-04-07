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
  badgeClass: string;
  rowClass: string;
} {
  if (adet <= 0)
    return { label: "Yok", badgeClass: "bg-gray-400 text-white", rowClass: "bg-gray-50 border-gray-200" };
  if (adet <= 2)
    return { label: "Az", badgeClass: "bg-red-500 text-white", rowClass: "bg-red-50 border-red-200" };
  if (adet <= 5)
    return { label: "Orta", badgeClass: "bg-amber-500 text-white", rowClass: "bg-amber-50 border-amber-200" };
  return { label: "Yüksek", badgeClass: "bg-green-600 text-white", rowClass: "bg-green-50 border-green-200" };
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
        className="w-full px-4 py-4 flex items-center gap-3 text-left active:bg-gray-50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <p className="text-base font-bold text-gray-900 leading-snug">
            {urun_ad}
          </p>
          {priceStr && (
            <p className="text-xl font-extrabold text-red-600 mt-1">
              {priceStr}
            </p>
          )}
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-sm text-gray-400">{urun_kod}</span>
            <span className="text-sm text-gray-300">&middot;</span>
            <span className="text-sm text-gray-600 font-medium">
              {hasStock ? `${stoklu_magaza} mağaza` : "Stokta yok"}
            </span>
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
          {/* Badges row */}
          <div className="flex gap-2.5 mt-3 flex-wrap">
            {priceStr && (
              <span className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-bold text-white bg-gradient-to-r from-emerald-500 to-teal-500">
                {priceStr}
              </span>
            )}
            {toplam_stok > 0 && (
              <span className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-bold text-white bg-gradient-to-r from-violet-500 to-purple-500">
                Toplam Bölge Stok: {toplam_stok}
              </span>
            )}
          </div>

          {/* Store list */}
          {magazalar.length === 0 ? (
            <p className="mt-4 text-base text-red-500 font-semibold">
              Bu ürün hiçbir mağazada stokta yok!
            </p>
          ) : (
            <div className="mt-4 space-y-2.5">
              {magazalar.map((m) => {
                const level = getStockLevel(m.stok_adet);
                return (
                  <div
                    key={m.magaza_kod}
                    className={`flex items-center gap-3 p-3.5 rounded-xl border ${level.rowClass}`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-base font-bold text-gray-900 leading-snug">
                        {m.magaza_ad || m.magaza_kod}
                      </p>
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

"use client";

import { useEffect, useState } from "react";
import { getProductStores } from "@/lib/api";
import { productImageUrl } from "@/lib/supabase";
import { formatPrice } from "@/lib/format";
import type { HalkgunuProductStore } from "@/lib/types";

interface Props {
  eventId: string;
  urunKod: string | null;
  onClose: () => void;
}

export function StoreModal({ eventId, urunKod, onClose }: Props) {
  const [stores, setStores] = useState<HalkgunuProductStore[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    if (!urunKod) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setImgError(false);
    getProductStores(eventId, urunKod)
      .then((rows) => {
        if (!cancelled) setStores(rows);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [eventId, urunKod]);

  if (!urunKod) return null;

  // Mağaza kartı renkleri (Ara'daki seviye renkleriyle uyumlu paleti)
  const colors = ["#22c55e", "#3b82f6", "#f59e0b", "#ec4899"];

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-card shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start gap-3 p-4 border-b border-slate-200">
          <div className="w-20 h-20 shrink-0 bg-slate-100 rounded-md overflow-hidden">
            {imgError ? (
              <div className="w-full h-full flex items-center justify-center text-xs text-ink-500">
                Resim yok
              </div>
            ) : (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={productImageUrl(urunKod)}
                alt={urunKod}
                className="w-full h-full object-contain p-1"
                onError={() => setImgError(true)}
              />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-mono text-ink-500">{urunKod}</div>
            <div className="text-base font-semibold text-ink-900">
              İndirimli Mağazalar
            </div>
            {!loading && stores.length > 0 && (
              <div className="text-xs text-ink-500 mt-1">
                {stores.length} mağazada mevcut
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-ink-500 hover:text-ink-900 text-xl leading-none px-2"
            aria-label="Kapat"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading && <div className="text-center text-ink-500 py-6">Yükleniyor…</div>}
          {error && <div className="text-center text-rose-600 py-6">Hata: {error}</div>}
          {!loading && !error && stores.length === 0 && (
            <div className="text-center text-ink-500 py-6">
              Bu ürün için indirimli mağaza bulunamadı.
            </div>
          )}
          {!loading &&
            !error &&
            stores.map((s, i) => {
              const color = colors[i % colors.length];
              return (
                <div
                  key={s.magaza_kod}
                  className="store-card"
                  style={{
                    borderLeftColor: color,
                    background: `linear-gradient(135deg, ${color}22 0%, ${color}11 100%)`,
                  }}
                >
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-ink-900 flex items-center gap-2 flex-wrap">
                      <span>{s.magaza_adi ?? s.magaza_kod}</span>
                      {s.latitude != null && s.longitude != null && (
                        <a
                          href={`https://www.google.com/maps?q=${s.latitude},${s.longitude}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 hover:bg-indigo-100 no-underline"
                        >
                          📍 Yol tarifi
                        </a>
                      )}
                    </div>
                    {s.adres && (
                      <div className="text-xs text-ink-500 mt-1 line-clamp-2">
                        {s.adres}
                      </div>
                    )}
                    <div className="text-xs text-ink-500 mt-1 font-mono">
                      {s.magaza_kod} · stok {s.stok_adet}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-base font-bold text-rose-600">
                      {formatPrice(s.indirimli_fiyat)}
                    </div>
                    {s.normal_fiyat != null &&
                      s.indirimli_fiyat != null &&
                      s.normal_fiyat > s.indirimli_fiyat && (
                        <div className="text-xs text-ink-500 line-through">
                          {formatPrice(s.normal_fiyat)}
                        </div>
                      )}
                  </div>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}

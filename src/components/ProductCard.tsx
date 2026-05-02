"use client";

import { useState } from "react";
import type { HalkgunuProductSummary } from "@/lib/types";
import { productImageUrl } from "@/lib/supabase";
import { discountPercent, formatPrice } from "@/lib/format";

interface Props {
  product: HalkgunuProductSummary;
  onClick: (urunKod: string) => void;
}

export function ProductCard({ product, onClick }: Props) {
  const [imgError, setImgError] = useState(false);
  const url = productImageUrl(product.urun_kod);
  const indirim = discountPercent(product.max_normal, product.min_indirimli);

  return (
    <button
      type="button"
      onClick={() => onClick(product.urun_kod)}
      className="text-left bg-white rounded-card border border-slate-200 hover:border-brand-start hover:shadow-md transition overflow-hidden group"
    >
      <div className="aspect-square bg-slate-100 relative">
        {imgError ? (
          <div className="absolute inset-0 flex items-center justify-center text-ink-500 text-xs">
            Resim yok
          </div>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={url}
            alt={product.urun_ad ?? product.urun_kod}
            className="absolute inset-0 w-full h-full object-contain p-2"
            onError={() => setImgError(true)}
            loading="lazy"
          />
        )}
        {indirim != null && (
          <div className="absolute top-2 right-2 bg-rose-600 text-white text-xs font-bold px-2 py-1 rounded-full shadow">
            %{indirim}
          </div>
        )}
      </div>
      <div className="p-3">
        <div className="text-xs text-ink-500 font-mono">{product.urun_kod}</div>
        <div className="text-sm font-medium text-ink-900 line-clamp-2 min-h-[2.5rem]">
          {product.urun_ad ?? "—"}
        </div>
        <div className="mt-2 flex items-baseline gap-2">
          <span className="text-base font-bold text-rose-600">
            {formatPrice(product.min_indirimli)}
          </span>
          {product.max_normal != null && product.max_normal > (product.min_indirimli ?? 0) && (
            <span className="text-xs text-ink-500 line-through">
              {formatPrice(product.max_normal)}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

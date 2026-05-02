"use client";

import { useEffect, useMemo, useState } from "react";
import { listEventProductSummary } from "@/lib/api";
import type { HalkgunuProductSummary } from "@/lib/types";
import { ProductCard } from "./ProductCard";

interface Props {
  eventId: string;
  onProductClick: (urunKod: string) => void;
}

export function ListView({ eventId, onProductClick }: Props) {
  const [products, setProducts] = useState<HalkgunuProductSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listEventProductSummary(eventId)
      .then((rows) => {
        if (!cancelled) setProducts(rows);
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
  }, [eventId]);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr");
    if (!q) return products;
    return products.filter(
      (p) =>
        p.urun_kod.toLocaleLowerCase("tr").includes(q) ||
        (p.urun_ad ?? "").toLocaleLowerCase("tr").includes(q),
    );
  }, [query, products]);

  if (loading) {
    return <div className="text-center py-10 text-ink-500">Yükleniyor…</div>;
  }
  if (error) {
    return <div className="text-center py-10 text-rose-600">Hata: {error}</div>;
  }
  if (products.length === 0) {
    return (
      <div className="text-center py-10 text-ink-500">
        Bu etkinlik için ürün listesi henüz hazır değil.
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ürün adı veya kodu ara…"
          className="w-full rounded-card border border-slate-200 px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-start"
        />
      </div>
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        {filtered.map((p) => (
          <ProductCard key={p.urun_kod} product={p} onClick={onProductClick} />
        ))}
      </div>
      {filtered.length === 0 && (
        <div className="text-center py-6 text-ink-500">Sonuç yok.</div>
      )}
    </div>
  );
}

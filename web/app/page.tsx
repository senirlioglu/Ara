"use client";

import { useState, useEffect, useCallback } from "react";
import SearchBar from "./components/SearchBar";
import ProductCard from "./components/ProductCard";
import PosterViewer from "./components/PosterViewer";
import {
  searchProducts,
  getPopularTerms,
  getPublishedWeeks,
  getPosterPages,
  getMappingsForWeek,
  logSearch,
} from "@/lib/api";
import type { ProductCard as ProductCardType } from "@/lib/types";
import type { PosterWeek, PosterPage, Hotspot } from "@/lib/types";

export default function Home() {
  // Search state
  const [results, setResults] = useState<ProductCardType[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [popularTerms, setPopularTerms] = useState<string[]>([]);

  // Poster state
  const [weeks, setWeeks] = useState<PosterWeek[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string>("");
  const [posterPages, setPosterPages] = useState<PosterPage[]>([]);
  const [mappings, setMappings] = useState<Hotspot[]>([]);

  // Load popular terms + weeks on mount
  useEffect(() => {
    getPopularTerms().then(setPopularTerms);
    getPublishedWeeks().then((w) => {
      setWeeks(w);
      if (w.length > 0) setSelectedWeek(w[0].week_id);
    });
  }, []);

  // Load poster pages when week changes
  useEffect(() => {
    if (!selectedWeek) return;
    Promise.all([
      getPosterPages(selectedWeek),
      getMappingsForWeek(selectedWeek),
    ]).then(([pages, maps]) => {
      setPosterPages(pages);
      setMappings(maps);
    });
  }, [selectedWeek]);

  const handleSearch = useCallback(async (query: string) => {
    setLoading(true);
    setSearchError("");
    setSearched(true);
    try {
      const products = await searchProducts(query);
      setResults(products);
      // Log in background
      const count = products.length;
      logSearch(query, count);
    } catch {
      setSearchError("Arama sırasında bir hata oluştu. Lütfen tekrar deneyin.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleHotspotClick = useCallback(
    (urunKodu: string) => {
      if (urunKodu) handleSearch(urunKodu);
    },
    [handleSearch]
  );

  return (
    <div className="flex flex-col min-h-full">
      {/* Header */}
      <header className="bg-gradient-to-r from-primary to-primary-dark px-4 py-4 shadow-md">
        <h1 className="text-xl font-bold text-white text-center">
          Ürün Ara
        </h1>
      </header>

      <main className="flex-1 px-4 py-4 max-w-2xl mx-auto w-full space-y-5">
        {/* Search */}
        <SearchBar
          onSearch={handleSearch}
          loading={loading}
          popularTerms={popularTerms}
        />

        {/* Results */}
        {searched && !loading && (
          <>
            {searchError && (
              <p className="text-sm text-red-500 font-medium">{searchError}</p>
            )}
            {!searchError && results.length === 0 && (
              <p className="text-sm text-gray-500 text-center py-4">
                Sonuç bulunamadı.
              </p>
            )}
            {results.length > 0 && (
              <div>
                <p className="text-sm text-gray-500 mb-3">
                  <strong>{results.length}</strong> ürün bulundu
                </p>
                <div className="space-y-3">
                  {results.slice(0, 40).map((p) => (
                    <ProductCard key={p.urun_kod} product={p} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* Poster section */}
        {weeks.length > 0 && (
          <section>
            <h2 className="text-lg font-bold text-gray-800 mb-3">
              Haftalık Broşür
            </h2>

            {/* Week selector pills */}
            <div className="flex gap-2 overflow-x-auto pb-2 mb-3 scrollbar-hide">
              {weeks.map((w) => (
                <button
                  key={w.week_id}
                  onClick={() => setSelectedWeek(w.week_id)}
                  className={`shrink-0 px-4 py-2 rounded-full text-sm font-semibold transition-all
                    ${
                      selectedWeek === w.week_id
                        ? "bg-gradient-to-r from-amber-400 to-orange-400 text-white shadow-sm"
                        : "bg-white border border-gray-200 text-gray-600 hover:border-amber-300"
                    }`}
                >
                  {w.week_name}
                </button>
              ))}
            </div>

            {/* Poster viewer */}
            {posterPages.length > 0 && (
              <PosterViewer
                pages={posterPages}
                mappings={mappings}
                onHotspotClick={handleHotspotClick}
              />
            )}
          </section>
        )}
      </main>
    </div>
  );
}

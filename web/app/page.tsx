"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import SearchBar from "./components/SearchBar";
import ProductCard from "./components/ProductCard";
import PosterViewer from "./components/PosterViewer";
import BarcodeScanner from "./components/BarcodeScanner";
import LocationBanner from "./components/LocationBanner";
import { useLocation } from "./components/LocationProvider";
import {
  searchProducts,
  searchByBarcode,
  getPopularTerms,
  getPublishedWeeks,
  getPosterPages,
  getMappingsForWeek,
  logSearch,
} from "@/lib/api";
import type { ProductCard as ProductCardType } from "@/lib/types";
import type { PosterWeek, PosterPage, Hotspot } from "@/lib/types";

export default function Home() {
  const { lat, lon, status, requestLocation, acceptAndRequest } = useLocation();

  // Search state
  const [results, setResults] = useState<ProductCardType[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [popularTerms, setPopularTerms] = useState<string[]>([]);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [lastBarcode, setLastBarcode] = useState("");

  // Poster state
  const [weeks, setWeeks] = useState<PosterWeek[]>([]);
  const [selectedWeek, setSelectedWeek] = useState<string>("");
  const [posterPages, setPosterPages] = useState<PosterPage[]>([]);
  const [mappings, setMappings] = useState<Hotspot[]>([]);

  // Track if we've already asked for location this session
  const locationRequested = useRef(false);

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

  // Request location on first search (if not already decided)
  const maybeRequestLocation = useCallback(() => {
    if (locationRequested.current) return;
    if (status === "idle") {
      locationRequested.current = true;
      requestLocation();
    }
  }, [status, requestLocation]);

  const handleSearch = useCallback(async (query: string) => {
    setLoading(true);
    setSearchError("");
    setSearched(true);
    setLastBarcode("");
    maybeRequestLocation();
    try {
      const isBarcode = /^\d{8,14}$/.test(query.trim()) && query.trim().length >= 8;
      let products: ProductCardType[];

      if (isBarcode) {
        products = await searchByBarcode(query.trim());
        if (products.length === 0) {
          products = await searchProducts(query);
        }
      } else {
        products = await searchProducts(query);
      }

      setResults(products);
      logSearch(query, products.length);
    } catch {
      setSearchError("Arama sırasında bir hata oluştu. Lütfen tekrar deneyin.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [maybeRequestLocation]);

  const handleBarcodeScan = useCallback(
    (barcode: string) => {
      setScannerOpen(false);
      setLastBarcode(barcode);
      handleSearch(barcode);
    },
    [handleSearch]
  );

  const handleHotspotClick = useCallback(
    (urunKodu: string) => {
      if (urunKodu) handleSearch(urunKodu);
    },
    [handleSearch]
  );

  // When user clicks "Evet" on our banner → trigger browser geolocation
  const handleLocationAccept = useCallback(() => {
    acceptAndRequest();
  }, [acceptAndRequest]);

  return (
    <div className="flex flex-col min-h-full">
      {/* Barcode scanner modal */}
      {scannerOpen && (
        <BarcodeScanner
          onScan={handleBarcodeScan}
          onClose={() => setScannerOpen(false)}
        />
      )}

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
          onBarcodeClick={() => {
            maybeRequestLocation();
            setScannerOpen(true);
          }}
          loading={loading}
          popularTerms={popularTerms}
        />

        {/* Location permission banner */}
        <LocationBanner onAccept={handleLocationAccept} />

        {/* Barcode info */}
        {lastBarcode && (
          <p className="text-xs text-gray-400">
            Barkod: {lastBarcode}
          </p>
        )}

        {/* Results */}
        {searched && !loading && (
          <>
            {searchError && (
              <p className="text-sm text-red-500 font-medium">{searchError}</p>
            )}
            {!searchError && results.length === 0 && (
              <p className="text-sm text-gray-500 text-center py-4">
                {lastBarcode
                  ? "Bu barkod ile eşleşen ürün bulunamadı."
                  : "Sonuç bulunamadı."}
              </p>
            )}
            {results.length > 0 && (
              <div>
                <p className="text-sm text-gray-500 mb-3">
                  <strong>{results.length}</strong> ürün bulundu
                  {lat && lon && (
                    <span className="text-blue-500 ml-1">
                      · 📍 Yakınına göre sıralı
                    </span>
                  )}
                </p>
                <div className="space-y-3">
                  {results.slice(0, 40).map((p) => (
                    <ProductCard
                      key={p.urun_kod}
                      product={p}
                      userLat={lat}
                      userLon={lon}
                    />
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

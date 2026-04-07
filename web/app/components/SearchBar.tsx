"use client";

import { useState, useRef, useEffect } from "react";

interface SearchBarProps {
  onSearch: (query: string) => void;
  onBarcodeClick?: () => void;
  loading?: boolean;
  popularTerms?: string[];
}

export default function SearchBar({
  onSearch,
  onBarcodeClick,
  loading,
  popularTerms = [],
}: SearchBarProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-focus on mount (important for kiosk barcode scanners)
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) onSearch(query.trim());
  };

  const handlePopularClick = (term: string) => {
    setQuery(term);
    onSearch(term);
  };

  return (
    <div className="w-full">
      {/* Search bar — mobile: barcode icon inside, desktop: separate button below */}
      <form onSubmit={handleSubmit}>
        {/* Search input with inline icons */}
        <div className="relative flex items-center">
          {/* Search icon (left) */}
          <svg
            className="absolute left-4 w-5 h-5 text-gray-400 pointer-events-none"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>

          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ürün adı, kodu veya barkod..."
            className="w-full pl-12 pr-24 py-3.5 rounded-2xl border border-gray-200 bg-white text-base
                       focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary
                       placeholder:text-gray-400 shadow-sm"
            autoComplete="off"
            enterKeyHint="search"
          />

          {/* Right side buttons inside the input */}
          <div className="absolute right-2 flex items-center gap-1">
            {/* Barcode icon — mobile only (inside input) */}
            <button
              type="button"
              onClick={onBarcodeClick}
              className="md:hidden p-2 rounded-xl hover:bg-gray-100 active:scale-90 transition-all"
              aria-label="Barkod tara"
            >
              <svg className="w-6 h-6 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" d="M3 7V5a2 2 0 012-2h2M17 3h2a2 2 0 012 2v2M3 17v2a2 2 0 002 2h2M17 21h2a2 2 0 002-2v-2" />
                <path strokeLinecap="round" d="M7 8v8M10 8v8M13 8v8M16 8v8" strokeWidth={1.5} />
              </svg>
            </button>

            {/* Search button (inside input) */}
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="px-4 py-2 bg-gradient-to-r from-primary to-primary-dark text-white
                         rounded-xl font-semibold text-sm
                         disabled:opacity-40 active:scale-95 transition-transform"
            >
              {loading ? (
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                "Ara"
              )}
            </button>
          </div>
        </div>

        {/* Desktop: large barcode button below search (for kiosk) */}
        <button
          type="button"
          onClick={onBarcodeClick}
          className="hidden md:flex w-full mt-3 items-center justify-center gap-3 px-6 py-4
                     bg-white border-2 border-dashed border-gray-300 rounded-2xl
                     hover:border-red-400 hover:bg-red-50/50 active:scale-[0.98]
                     transition-all group cursor-pointer"
          aria-label="Barkod tara"
        >
          <svg className="w-7 h-7 text-red-500 group-hover:scale-110 transition-transform" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" d="M3 7V5a2 2 0 012-2h2M17 3h2a2 2 0 012 2v2M3 17v2a2 2 0 002 2h2M17 21h2a2 2 0 002-2v-2" />
            <path strokeLinecap="round" d="M7 8v8M10 8v8M13 8v8M16 8v8" strokeWidth={1.5} />
          </svg>
          <span className="text-base font-semibold text-gray-600 group-hover:text-red-600 transition-colors">
            Barkod ile Ara
          </span>
        </button>
      </form>

      {/* Popular terms */}
      {popularTerms.length > 0 && (
        <div className="mt-4">
          <p className="text-sm font-semibold text-gray-500 mb-2">
            Popüler Aramalar
          </p>
          <div className="flex gap-2.5 overflow-x-auto pb-2 scrollbar-hide">
            {popularTerms.map((term) => (
              <button
                key={term}
                onClick={() => handlePopularClick(term)}
                className="shrink-0 px-4 py-2 bg-white border border-gray-200 rounded-full
                           text-sm text-gray-700 font-medium
                           hover:bg-primary/5 hover:border-primary/30
                           active:scale-95 transition-all shadow-sm"
              >
                {term}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

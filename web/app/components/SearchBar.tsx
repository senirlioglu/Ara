"use client";

import { useState, useRef, useEffect } from "react";

interface SearchBarProps {
  onSearch: (query: string) => void;
  loading?: boolean;
  popularTerms?: string[];
}

export default function SearchBar({
  onSearch,
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
      {/* Search form */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ürün adı veya kodu..."
          className="flex-1 px-4 py-3 rounded-xl border border-gray-200 bg-white text-base
                     focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary
                     placeholder:text-gray-400"
          autoComplete="off"
          enterKeyHint="search"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-5 py-3 bg-gradient-to-r from-primary to-primary-dark text-white
                     rounded-xl font-semibold text-base
                     disabled:opacity-50 active:scale-95 transition-transform"
        >
          {loading ? (
            <span className="inline-block w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            "Ara"
          )}
        </button>
      </form>

      {/* Popular terms */}
      {popularTerms.length > 0 && (
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
          {popularTerms.map((term) => (
            <button
              key={term}
              onClick={() => handlePopularClick(term)}
              className="shrink-0 px-3 py-1.5 bg-white border border-gray-200 rounded-full
                         text-sm text-gray-600 hover:bg-primary/5 hover:border-primary/30
                         active:scale-95 transition-all"
            >
              {term}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

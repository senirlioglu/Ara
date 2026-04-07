"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { normalizeTurkish } from "@/lib/turkish";

interface SearchBarProps {
  onSearch: (query: string) => void;
  onBarcodeClick?: () => void;
  loading?: boolean;
  popularTerms?: string[];
}

/** Load and cache the suggestion list */
let cachedList: string[] | null = null;
async function loadSuggestions(): Promise<string[]> {
  if (cachedList) return cachedList;
  try {
    const res = await fetch("/oneri_listesi.json");
    cachedList = await res.json();
    return cachedList!;
  } catch {
    return [];
  }
}

export default function SearchBar({
  onSearch,
  onBarcodeClick,
  loading,
  popularTerms = [],
}: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [allItems, setAllItems] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Load suggestion list on mount
  useEffect(() => {
    loadSuggestions().then(setAllItems);
  }, []);

  // Auto-focus on mount (important for kiosk barcode scanners)
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Close suggestions on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Pre-normalize all items for fast search
  const normalizedItems = useMemo(() => {
    return allItems.map((item) => ({
      original: item,
      normalized: normalizeTurkish(item),
    }));
  }, [allItems]);

  // Filter suggestions when query changes
  const filterSuggestions = useCallback(
    (q: string) => {
      if (!q || q.length < 2 || normalizedItems.length === 0) {
        setSuggestions([]);
        setShowSuggestions(false);
        return;
      }

      const normalized = normalizeTurkish(q);
      const words = normalized.split(/\s+/).filter(Boolean);

      const matches = normalizedItems
        .filter((item) => words.every((w) => item.normalized.includes(w)))
        .slice(0, 8)
        .map((item) => item.original);

      setSuggestions(matches);
      setShowSuggestions(matches.length > 0);
      setSelectedIdx(-1);
    },
    [normalizedItems]
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    filterSuggestions(val);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      setShowSuggestions(false);
      onSearch(query.trim());
    }
  };

  const handleSuggestionClick = (suggestion: string) => {
    setQuery(suggestion);
    setShowSuggestions(false);
    onSearch(suggestion);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions || suggestions.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((prev) => (prev + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((prev) => (prev - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === "Enter" && selectedIdx >= 0) {
      e.preventDefault();
      handleSuggestionClick(suggestions[selectedIdx]);
    } else if (e.key === "Escape") {
      setShowSuggestions(false);
    }
  };

  const handlePopularClick = (term: string) => {
    setQuery(term);
    setShowSuggestions(false);
    onSearch(term);
  };

  return (
    <div className="w-full" ref={wrapperRef}>
      {/* Search bar */}
      <form onSubmit={handleSubmit}>
        {/* Search input with inline icons */}
        <div className="relative">
          {/* Search icon (left) */}
          <svg
            className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>

          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              if (suggestions.length > 0) setShowSuggestions(true);
            }}
            placeholder="Ürün adı, kodu veya barkod..."
            className="w-full pl-12 pr-24 py-3.5 rounded-2xl border border-gray-200 bg-white text-base
                       focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary
                       placeholder:text-gray-400 shadow-sm"
            autoComplete="off"
            enterKeyHint="search"
            role="combobox"
            aria-expanded={showSuggestions}
            aria-autocomplete="list"
          />

          {/* Right side buttons inside the input */}
          <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
            {/* Mobile: barcode icon when empty, clear (X) button when typing */}
            {query.trim() ? (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setSuggestions([]);
                  setShowSuggestions(false);
                  inputRef.current?.focus();
                }}
                className="md:hidden p-2 rounded-xl hover:bg-gray-100 active:scale-90 transition-all"
                aria-label="Temizle"
              >
                <svg className="w-5 h-5 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            ) : (
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
            )}

            {/* Search button */}
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

          {/* Autocomplete dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <ul
              className="absolute z-50 left-0 right-0 top-full mt-1 bg-white border border-gray-200
                         rounded-2xl shadow-lg overflow-hidden max-h-80 overflow-y-auto"
              role="listbox"
            >
              {suggestions.map((s, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => handleSuggestionClick(s)}
                    onMouseEnter={() => setSelectedIdx(i)}
                    className={`w-full text-left px-4 py-3 text-sm border-b border-gray-50 last:border-0
                               transition-colors ${
                                 i === selectedIdx
                                   ? "bg-primary/5 text-primary"
                                   : "text-gray-700 hover:bg-gray-50"
                               }`}
                    role="option"
                    aria-selected={i === selectedIdx}
                  >
                    {s}
                  </button>
                </li>
              ))}
            </ul>
          )}
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
            ⭐ Popüler Aramalar
          </p>
          <div className="flex gap-2.5 overflow-x-auto md:overflow-visible md:flex-wrap pb-2 scrollbar-hide">
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

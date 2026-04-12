"use client";

import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { normalizeTurkish } from "@/lib/turkish";
import { analytics } from "@/lib/analytics";

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

  useEffect(() => {
    loadSuggestions().then(setAllItems);
  }, []);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const normalizedItems = useMemo(() => {
    return allItems.map((item) => ({
      original: item,
      normalized: normalizeTurkish(item),
    }));
  }, [allItems]);

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
    analytics.popularSearch(term);
    setQuery(term);
    setShowSuggestions(false);
    onSearch(term);
  };

  return (
    <div className="w-full max-w-2xl mx-auto" ref={wrapperRef}>
      {/* Search bar */}
      <form onSubmit={handleSubmit}>
        <div className="relative">
          <div className="flex items-center bg-card rounded-xl shadow-search border border-border/50 overflow-hidden">
            {/* Search icon */}
            <svg className="ml-3.5 h-5 w-5 text-muted-foreground shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
              className="flex-1 px-3 py-3.5 bg-transparent text-foreground placeholder:text-muted-foreground outline-none text-sm"
              autoComplete="off"
              enterKeyHint="search"
              role="combobox"
              aria-expanded={showSuggestions}
              aria-autocomplete="list"
            />

            {/* Right icons: barcode/clear + search button */}
            {query.trim() ? (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setSuggestions([]);
                  setShowSuggestions(false);
                  inputRef.current?.focus();
                }}
                className="p-2 text-muted-foreground hover:text-foreground transition-colors"
                aria-label="Temizle"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            ) : (
              <button
                type="button"
                onClick={onBarcodeClick}
                className="p-2 text-muted-foreground hover:text-primary transition-colors"
                aria-label="Barkod tara"
              >
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
                  <path strokeLinecap="round" d="M3 7V5a2 2 0 012-2h2M17 3h2a2 2 0 012 2v2M3 17v2a2 2 0 002 2h2M17 21h2a2 2 0 002-2v-2" />
                  <path strokeLinecap="round" d="M7 8v8M10 8v8M13 8v8M16 8v8" strokeWidth={1.5} />
                </svg>
              </button>
            )}

            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="px-5 py-2 mr-1.5 bg-primary/20 text-primary rounded-lg font-semibold text-sm
                         hover:bg-primary/30 transition-colors disabled:opacity-40"
            >
              {loading ? (
                <span className="inline-block w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
              ) : (
                "Ara"
              )}
            </button>
          </div>

          {/* Autocomplete dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <ul
              className="absolute z-50 left-0 right-0 top-full mt-1 bg-card border border-border
                         rounded-xl shadow-hover overflow-hidden max-h-80 overflow-y-auto"
              role="listbox"
            >
              {suggestions.map((s, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => handleSuggestionClick(s)}
                    onMouseEnter={() => setSelectedIdx(i)}
                    className={`w-full text-left px-4 py-3 text-sm border-b border-border/50 last:border-0
                               transition-colors ${
                                 i === selectedIdx
                                   ? "bg-primary/5 text-primary"
                                   : "text-foreground hover:bg-muted/50"
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

        {/* Desktop: large barcode button */}
        <button
          type="button"
          onClick={onBarcodeClick}
          className="hidden md:flex w-full mt-3 items-center justify-center gap-3 px-6 py-4
                     bg-card border-2 border-dashed border-border rounded-xl
                     hover:border-primary/40 active:scale-[0.98]
                     transition-all group cursor-pointer shadow-card"
          aria-label="Barkod tara"
        >
          <svg className="w-7 h-7 text-primary group-hover:scale-110 transition-transform" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" d="M3 7V5a2 2 0 012-2h2M17 3h2a2 2 0 012 2v2M3 17v2a2 2 0 002 2h2M17 21h2a2 2 0 002-2v-2" />
            <path strokeLinecap="round" d="M7 8v8M10 8v8M13 8v8M16 8v8" strokeWidth={1.5} />
          </svg>
          <span className="text-base font-semibold text-muted-foreground group-hover:text-primary transition-colors">
            Barkod ile Ara
          </span>
        </button>
      </form>

      {/* Popular terms */}
      {popularTerms.length > 0 && (
        <div className="mt-4">
          <h2 className="text-sm font-bold text-foreground mb-2.5 px-1">
            ⭐ Popüler Aramalar
          </h2>
          <div
            className="flex gap-2 overflow-x-auto md:overflow-visible md:flex-wrap scrollbar-hide pb-1 -mx-1 px-1"
            style={{ WebkitOverflowScrolling: "touch" } as React.CSSProperties}
          >
            {popularTerms.map((term) => (
              <button
                key={term}
                onClick={() => handlePopularClick(term)}
                className="shrink-0 px-3.5 py-2 bg-card border border-border rounded-lg
                           text-sm text-foreground font-medium
                           hover:border-primary/40 active:scale-95
                           transition-all whitespace-nowrap"
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

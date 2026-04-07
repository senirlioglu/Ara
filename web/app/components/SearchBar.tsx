import { Search, ScanBarcode } from "lucide-react";
import { useState, useEffect } from "react";

interface SearchBarProps {
  onSearch: (query: string) => void;
  initialQuery?: string;
}

const SearchBar = ({ onSearch, initialQuery = "" }: SearchBarProps) => {
  const [query, setQuery] = useState(initialQuery);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      onSearch(query.trim());
    }
  };

  return (
    <form onSubmit={handleSearch} className="w-full max-w-2xl mx-auto">
      <div className="flex items-center bg-card rounded-xl shadow-search border border-border/50 overflow-hidden">
        <Search className="ml-3.5 h-5 w-5 text-muted-foreground shrink-0" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ürün adı, kodu veya barkod..."
          className="flex-1 px-3 py-3.5 bg-transparent text-foreground placeholder:text-muted-foreground outline-none text-sm"
        />
        <button type="button" className="p-2 text-muted-foreground hover:text-primary transition-colors">
          <ScanBarcode className="h-5 w-5" />
        </button>
        <button
          type="submit"
          className="px-5 py-2 mr-1.5 bg-primary/20 text-primary rounded-lg font-semibold text-sm hover:bg-primary/30 transition-colors"
        >
          Ara
        </button>
      </div>
    </form>
  );
};

export default SearchBar;

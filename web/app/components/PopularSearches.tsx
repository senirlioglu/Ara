import { useRef } from "react";

interface PopularSearchesProps {
  onSearch: (term: string) => void;
}

const popularSearches = [
  '"tv 50'\'' 50uv2363dt vidaa toshiba"',
  '"tv 50'\'' 50uv2363dt vidaa"',
  '"kuruyemiş keyifli mix 330 g"',
  '"elektrikli çay seti stm-5840"',
  '"katlanabilir kamp koltuğu"',
  '"samsung telefon 5g"',
];

const PopularSearches = ({ onSearch }: PopularSearchesProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <section className="w-full max-w-2xl mx-auto">
      <h2 className="text-sm font-bold text-foreground mb-2.5 px-1">
        Popüler Aramalar
      </h2>
      <div
        ref={scrollRef}
        className="flex gap-2 overflow-x-auto scrollbar-hide pb-1 -mx-1 px-1"
        style={{ WebkitOverflowScrolling: "touch" }}
      >
        {popularSearches.map((term, i) => (
          <button
            key={i}
            onClick={() => onSearch(term.replace(/"/g, ""))}
            className="shrink-0 px-3.5 py-2 bg-card border border-border rounded-lg text-sm text-foreground hover:border-primary/40 transition-all whitespace-nowrap"
          >
            {term}
          </button>
        ))}
      </div>
    </section>
  );
};

export default PopularSearches;

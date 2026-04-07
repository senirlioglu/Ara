import { useState } from "react";

const brochures = [
  { title: "2 Nisan Aldın Aldın", active: true, image: "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?w=600&h=400&fit=crop" },
  { title: "26 Mart Aldın Aldın", active: false, image: "https://images.unsplash.com/photo-1607082349566-187342175e2f?w=600&h=400&fit=crop" },
];

const WeeklyBrochures = () => {
  const [activeIndex, setActiveIndex] = useState(0);

  return (
    <section className="w-full max-w-2xl mx-auto">
      <h2 className="text-lg font-bold text-foreground mb-3">Haftalık Broşür</h2>
      <div className="flex gap-2 mb-4">
        {brochures.map((b, i) => (
          <button
            key={i}
            onClick={() => setActiveIndex(i)}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
              i === activeIndex
                ? "bg-red-500 text-white"
                : "bg-card border border-border text-foreground hover:border-primary/40"
            }`}
          >
            {b.title}
          </button>
        ))}
      </div>
      <div className="rounded-xl overflow-hidden border border-border shadow-card">
        <img
          src={brochures[activeIndex].image}
          alt={brochures[activeIndex].title}
          className="w-full h-48 md:h-64 object-cover"
          loading="lazy"
        />
      </div>
    </section>
  );
};

export default WeeklyBrochures;

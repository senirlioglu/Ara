import { useState } from "react";
import { ChevronDown, ChevronUp, MapPin } from "lucide-react";

interface Store {
  name: string;
  distance: string;
  stockLevel: "Yüksek" | "Orta" | "Düşük";
  sm: string;
  bs: string;
  code: string;
}

interface Product {
  id: number;
  name: string;
  price: string;
  productCode: string;
  storeCount: number;
  regionStock: number;
  stores: Store[];
}

const stockColors: Record<string, string> = {
  Yüksek: "bg-green-500 text-white",
  Orta: "bg-yellow-500 text-white",
  Düşük: "bg-red-400 text-white",
};

const ProductCard = ({ product }: { product: Product }) => {
  const [expanded, setExpanded] = useState(false);
  const [sortBy, setSortBy] = useState<"distance" | "stock">("distance");

  const sortedStores = [...product.stores].sort((a, b) => {
    if (sortBy === "distance") {
      return parseFloat(a.distance) - parseFloat(b.distance);
    }
    const stockOrder = { Yüksek: 0, Orta: 1, Düşük: 2 };
    return stockOrder[a.stockLevel] - stockOrder[b.stockLevel];
  });

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden shadow-card">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start justify-between gap-3 p-4 text-left"
      >
        <div className="flex-1 min-w-0">
          <h3 className="font-bold text-foreground text-base leading-snug mb-2">
            {product.name}
          </h3>
          <span className="inline-block px-3 py-1 bg-red-500 text-white text-sm font-bold rounded-lg mb-2">
            {product.price}
          </span>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground flex-wrap">
            <span>{product.productCode}</span>
            <span>·</span>
            <span className="font-semibold text-foreground">{product.storeCount} mağaza</span>
            <span>·</span>
            <span className="inline-flex px-2 py-0.5 bg-green-500 text-white rounded text-xs font-semibold">
              Bölge Stok: {product.regionStock}
            </span>
          </div>
        </div>
        <div className="shrink-0 mt-1 text-muted-foreground">
          {expanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border px-4 pb-4">
          <div className="flex items-center gap-2 py-3">
            <span className="text-xs text-muted-foreground">Sırala:</span>
            <button
              onClick={() => setSortBy("distance")}
              className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                sortBy === "distance"
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted/50"
              }`}
            >
              <MapPin className="h-3 w-3" />
              Yakınlık
            </button>
            <button
              onClick={() => setSortBy("stock")}
              className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                sortBy === "stock"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted/50"
              }`}
            >
              📦 Stok
            </button>
          </div>

          <div className="space-y-2.5">
            {sortedStores.map((store, i) => (
              <div
                key={i}
                className="border border-border rounded-lg p-3 bg-background"
              >
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="font-bold text-sm text-foreground">{store.name}</h4>
                      <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                        {store.distance} km
                      </span>
                    </div>
                    <button className="text-xs text-red-500 font-medium flex items-center gap-0.5 mt-0.5">
                      <MapPin className="h-3 w-3" />
                      Yol tarifi
                    </button>
                  </div>
                  <span className={`text-xs font-bold px-2.5 py-1 rounded ${stockColors[store.stockLevel]}`}>
                    {store.stockLevel}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  SM: {store.sm} · BS: {store.bs} · {store.code}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ProductCard;

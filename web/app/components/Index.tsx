import { useState } from "react";
import HeroHeader from "@/components/HeroHeader";
import SearchBar from "@/components/SearchBar";
import PopularSearches from "@/components/PopularSearches";
import ProductCard from "@/components/ProductCard";
import WeeklyBrochures from "@/components/WeeklyBrochures";

const mockProducts = [
  {
    id: 1,
    name: 'TV 55" U65A UHD SMART GOOGLE IFFALCON',
    price: "22.999,00 ₺",
    productCode: "26071231",
    storeCount: 96,
    regionStock: 100,
    stores: [
      { name: "Güzeloba Antalya", distance: "13.7", stockLevel: "Orta" as const, sm: "VELİ GÖK", bs: "ÇAĞRI YALÇIN", code: "1484" },
      { name: "Tonguç Antalya", distance: "5.3", stockLevel: "Düşük" as const, sm: "ALİ AKÇAY", bs: "ÜMİT KIRBAŞ", code: "1441" },
      { name: "Kültür Merkezi Muratpaşa", distance: "6.4", stockLevel: "Düşük" as const, sm: "SADAN YURDAKUL", bs: "ÜMİT KAAN", code: "1392" },
      { name: "Lara Antalya", distance: "8.1", stockLevel: "Yüksek" as const, sm: "MEHMET KAYA", bs: "AHMET DEMİR", code: "1455" },
    ],
  },
  {
    id: 2,
    name: "Kuruyemiş Keyifli Mix 330g Master Nut",
    price: "54,90 ₺",
    productCode: "18045672",
    storeCount: 142,
    regionStock: 250,
    stores: [
      { name: "Güzeloba Antalya", distance: "13.7", stockLevel: "Yüksek" as const, sm: "VELİ GÖK", bs: "ÇAĞRI YALÇIN", code: "1484" },
      { name: "Tonguç Antalya", distance: "5.3", stockLevel: "Orta" as const, sm: "ALİ AKÇAY", bs: "ÜMİT KIRBAŞ", code: "1441" },
    ],
  },
];

const Index = () => {
  const [query, setQuery] = useState("");
  const [searchedQuery, setSearchedQuery] = useState("");

  const handleSearch = (q: string) => {
    setQuery(q);
    setSearchedQuery(q);
  };

  const filtered = searchedQuery
    ? mockProducts.filter((p) =>
        p.name.toLowerCase().includes(searchedQuery.toLowerCase())
      )
    : mockProducts;

  return (
    <div className="min-h-screen bg-background">
      <HeroHeader />
      <div className="px-4 -mt-6 space-y-5 pb-12">
        <SearchBar onSearch={handleSearch} initialQuery={query} />
        <PopularSearches onSearch={handleSearch} />

        {filtered.length > 0 && (
          <div className="w-full max-w-2xl mx-auto">
            <div className="flex items-center gap-2 mb-3 text-sm">
              <span className="text-primary font-bold">{filtered.length}</span>
              <span className="text-muted-foreground">ürün bulundu</span>
              <span className="text-muted-foreground">·</span>
              <span className="text-red-500 font-medium flex items-center gap-1">
                📍 Yakınına göre sıralı
              </span>
            </div>
            <div className="space-y-3">
              {filtered.map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>
          </div>
        )}

        <WeeklyBrochures />
      </div>
    </div>
  );
};

export default Index;

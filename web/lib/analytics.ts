/** Google Analytics event helpers */

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
  }
}

function track(event: string, params?: Record<string, unknown>) {
  if (typeof window !== "undefined" && window.gtag) {
    window.gtag("event", event, params);
  }
}

export const analytics = {
  search(query: string, resultCount: number) {
    track("search", { search_term: query, result_count: resultCount });
  },
  barcodeScan(barcode: string) {
    track("barcode_scan", { barcode });
  },
  productExpand(urunKod: string, urunAd: string) {
    track("product_expand", { urun_kod: urunKod, urun_ad: urunAd });
  },
  directionsClick(magazaAd: string, magazaKod: string) {
    track("directions_click", { magaza_ad: magazaAd, magaza_kod: magazaKod });
  },
  sortChange(mode: "distance" | "stock") {
    track("sort_change", { sort_mode: mode });
  },
  posterWeek(weekName: string) {
    track("poster_week", { week_name: weekName });
  },
  posterSwipe(pageIndex: number, total: number) {
    track("poster_swipe", { page_index: pageIndex, total_pages: total });
  },
  hotspotClick(urunKod: string) {
    track("hotspot_click", { urun_kod: urunKod });
  },
  popularSearch(term: string) {
    track("popular_search", { search_term: term });
  },
  locationResponse(response: "accept" | "dismiss") {
    track("location_response", { response });
  },
};

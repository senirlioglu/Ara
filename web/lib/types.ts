/** Product search result row (from hizli_urun_ara RPC) */
export interface StokRow {
  urun_kod: string;
  urun_ad: string;
  magaza_kod: string;
  magaza_ad: string;
  stok_adet: number;
  birim_fiyat: number;
  latitude: number | null;
  longitude: number | null;
  sm_kod: string | null;
  bs_kod: string | null;
}

/** Grouped product for display */
export interface ProductCard {
  urun_kod: string;
  urun_ad: string;
  fiyat: number;
  stoklu_magaza: number;
  toplam_stok: number;
  magazalar: StoreStock[];
}

/** Per-store stock info */
export interface StoreStock {
  magaza_kod: string;
  magaza_ad: string;
  stok_adet: number;
  birim_fiyat: number;
  sm_kod: string | null;
  bs_kod: string | null;
  latitude: number | null;
  longitude: number | null;
}

/** Poster week metadata */
export interface PosterWeek {
  week_id: string;
  week_name: string;
  status: string;
  sort_order: number;
}

/** Poster page (metadata + image URL) */
export interface PosterPage {
  id: number;
  week_id: string;
  flyer_filename: string;
  page_no: number;
  image_path: string;
  title: string;
  sort_order: number;
}

/** Hotspot mapping on a poster */
export interface Hotspot {
  mapping_id: number;
  week_id: string;
  flyer_filename: string;
  page_no: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  urun_kodu: string;
  urun_aciklamasi: string | null;
  afis_fiyat: string | null;
}

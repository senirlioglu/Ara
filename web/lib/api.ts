import { supabase } from "./supabase";
import { normalizeTurkish } from "./turkish";
import type {
  StokRow,
  ProductCard,
  StoreStock,
  PosterWeek,
  PosterPage,
  Hotspot,
} from "./types";

// ─── Barcode Lookup ─────────────────────────────────────────────

/** Look up a barcode in urun_barkod table → return urun_kod */
export async function lookupBarcode(barcode: string): Promise<string | null> {
  const trimmed = barcode.trim();
  if (!trimmed) return null;

  const { data, error } = await supabase
    .from("urun_barkod")
    .select("urun_kod")
    .eq("barkod", trimmed)
    .limit(1);

  if (error || !data || data.length === 0) return null;
  return data[0].urun_kod as string;
}

/** Search by barcode: lookup barkod → get urun_kod → search stok */
export async function searchByBarcode(barcode: string): Promise<ProductCard[]> {
  const urunKod = await lookupBarcode(barcode);
  if (!urunKod) return [];
  return searchProducts(urunKod);
}

// ─── Product Search ─────────────────────────────────────────────

const RE_TV_NEGATIF =
  /ADAPTÖR|APARATI|AYAK|ASKISI|BAĞLANTI|BOYA|ÇUBUK|DUVAR|FİLTRE|GÖRÜNTÜ|HORTUM|KABLO|KAPAK|KLIPS|KUMANDA|MODÜL|MOTOR|MUHAFAZA|PANEL|PERDE|PLAKA|PLAZMA|ROBOT|SENSÖR|SERVİS|SPLITTER|TABLA|TIRNAK|TUTUCU|ÜNİTE|YÜZEY/i;

function isProductCode(query: string): boolean {
  return /^\d{7,}$/.test(query.trim());
}

/** Score results for relevance (mirrors Python calculate_relevance) */
function scoreResults(rows: StokRow[], query: string): StokRow[] {
  const qLower = query.toLowerCase();
  const qWords = new Set(qLower.split(/\s+/));
  const isCode = /^\d+$/.test(query);

  const scored = rows.map((row) => {
    let score = 0;
    const ad = (row.urun_ad ?? "").toLowerCase();
    const kod = String(row.urun_kod);

    if (isCode) {
      if (kod === query) score += 1000;
      else if (kod.startsWith(query)) score += 600;
      else if (query.length >= 6 && kod.includes(query)) score += 200;
    }

    if (ad.includes(qLower)) score += 100;

    const adWords = new Set(ad.split(/\s+/));
    for (const w of qWords) {
      if (adWords.has(w)) score += 10;
    }

    if (row.stok_adet > 0) score += 5;

    return { ...row, _score: score };
  });

  // TV filter
  if (qWords.has("tv") || qWords.has("televizyon")) {
    return scored
      .filter((r) => !RE_TV_NEGATIF.test(r.urun_ad))
      .sort((a, b) => b._score - a._score || b.stok_adet - a.stok_adet);
  }

  return scored.sort(
    (a, b) => b._score - a._score || b.stok_adet - a.stok_adet
  );
}

/** Deduplicate by magaza_kod + urun_kod */
function dedup(rows: StokRow[]): StokRow[] {
  const seen = new Set<string>();
  return rows.filter((r) => {
    const key = `${r.magaza_kod}__${r.urun_kod}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Group flat rows into ProductCard[] for display */
export function groupProducts(rows: StokRow[]): ProductCard[] {
  // Preserve order of first occurrence
  const orderMap = new Map<string, number>();
  rows.forEach((r, i) => {
    if (!orderMap.has(r.urun_kod)) orderMap.set(r.urun_kod, i);
  });

  const grouped = new Map<string, StokRow[]>();
  for (const r of rows) {
    const arr = grouped.get(r.urun_kod) ?? [];
    arr.push(r);
    grouped.set(r.urun_kod, arr);
  }

  const cards: ProductCard[] = [];
  for (const [kod, storeRows] of grouped) {
    const first = storeRows[0];
    const stoklu = storeRows.filter((r) => r.stok_adet > 0);
    const toplam = stoklu.reduce((s, r) => s + r.stok_adet, 0);

    // Get first valid price
    const fiyat =
      stoklu.find((r) => r.birim_fiyat > 0)?.birim_fiyat ??
      storeRows.find((r) => r.birim_fiyat > 0)?.birim_fiyat ??
      0;

    const magazalar: StoreStock[] = stoklu
      .sort((a, b) => b.stok_adet - a.stok_adet)
      .map((r) => ({
        magaza_kod: r.magaza_kod,
        magaza_ad: r.magaza_ad,
        stok_adet: r.stok_adet,
        birim_fiyat: r.birim_fiyat,
        sm_kod: r.sm_kod,
        bs_kod: r.bs_kod,
        latitude: r.latitude,
        longitude: r.longitude,
      }));

    cards.push({
      urun_kod: kod,
      urun_ad: first.urun_ad,
      fiyat,
      stoklu_magaza: stoklu.length,
      toplam_stok: toplam,
      magazalar,
    });
  }

  // Sort by first-occurrence order (preserves relevance ranking)
  cards.sort(
    (a, b) => (orderMap.get(a.urun_kod) ?? 0) - (orderMap.get(b.urun_kod) ?? 0)
  );

  return cards;
}

/** Main search function — calls hizli_urun_ara RPC */
export async function searchProducts(rawQuery: string): Promise<ProductCard[]> {
  const trimmed = rawQuery.trim();
  if (!trimmed || trimmed.length < 2) return [];

  // Detect "KOD - AD" format from autocomplete
  const kodPrefixMatch = trimmed.match(/^\s*(\d{5,})\s*(?:-|–)\s*/);
  let query: string;
  if (kodPrefixMatch) {
    query = kodPrefixMatch[1];
  } else if (/^\d+$/.test(trimmed)) {
    query = trimmed;
  } else {
    query = normalizeTurkish(trimmed);
  }

  const isCode = isProductCode(query);

  // Primary search
  const { data, error } = await supabase.rpc("hizli_urun_ara", {
    arama_terimi: query,
  });

  if (error) throw error;

  if (data && data.length > 0) {
    const mapped = mapRpcResult(data);
    const scored = scoreResults(mapped, query);
    const unique = dedup(scored);

    if (isCode) {
      const exact = unique.filter((r) => String(r.urun_kod) === query);
      if (exact.length > 0) return groupProducts(exact);
    }

    return groupProducts(unique);
  }

  // Code search: no fallback
  if (isCode) return [];

  // Fallback: try individual words
  const words = query.split(/\s+/).filter((w) => w.length >= 3);
  for (const word of words) {
    const { data: fb } = await supabase.rpc("hizli_urun_ara", {
      arama_terimi: word,
    });
    if (fb && fb.length > 0) {
      return groupProducts(dedup(scoreResults(mapRpcResult(fb), query)));
    }
  }

  return [];
}

/** Map RPC column names (out_ prefix) to StokRow */
function mapRpcResult(data: Record<string, unknown>[]): StokRow[] {
  return data.map((r) => ({
    urun_kod: String(r.out_urun_kod ?? r.urun_kod ?? ""),
    urun_ad: String(r.out_urun_ad ?? r.urun_ad ?? ""),
    magaza_kod: String(r.out_magaza_kod ?? r.magaza_kod ?? ""),
    magaza_ad: String(r.out_magaza_ad ?? r.magaza_ad ?? ""),
    stok_adet: Number(r.out_stok_adet ?? r.stok_adet ?? 0),
    birim_fiyat: Number(r.out_birim_fiyat ?? r.birim_fiyat ?? 0),
    latitude: (r.out_latitude ?? r.latitude ?? null) as number | null,
    longitude: (r.out_longitude ?? r.longitude ?? null) as number | null,
    sm_kod: (r.out_sm_kod ?? r.sm_kod ?? null) as string | null,
    bs_kod: (r.out_bs_kod ?? r.bs_kod ?? null) as string | null,
  }));
}

// ─── Search Logging ─────────────────────────────────────────────

export async function logSearch(term: string, resultCount: number) {
  try {
    const terim = term.trim().toLowerCase().slice(0, 100);
    const bugun = new Date().toISOString().slice(0, 10);
    const simdi = new Date().toISOString();

    const { data: existing } = await supabase
      .from("arama_log")
      .select("id, arama_sayisi")
      .eq("tarih", bugun)
      .eq("arama_terimi", terim)
      .limit(1);

    if (existing && existing.length > 0) {
      await supabase
        .from("arama_log")
        .update({
          arama_sayisi: existing[0].arama_sayisi + 1,
          sonuc_sayisi: resultCount,
          son_arama_zamani: simdi,
        })
        .eq("id", existing[0].id);
    } else {
      await supabase.from("arama_log").insert({
        tarih: bugun,
        arama_terimi: terim,
        arama_sayisi: 1,
        sonuc_sayisi: resultCount,
        son_arama_zamani: simdi,
      });
    }
  } catch {
    // Silent fail — logging should never break the app
  }
}

/** Popular search terms from last 3 days */
export async function getPopularTerms(): Promise<string[]> {
  try {
    const threeDaysAgo = new Date(Date.now() - 3 * 86400000)
      .toISOString()
      .slice(0, 10);

    const { data } = await supabase
      .from("arama_log")
      .select("arama_terimi, arama_sayisi")
      .gte("tarih", threeDaysAgo)
      .gt("sonuc_sayisi", 0)
      .order("arama_sayisi", { ascending: false })
      .limit(10);

    if (data) {
      return data
        .map((r) => r.arama_terimi as string)
        .filter((t) => !/^\d+$/.test(t.trim()));
    }
  } catch {
    // Silent fail
  }
  return ["tv", "klima", "supurge", "mama", "tuvalet kagidi"];
}

// ─── Poster / Weeks ─────────────────────────────────────────────

const POSTER_BUCKET = "poster-images";

/** Get published weeks with names, ordered */
export async function getPublishedWeeks(): Promise<PosterWeek[]> {
  const { data: pagesData } = await supabase
    .from("poster_pages")
    .select("week_id");

  const pageWeekIds = new Set(
    (pagesData ?? []).map((r) => r.week_id as string)
  );
  if (pageWeekIds.size === 0) return [];

  const { data: weeksData } = await supabase
    .from("poster_weeks")
    .select("week_id, week_name, status, sort_order, created_at");

  if (!weeksData) return [];

  // Only published weeks that have pages
  const published = weeksData.filter(
    (w) =>
      pageWeekIds.has(w.week_id) &&
      (w.status === "published" || w.status === null)
  );

  // Sort: explicit sort_order > 0 first (ASC), then by newest created_at
  published.sort((a, b) => {
    const aOrder = a.sort_order ?? 0;
    const bOrder = b.sort_order ?? 0;
    if (aOrder > 0 && bOrder > 0) return aOrder - bOrder;
    if (aOrder > 0) return -1;
    if (bOrder > 0) return 1;
    return (b.created_at ?? "").localeCompare(a.created_at ?? "");
  });

  return published.map((w) => ({
    week_id: w.week_id,
    week_name: w.week_name ?? w.week_id,
    status: w.status ?? "published",
    sort_order: w.sort_order ?? 0,
  }));
}

/** Get poster pages for a week (metadata + public image URLs) */
export async function getPosterPages(weekId: string): Promise<PosterPage[]> {
  const { data } = await supabase
    .from("poster_pages")
    .select("id, week_id, flyer_filename, page_no, image_path, title, sort_order")
    .eq("week_id", weekId)
    .order("sort_order")
    .order("flyer_filename")
    .order("page_no");

  return (data ?? []).map((r) => ({
    id: r.id,
    week_id: r.week_id,
    flyer_filename: r.flyer_filename,
    page_no: r.page_no,
    image_path: r.image_path,
    title: r.title ?? "",
    sort_order: r.sort_order ?? 0,
  }));
}

/** Get public URL for a poster image */
export function getPosterImageUrl(imagePath: string): string {
  const { data } = supabase.storage.from(POSTER_BUCKET).getPublicUrl(imagePath);
  return data.publicUrl;
}

/** Get all hotspot mappings for a week */
export async function getMappingsForWeek(weekId: string): Promise<Hotspot[]> {
  const { data } = await supabase
    .from("mappings")
    .select("*")
    .eq("week_id", weekId)
    .order("mapping_id");

  return (data ?? []) as Hotspot[];
}

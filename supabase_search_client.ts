/**
 * SUPABASE TÜRKÇE ARAMA CLIENT
 * ============================
 * Full-Text Search + Fuzzy Search kullanımı
 */

import { createClient, SupabaseClient } from '@supabase/supabase-js';

// Supabase client oluştur
const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseKey = process.env.SUPABASE_ANON_KEY!;

const supabase: SupabaseClient = createClient(supabaseUrl, supabaseKey);

// ============================================================================
// TİPLER
// ============================================================================

interface Product {
  id: number;
  name: string;
  description: string | null;
  category: string | null;
  price: number;
  stock: number;
  match_type?: 'exact' | 'fuzzy' | 'prefix';
  rank?: number;
}

interface SearchOptions {
  category?: string;
  minPrice?: number;
  maxPrice?: number;
  limit?: number;
  fuzzyThreshold?: number;
}

interface AutocompleteSuggestion {
  suggestion: string;
  product_count: number;
}

// ============================================================================
// ARAMA FONKSİYONLARI
// ============================================================================

/**
 * Ürün arama (Hybrid: FTS + Fuzzy)
 * @param keyword - Arama terimi
 * @param options - Filtre seçenekleri
 */
export async function searchProducts(
  keyword: string,
  options: SearchOptions = {}
): Promise<Product[]> {
  const {
    category = null,
    minPrice = null,
    maxPrice = null,
    limit = 50,
    fuzzyThreshold = 0.3,
  } = options;

  const { data, error } = await supabase.rpc('search_products', {
    keyword,
    category_filter: category,
    min_price: minPrice,
    max_price: maxPrice,
    result_limit: limit,
    fuzzy_threshold: fuzzyThreshold,
  });

  if (error) {
    console.error('Arama hatası:', error);
    throw error;
  }

  return data as Product[];
}

/**
 * Autocomplete önerileri
 * @param partialKeyword - Kısmi arama terimi
 * @param limit - Maksimum öneri sayısı
 */
export async function getAutocomplete(
  partialKeyword: string,
  limit: number = 10
): Promise<AutocompleteSuggestion[]> {
  const { data, error } = await supabase.rpc('autocomplete_products', {
    partial_keyword: partialKeyword,
    result_limit: limit,
  });

  if (error) {
    console.error('Autocomplete hatası:', error);
    throw error;
  }

  return data as AutocompleteSuggestion[];
}

/**
 * Basit FTS arama (RPC olmadan)
 * @param keyword - Arama terimi
 */
export async function simpleFTSSearch(keyword: string): Promise<Product[]> {
  const { data, error } = await supabase
    .from('products')
    .select('*')
    .textSearch('fts', keyword, {
      type: 'plain',
      config: 'simple',
    })
    .limit(50);

  if (error) {
    console.error('FTS arama hatası:', error);
    throw error;
  }

  return data as Product[];
}

/**
 * Türkçe karakter normalize et (client-side)
 */
export function normalizeTurkish(text: string): string {
  const turkishMap: Record<string, string> = {
    'İ': 'i', 'I': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c',
    'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
  };

  return text
    .split('')
    .map((char) => turkishMap[char] || char)
    .join('')
    .toLowerCase();
}

// ============================================================================
// REACT HOOK ÖRNEĞİ
// ============================================================================

/**
 * React hook örneği (React projelerinde kullanım için)
 *
 * import { useState, useEffect } from 'react';
 *
 * export function useProductSearch(keyword: string, debounceMs: number = 300) {
 *   const [results, setResults] = useState<Product[]>([]);
 *   const [loading, setLoading] = useState(false);
 *   const [error, setError] = useState<Error | null>(null);
 *
 *   useEffect(() => {
 *     if (!keyword || keyword.length < 2) {
 *       setResults([]);
 *       return;
 *     }
 *
 *     const timer = setTimeout(async () => {
 *       setLoading(true);
 *       try {
 *         const data = await searchProducts(keyword);
 *         setResults(data);
 *         setError(null);
 *       } catch (err) {
 *         setError(err as Error);
 *       } finally {
 *         setLoading(false);
 *       }
 *     }, debounceMs);
 *
 *     return () => clearTimeout(timer);
 *   }, [keyword, debounceMs]);
 *
 *   return { results, loading, error };
 * }
 */

// ============================================================================
// KULLANIM ÖRNEKLERİ
// ============================================================================

async function main() {
  console.log('=== Supabase Türkçe Arama Örnekleri ===\n');

  // 1. Basit arama
  console.log('1. "ekmek" araması:');
  const ekmekResults = await searchProducts('ekmek');
  console.log(ekmekResults);

  // 2. Yazım hatalı arama (fuzzy)
  console.log('\n2. "makina" araması (yazım hatası):');
  const makinaResults = await searchProducts('makina');
  console.log(makinaResults);

  // 3. Türkçe karakter olmadan arama
  console.log('\n3. "gozluk" araması (Türkçe karaktersiz):');
  const gozlukResults = await searchProducts('gozluk');
  console.log(gozlukResults);

  // 4. Kategori filtreli arama
  console.log('\n4. "Beyaz Eşya" kategorisinde arama:');
  const filteredResults = await searchProducts('makine', {
    category: 'Beyaz Eşya',
  });
  console.log(filteredResults);

  // 5. Fiyat aralıklı arama
  console.log('\n5. Fiyat filtreli arama (100-500 TL):');
  const priceResults = await searchProducts('', {
    minPrice: 100,
    maxPrice: 500,
  });
  console.log(priceResults);

  // 6. Autocomplete
  console.log('\n6. "bil" için autocomplete:');
  const suggestions = await getAutocomplete('bil');
  console.log(suggestions);
}

// Test için çalıştır
// main().catch(console.error);

export default {
  searchProducts,
  getAutocomplete,
  simpleFTSSearch,
  normalizeTurkish,
};

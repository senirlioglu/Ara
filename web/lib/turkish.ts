/**
 * Turkish character normalization — mirrors SQL normalize_tr_search().
 *
 * Steps (same order as PostgreSQL function):
 *  1. translate İIıĞğÜüŞşÖöÇç → ASCII
 *  2. strip combining accents (â→a etc.)
 *  3. lowercase
 *  4-6. makinasi/makinesi/makina → makine
 *  7. common typo corrections
 */

const TR_MAP: Record<string, string> = {
  İ: "i", I: "i", ı: "i",
  Ğ: "g", ğ: "g",
  Ü: "u", ü: "u",
  Ş: "s", ş: "s",
  Ö: "o", ö: "o",
  Ç: "c", ç: "c",
};

const YAZIM_DUZELTME: Record<string, string> = {
  nescaffe: "nescafe", nescfe: "nescafe", nesacfe: "nescafe",
  cold: "gold",
  philps: "philips", phlips: "philips", plips: "philips",
};

export function normalizeTurkish(text: string): string {
  if (!text) return "";

  // 1. Turkish char translation
  let result = "";
  for (const ch of text) {
    result += TR_MAP[ch] ?? ch;
  }

  // 2. Strip combining accents (â→a etc.)
  result = result.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");

  // 3. Lowercase
  result = result.toLowerCase();

  // 4-6. Makine normalization
  result = result
    .replace(/makinasi/g, "makine")
    .replace(/makinesi/g, "makine")
    .replace(/makina/g, "makine");

  // Strip smart quotes & special chars
  result = result
    .replace(/[\u201c\u201d\u2019]/g, "")
    .replace(/\u00a0/g, " ")
    .replace(/\u0307/g, "");

  // Split tv+number: "tv65" → "tv 65"
  result = result.replace(/(tv|televizyon)(\d)/g, "$1 $2");

  // Collapse whitespace
  result = result.replace(/\s+/g, " ").trim();

  // 7. Typo corrections
  const words = result.split(" ");
  const corrected = words.map((w) => YAZIM_DUZELTME[w] ?? w);
  return corrected.join(" ");
}

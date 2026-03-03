from rapidfuzz import fuzz

from utils_text import extract_tokens, normalize_tr


def _row_text(row) -> str:
    return normalize_tr(f"{row.get('ÜRÜN KODU', '')} {row.get('ÜRÜN AÇIKLAMASI', '')}")


def top_k_candidates(ocr_text, excel_df, k=5):
    ocr_norm = normalize_tr(ocr_text)
    tokens = extract_tokens(ocr_text)
    ranked = []

    for _, row in excel_df.iterrows():
        row_text = _row_text(row)
        score = 0

        if tokens["model_tokens"] and any(tok in row_text for tok in tokens["model_tokens"]):
            score += 100
        if tokens["four_digit_tokens"] and any(tok in row_text for tok in tokens["four_digit_tokens"]):
            score += 80
        if tokens["brand_tokens"] and any(tok in row_text for tok in tokens["brand_tokens"]):
            score += 30
        if tokens["size_tokens"] and any(tok in row_text for tok in tokens["size_tokens"]):
            score += 20

        fuzzy = fuzz.token_set_ratio(ocr_norm, row_text)
        score += int(fuzzy * 0.30)

        ranked.append(
            {
                "urun_kodu": str(row.get("ÜRÜN KODU", "")),
                "urun_aciklamasi": str(row.get("ÜRÜN AÇIKLAMASI", "")),
                "afis_fiyat": row.get("AFIS_FIYAT", None),
                "score": score,
            }
        )

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:k]

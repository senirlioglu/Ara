"""Text normalization and token extraction utilities."""

from __future__ import annotations

import re

_TR_MAP = str.maketrans("İŞĞÖÜÇıişğöüç", "ISGOUCiisgouc")

BRAND_WHITELIST = {
    "SAMSUNG", "LG", "SONY", "PHILIPS", "VESTEL", "TOSHIBA", "BEKO",
    "ARCELIK", "ARÇELIK", "ONVO", "NORDMENDE", "SEG", "GRUNDIG",
    "PIRANHA", "XIAOMI", "TCL", "HISENSE", "BOSCH", "SIEMENS", "REGAL",
    "ALTUS", "PROFILO", "FAKIR", "ARZUM", "SINBO", "KARACA", "KUMTEL",
    "LUXELL", "HOMEND", "KING", "FANTOM", "DYSON", "TEFAL", "BRAUN",
    "PANASONIC", "KENWOOD", "DELONGHI", "HP", "LENOVO", "APPLE",
    "HUAWEI", "OPPO", "MONSTER", "CASPER", "EXCALIBUR", "MSI", "ASUS",
    "ACER", "DELL", "LOGITECH", "JBL", "ANKER", "BASEUS", "UGREEN",
}


def normalize_tr(text: str) -> str:
    """Uppercase, strip punctuation, collapse whitespace."""
    s = text.upper().translate(_TR_MAP)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_tokens(text: str) -> dict:
    """Extract structured tokens from text."""
    upper = normalize_tr(text)

    model_tokens = [
        m for m in re.findall(r"\b[A-Z0-9\-]{6,}\b", upper)
        if re.search(r"[A-Z]", m) and re.search(r"\d", m)
    ]

    code4_tokens = re.findall(r"\b\d{4}\b", upper)

    size_tokens = re.findall(
        r'\b\d{2,3}\s*(?:"|CM|INC|KG|LT?|MAH)\b', upper,
    )

    brand_tokens = [b for b in BRAND_WHITELIST if b in upper or normalize_tr(b) in upper]

    return {
        "model": model_tokens,
        "code4": code4_tokens,
        "size": size_tokens,
        "brand": brand_tokens,
    }

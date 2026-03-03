import re
import string

BRAND_WHITELIST = [
    "SAMSUNG",
    "LG",
    "APPLE",
    "XIAOMI",
    "PHILIPS",
    "ARCELIK",
    "BEKO",
    "VESTEL",
    "BOSCH",
    "SIEMENS",
    "ASUS",
    "HP",
    "LENOVO",
]

TR_MAP = str.maketrans(
    {
        "İ": "I",
        "I": "I",
        "Ş": "S",
        "Ğ": "G",
        "Ö": "O",
        "Ü": "U",
        "Ç": "C",
        "ı": "I",
        "ş": "S",
        "ğ": "G",
        "ö": "O",
        "ü": "U",
        "ç": "C",
    }
)


def normalize_tr(text: str) -> str:
    text = (text or "").translate(TR_MAP).upper()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_tokens(text: str) -> dict:
    raw_txt = (text or "").translate(TR_MAP).upper()
    txt = normalize_tr(text)
    model_tokens = set(re.findall(r"\b[A-Z0-9]{6,}\b", txt))
    four_digit_tokens = set(re.findall(r"\b\d{4}\b", txt))
    size_tokens = set(
        re.findall(r"\b\d{2,3}\s*\"\b|\b\d+(?:[.,]\d+)?\s*(?:KG|L|MAH)\b", raw_txt)
    )
    brand_tokens = {b for b in BRAND_WHITELIST if b in txt}
    return {
        "model_tokens": model_tokens,
        "four_digit_tokens": four_digit_tokens,
        "size_tokens": size_tokens,
        "brand_tokens": brand_tokens,
    }

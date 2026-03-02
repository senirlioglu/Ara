from flyer.price_detect import find_prices
from flyer.region_builder import build_regions
from flyer.match_excel import match_regions
import pandas as pd

# Mock OCR words from a grocery flyer (e.g., "Dana Kıyma 1 Kg 349 TL")
mock_words = [
    {"text": "Dana", "x0": 100, "y0": 100, "x1": 150, "y1": 120},
    {"text": "Kıyma", "x0": 160, "y0": 100, "x1": 220, "y1": 120},
    {"text": "1", "x0": 230, "y0": 100, "x1": 240, "y1": 120},
    {"text": "Kg", "x0": 250, "y0": 100, "x1": 270, "y1": 120},
    {"text": "349", "x0": 150, "y0": 130, "x1": 200, "y1": 150},
    {"text": "TL", "x0": 210, "y0": 130, "x1": 240, "y1": 150},
]

# Mock image dimensions
img_w, img_h = 1000, 1000

print("Testing price_detect...")
prices = find_prices(mock_words, img_w, img_h)
print("Detected prices:", prices)
assert len(prices) == 1, f"Expected 1 price, found {len(prices)}"
assert prices[0]["value"] == "349", f"Expected price 349, got {prices[0]['value']}"
print("Price detection passed!\n")


print("Testing region_builder...")
regions = build_regions(mock_words, prices, img_w, img_h)
print("Built regions:", len(regions))
for i, r in enumerate(regions):
    print(f"Region {i}: {r['region_text']}")
assert len(regions) == 1, f"Expected 1 region, found {len(regions)}"
assert "Dana" in regions[0]["region_text"], "Expected 'Dana' in region text"
print("Region builder passed!\n")

print("Testing match_excel...")
mock_excel = pd.DataFrame([
    {"urun_kodu": "MIGROS-123", "urun_aciklamasi": "Uzman Kasap Dana Kıyma 1 Kg", "afis_fiyat": "349"},
    {"urun_kodu": "MIGROS-456", "urun_aciklamasi": "Piliç Bonfile 500 Gr", "afis_fiyat": "89"}
])

# Re-assign an arbitrary region_id for matching test
regions[0]["region_id"] = 1

matches = match_regions(regions, mock_excel, top_n=3)
print("Matches found:")
for m in matches:
    print(f"- Region ID: {m['region_id']}")
    print(f"  Status: {m['status']}")
    print(f"  Best Match: {m['best_match']}")
    for c in m['candidates']:
        print(f"    Candidate: {c['urun_aciklamasi']} (Score: {c['score']})")

assert len(matches) == 1, "Expected 1 match result"
assert matches[0]["status"] == "matched", f"Expected status 'matched', got {matches[0]['status']}"
assert "Dana Kıyma" in matches[0]["best_match"]["urun_aciklamasi"], "Expected best match to be Dana Kıyma"
print("Match excel passed!\n")
print("All tests passed successfully!")

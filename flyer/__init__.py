"""Flyer pipeline v3 — Price-Anchored Product Regions (Lens-like).

PDF → Vision OCR (words) → Price Detection → Region Building → Excel Matching.

Modules:
  pdf_render         — PyMuPDF zoom-based PDF→PNG
  vision_ocr         — Google Cloud Vision word-level OCR + caching
  price_detect       — Price seed detection (large + small with context)
  region_builder     — Price-anchored region builder + IOU merge
  match_excel        — Weighted scoring against Excel products
  storage_supabase   — Supabase CRUD
  admin_bulk_import  — Streamlit bulk upload UI
  admin_review       — Streamlit per-page review UI
  viewer             — Store staff viewer with hotspot overlays
"""

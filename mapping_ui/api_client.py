"""Thin HTTP client for the Mapping Engine backend."""

from __future__ import annotations

import os

import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "dev-key-change-me")

_HEADERS = {"X-API-KEY": API_KEY}


def _url(path: str) -> str:
    return f"{BACKEND_URL}{path}"


# ── Pages ──

@st.cache_data(ttl=300)
def get_pages(week_id: str) -> list[dict]:
    r = httpx.get(_url(f"/weeks/{week_id}/pages"), timeout=10)
    r.raise_for_status()
    return r.json()


# ── Mappings ──

def get_mappings(week_id: str, flyer_id: str, page_no: int) -> list[dict]:
    r = httpx.get(
        _url(f"/weeks/{week_id}/pages/{flyer_id}/{page_no}/mappings"),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def save_mapping(
    week_id: str, flyer_id: str, page_no: int,
    bbox: dict, urun_kod: str, urun_ad: str | None, source: str,
) -> dict:
    r = httpx.post(
        _url(f"/weeks/{week_id}/pages/{flyer_id}/{page_no}/mappings"),
        json={"bbox": bbox, "urun_kod": urun_kod, "urun_ad": urun_ad, "source": source},
        headers=_HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def delete_mapping(week_id: str, mapping_id: str) -> dict:
    r = httpx.delete(
        _url(f"/weeks/{week_id}/mappings/{mapping_id}"),
        headers=_HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


# ── Products ──

@st.cache_data(ttl=600)
def get_products(week_id: str) -> list[dict]:
    """Fetch all products for a week — cached 10 min."""
    r = httpx.get(_url(f"/weeks/{week_id}/products"), timeout=10)
    r.raise_for_status()
    return r.json()


# ── Week ──

def get_week_status(week_id: str) -> dict:
    r = httpx.get(_url(f"/weeks/{week_id}/status"), timeout=10)
    r.raise_for_status()
    return r.json()


def upload_pdf(week_id: str, flyer_id: str, filename: str, pdf_bytes: bytes) -> dict:
    r = httpx.post(
        _url(f"/weeks/{week_id}/upload-pdf"),
        data={"flyer_id": flyer_id},
        files={"file": (filename, pdf_bytes, "application/pdf")},
        headers=_HEADERS,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()


def upload_excel(week_id: str, filename: str, excel_bytes: bytes) -> dict:
    r = httpx.post(
        _url(f"/weeks/{week_id}/upload-excel"),
        files={"file": (filename, excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=_HEADERS,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def image_url(image_path: str | None) -> str | None:
    """Convert relative image_path to full URL."""
    if not image_path:
        return None
    return f"{BACKEND_URL}{image_path}"

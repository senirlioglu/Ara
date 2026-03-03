import fitz


def render_pdf_bytes_to_pages(pdf_bytes: bytes, zoom: float = 3.5) -> list[dict]:
    pages = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        matrix = fitz.Matrix(zoom, zoom)
        for idx, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pix.tobytes("png")
            pages.append(
                {
                    "page_no": idx,
                    "png_bytes": png_bytes,
                    "w": pix.width,
                    "h": pix.height,
                }
            )
    finally:
        doc.close()
    return pages

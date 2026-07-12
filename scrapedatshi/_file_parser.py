"""
scrapedatshi._file_parser
~~~~~~~~~~~~~~~~~~~~~~~~~
Local file text extraction helpers.

These functions run on the CLIENT machine — not on the scrapedatshi server.
They extract plain text from local files (PDF, MD, TXT, YAML, JSON) so the
heavy CPU work (PDF parsing, OCR) stays off the server.

The extracted text is then submitted to /v1/process-text for chunking.

Supported formats:
    .pdf   — pdfplumber (text layer) with basic fallback
    .md    — read as-is (already markdown)
    .txt   — read as-is
    .yaml / .yml — YAML → formatted text
    .json  — JSON → formatted text

Dependencies:
    pdfplumber is required for PDF extraction.  It is listed as an optional
    dependency of scrapedatshi — install it with:
        pip install scrapedatshi[pdf]
    or directly:
        pip install pdfplumber
"""

from __future__ import annotations

from pathlib import Path


def _guess_source_type(path: Path) -> str:
    """Return a short source type string based on file extension."""
    ext = path.suffix.lower()
    mapping = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".txt": "text",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
    }
    return mapping.get(ext, "text")


def _extract_file_text_locally(path: Path) -> str:
    """
    Extract plain text from a local file using the client's own CPU.

    Supports: .pdf, .md, .txt, .yaml, .yml, .json

    Args:
        path: Path to the local file.

    Returns:
        Extracted text as a string.

    Raises:
        ValueError: If the file format is unsupported or extraction fails.
        ImportError: If pdfplumber is not installed (for PDF files).
    """
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _extract_pdf_text(path)
    elif ext in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="replace")
    elif ext in (".yaml", ".yml"):
        return _extract_yaml_text(path)
    elif ext == ".json":
        return _extract_json_text(path)
    else:
        # Try reading as plain text for unknown extensions
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise ValueError(
                f"Unsupported file format '{ext}'. "
                "Supported: .pdf, .md, .txt, .yaml, .yml, .json"
            ) from exc


def _extract_pdf_text(path: Path) -> str:
    """
    Extract text from a PDF using pdfplumber (text layer only).

    This is a lightweight extraction — it reads the text layer of the PDF
    without OCR.  For scanned/image-only PDFs, the result may be empty or
    sparse.  In that case, consider using the server-side pipeline
    (fetch_mode="server") which includes RapidOCR fallback.

    Args:
        path: Path to the PDF file.

    Returns:
        Extracted text as a string.

    Raises:
        ImportError: If pdfplumber is not installed.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber is required for local PDF extraction. "
            "Install it with: pip install pdfplumber\n"
            "Or install the full PDF extras: pip install scrapedatshi[pdf]\n"
            "Alternatively, use fetch_mode='server' to have the server parse the PDF."
        )

    import io

    pdf_bytes = path.read_bytes()
    output_blocks: list[str] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # Extract tables first
            tables = page.extract_tables()
            table_bboxes = (
                [t_obj.bbox for t_obj in page.find_tables()] if tables else []
            )

            if table_bboxes:
                remaining = page
                for bbox in table_bboxes:
                    try:
                        remaining = remaining.outside_bbox(bbox)
                    except Exception:
                        pass
                text_content = (
                    remaining.extract_text(x_tolerance=3, y_tolerance=3) or ""
                )
            else:
                text_content = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

            if text_content.strip():
                output_blocks.extend(text_content.splitlines())

            # Add GFM tables
            for table_rows in tables:
                if not table_rows:
                    continue
                cleaned = [
                    [str(cell).strip() if cell is not None else "" for cell in row]
                    for row in table_rows
                ]
                output_blocks.append("")
                output_blocks.append(_table_to_gfm(cleaned))
                output_blocks.append("")

            output_blocks.append("")  # blank line between pages

    text = "\n".join(output_blocks).strip()

    if not text:
        # PDF has no text layer — warn the user
        import warnings

        warnings.warn(
            f"No text could be extracted from '{path.name}'. "
            "This PDF may be a scanned image-only document. "
            "For OCR support, use fetch_mode='server' which includes RapidOCR fallback.",
            stacklevel=4,
        )

    return text


def _table_to_gfm(rows: list[list[str]]) -> str:
    """Convert a list of rows to a GFM markdown table."""
    if not rows:
        return ""

    col_count = max(len(row) for row in rows)
    padded = [row + [""] * (col_count - len(row)) for row in rows]
    col_widths = [
        max(len(str(padded[r][c])) for r in range(len(padded)))
        for c in range(col_count)
    ]
    col_widths = [max(w, 3) for w in col_widths]

    def fmt_row(row: list[str]) -> str:
        cells = [str(row[c]).ljust(col_widths[c]) for c in range(col_count)]
        return "| " + " | ".join(cells) + " |"

    separator = "| " + " | ".join("-" * w for w in col_widths) + " |"
    result_lines = [fmt_row(padded[0]), separator]
    for row in padded[1:]:
        result_lines.append(fmt_row(row))
    return "\n".join(result_lines)


def _extract_yaml_text(path: Path) -> str:
    """Extract text from a YAML file."""
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        return yaml.dump(data, default_flow_style=False, allow_unicode=True)
    except ImportError:
        # PyYAML not installed — read as plain text
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return path.read_text(encoding="utf-8", errors="replace")


def _extract_json_text(path: Path) -> str:
    """Extract text from a JSON file."""
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return path.read_text(encoding="utf-8", errors="replace")

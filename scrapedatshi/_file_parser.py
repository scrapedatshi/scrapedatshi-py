"""
scrapedatshi._file_parser
~~~~~~~~~~~~~~~~~~~~~~~~~
Local file text extraction helpers.

These functions run on the CLIENT machine — not on the scrapedatshi server.
They extract plain text from local files so the heavy CPU work stays off
the server. The extracted text is then submitted to /v1/process-text for
chunking.

Supported formats:
    .pdf              — pdfplumber (text layer) with basic fallback
    .md, .txt, .text  — read as-is
    .yaml, .yml       — YAML → formatted text
    .json             — JSON → formatted text
    .csv              — CSV rows → text blocks
    .xlsx, .xls       — Excel sheets → text (requires openpyxl)
    .docx             — Word documents (requires python-docx)
    .ipynb            — Jupyter notebooks (code + markdown cells)
    .html, .htm       — HTML stripped to text
    .xml              — XML text content
    .toml, .ini, .cfg — config files (plain text)
    .py, .js, .ts, .jsx, .tsx, .sql, .go, .rb, .java,
    .cs, .cpp, .c, .rs, .php, .sh, .bash, .zsh,
    .r, .swift, .kt, .scala — code files (plain text)

Dependencies:
    pdfplumber is required for PDF extraction.
    openpyxl is required for .xlsx/.xls extraction.
    python-docx is required for .docx extraction.
"""

from __future__ import annotations

from pathlib import Path

# Code and config file extensions — read as plain text
_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".sql",
    ".go",
    ".rb",
    ".java",
    ".cs",
    ".cpp",
    ".c",
    ".rs",
    ".php",
    ".sh",
    ".bash",
    ".zsh",
    ".r",
    ".swift",
    ".kt",
    ".scala",
    ".toml",
    ".ini",
    ".cfg",
    ".text",
}


def _guess_source_type(path: Path) -> str:
    """Return a short source type string based on file extension."""
    ext = path.suffix.lower()
    mapping = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".txt": "text",
        ".text": "text",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".csv": "csv",
        ".xlsx": "excel",
        ".xls": "excel",
        ".docx": "docx",
        ".ipynb": "notebook",
        ".html": "html",
        ".htm": "html",
        ".xml": "xml",
    }
    if ext in _CODE_EXTENSIONS:
        return "code"
    return mapping.get(ext, "text")


def _extract_file_text_locally(path: Path) -> str:
    """
    Extract plain text from a local file using the client's own CPU.

    Supports all common document, spreadsheet, notebook, and code file types.

    Args:
        path: Path to the local file.

    Returns:
        Extracted text as a string.

    Raises:
        ImportError: If a required optional dependency is not installed.
    """
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _extract_pdf_text(path)
    elif ext in (".md", ".txt", ".text"):
        return path.read_text(encoding="utf-8", errors="replace")
    elif ext in (".yaml", ".yml"):
        return _extract_yaml_text(path)
    elif ext == ".json":
        return _extract_json_text(path)
    elif ext == ".csv":
        return _extract_csv_text(path)
    elif ext in (".xlsx", ".xls"):
        return _extract_excel_text(path)
    elif ext == ".docx":
        return _extract_docx_text(path)
    elif ext == ".ipynb":
        return _extract_notebook_text(path)
    elif ext in (".html", ".htm"):
        return _extract_html_text(path)
    elif ext == ".xml":
        return _extract_xml_text(path)
    else:
        # Code files, config files, and any other text-based format
        return path.read_text(encoding="utf-8", errors="replace")


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


def _extract_csv_text(path: Path) -> str:
    """Extract text from a CSV file — converts rows to readable text blocks."""
    try:
        import csv
        import io

        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return text
        lines: list[str] = []
        for i, row in enumerate(rows, 1):
            row_text = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
            if row_text.strip():
                lines.append(f"Row {i}: {row_text}")
        return "\n".join(lines) if lines else text
    except Exception:
        return path.read_text(encoding="utf-8", errors="replace")


def _extract_excel_text(path: Path) -> str:
    """Extract text from an Excel file (.xlsx/.xls). Requires openpyxl."""
    try:
        import openpyxl  # type: ignore

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        all_text: list[str] = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            sheet_lines: list[str] = [f"## Sheet: {sheet_name}"]
            for row in ws.iter_rows(values_only=True):
                row_text = " | ".join(str(cell) for cell in row if cell is not None)
                if row_text.strip():
                    sheet_lines.append(row_text)
            if len(sheet_lines) > 1:
                all_text.append("\n".join(sheet_lines))
        wb.close()
        return "\n\n".join(all_text) if all_text else ""
    except ImportError:
        raise ImportError(
            "openpyxl is required for Excel file extraction. "
            "Install it with: pip install openpyxl"
        )
    except Exception as exc:
        return f"[Excel parse error: {exc}]"


def _extract_docx_text(path: Path) -> str:
    """Extract text from a Word document (.docx). Requires python-docx."""
    try:
        import docx  # type: ignore

        doc = docx.Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(
                    cell.text.strip() for cell in row.cells if cell.text.strip()
                )
                if row_text:
                    paragraphs.append(row_text)
        return "\n\n".join(paragraphs) if paragraphs else ""
    except ImportError:
        raise ImportError(
            "python-docx is required for Word document extraction. "
            "Install it with: pip install python-docx"
        )
    except Exception as exc:
        return f"[DOCX parse error: {exc}]"


def _extract_notebook_text(path: Path) -> str:
    """Extract text from a Jupyter notebook (.ipynb)."""
    try:
        import json as _json

        nb = _json.loads(path.read_text(encoding="utf-8", errors="replace"))
        cells = nb.get("cells", [])
        blocks: list[str] = []
        for cell in cells:
            cell_type = cell.get("cell_type", "")
            source = cell.get("source", [])
            if isinstance(source, list):
                source = "".join(source)
            if not source.strip():
                continue
            if cell_type == "markdown":
                blocks.append(source)
            elif cell_type == "code":
                blocks.append(f"```python\n{source}\n```")
        return "\n\n".join(blocks) if blocks else ""
    except Exception:
        return path.read_text(encoding="utf-8", errors="replace")


def _extract_html_text(path: Path) -> str:
    """Extract plain text from an HTML file (strips tags)."""
    try:
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self._parts: list[str] = []
                self._skip = False

            def handle_starttag(self, tag: str, attrs: list) -> None:
                if tag in ("script", "style"):
                    self._skip = True

            def handle_endtag(self, tag: str) -> None:
                if tag in ("script", "style"):
                    self._skip = False

            def handle_data(self, data: str) -> None:
                if not self._skip and data.strip():
                    self._parts.append(data.strip())

        extractor = _TextExtractor()
        extractor.feed(path.read_text(encoding="utf-8", errors="replace"))
        return " ".join(extractor._parts)
    except Exception:
        return path.read_text(encoding="utf-8", errors="replace")


def _extract_xml_text(path: Path) -> str:
    """Extract text content from an XML file."""
    try:
        from xml.etree import ElementTree as ET

        tree = ET.parse(str(path))
        root = tree.getroot()
        texts = [
            elem.text.strip() for elem in root.iter() if elem.text and elem.text.strip()
        ]
        return "\n".join(texts) if texts else ""
    except Exception:
        return path.read_text(encoding="utf-8", errors="replace")

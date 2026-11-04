# Read rich documents during chat

Run normal chat on the **BCM client**. Files must be readable by the current user on that client. The GPU host only receives model requests; files stored only on that host are not automatically visible. You may name the project directory or another local directory explicitly.

This feature is on main and is not included in the existing v1.2.0 tag. For an existing installation, download the main source archive and use the program-only updater (see [update guide](update.md)):

```bash
cd /raid/local-ai
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/heads/main.tar.gz -o /tmp/local-ai-main.tar.gz
python3 scripts/update.py --root /raid/local-ai --archive /tmp/local-ai-main.tar.gz
```

## Setup and use

On the BCM installation:

```bash
cd /raid/local-ai
./local-ai document doctor
```

DOCX, XLSX, PPTX and OpenDocument text extraction use the Python standard library. PDF, legacy Office and visual layout reading need system converters on the client. Ubuntu/Debian:

```bash
sudo apt-get install --no-install-recommends poppler-utils libreoffice-writer libreoffice-calc libreoffice-impress
./local-ai document doctor
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project
```

In the conversation, ask:

> Read the PDF, Word, Excel and PowerPoint files under /home/alice/project/materials. Summarize deployment requirements with source files, pages, sheets or slides. Inspect rendered pages when charts matter.

No attachment startup flag is required. New chats and chats resumed through local-ai connect the documents_read_document tool automatically. Exit an already-open client and re-enter after upgrading. The client-side tool does not require restarting the GPU service.

## Formats and behavior

| Format | Default reading | Visual layout |
|---|---|---|
| PNG, JPEG, WebP, GIF | Images sent to an image-capable model | Animation and complex image cases need separate evaluation |
| PDF | Selected page text and page images, including scans | render returns page images |
| DOCX/DOCM | Body/table text and headers/footers; no macro execution | LibreOffice to PDF and page rendering |
| XLSX/XLSM | Sheet names/visibility, cell addresses, raw values, formulas and cached values; no macro execution | LibreOffice to PDF for charts/layout |
| PPTX/PPTM | Relationship-ordered slide text and notes; no macro execution | LibreOffice to PDF for slide images |
| DOC, XLS, PPT, RTF | LibreOffice to PDF, then text and page images | Same |
| ODT, ODS, ODP | Body or table/page text | LibreOffice to PDF |
| UTF-8 text, Markdown, CSV/TSV, JSON, HTML/XML, source code | Text; no web loading or script execution | No browser layout rendering |

Codex's common document workflows are a usability reference, not a claim of identical format coverage, layout fidelity or recognition accuracy. Encrypted files, complex layouts, embedded objects, formula display and unusual fonts may need additional processing. Audio, video and arbitrary binaries are not promised.

The default selection is 3 pages/sheets/slides. Tool start is one-based; count is 1–5. Text is limited to 40,000 characters per call, with next_offset for continuation. Body text without reliable page boundaries is labelled as body text, not invented page numbers. The assistant must continue reading when the task requires it. Input files are limited to 100 MiB; each returned image to 8 MiB.

Spreadsheet text extraction does not evaluate formulas. Cached values may be stale and dates may retain serial values. Validate calculations separately. Office rendering may recalculate or alter display; the source file is not modified. Scans use visual recognition, so check critical numbers and tables against the original page.

## Diagnostics

Normal users ask in chat; these commands are optional diagnostics:

```bash
./local-ai document read /home/alice/project/materials/manual.pdf --mode text --start 1 --count 2
```

document read returns tool-result JSON. auto/render may contain base64 images; chat handles them automatically. --offset is a character offset within the selected range. CLI failures return nonzero; tool failures use isError=true with the actual error.

doctor reports pdf_ready and office_render_ready. Install missing converters on the **client**; do not re-download weights. The model recipe must declare image in modalities.input. Text-only models can use text mode for extractable text, but cannot interpret scans/charts.

The Log path printed at session start stores calls and errors. Document contents are reference data, never execution authorization.

## Offline environments

local-ai export includes the document tool's source, but not host-installed Poppler/LibreOffice. Provision those dependencies on the target BCM using a matching distribution/architecture repository, offline package mirror or administrator-prepared host, then run document doctor. Copying another host's /usr/bin executables is not a complete offline installation.

[中文版](../documents.md)

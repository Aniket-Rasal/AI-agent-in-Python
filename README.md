# MCA Companies Act Document Agent

A Python agent for discovering and processing Companies Act, 2013 documents. It has separate MCA and local PDF sources that feed a shared validation, hashing, OCR, classification, and SQLite pipeline.

## Project overview

The assignment is to run a Python agent on a 30-minute schedule, collect up to 100 Companies Act, 2013 PDFs, organize them by document type, and extract searchable text with OCR. Most processing requirements are implemented and tested. Automated MCA acquisition remains blocked by HTTP 403 from the portal.

## Assignment objectives

- Schedule the agent every 30 minutes and stop at 100 unique, successful PDFs.
- Discover public MCA PDF documents and classify them into separate folders.
- Extract embedded text and use Tesseract OCR for scanned pages; optionally use AWS Textract.
- Persist processing state, duplicates, and failures so work can resume after restart.
- Demonstrate the local processing workflow without presenting it as an MCA download.

## Verified status and MCA Access Limitation

- **Local processing verified:** the included Companies Act PDF was imported, its text was extracted, it was classified into `Acts`, and its category copy and SQLite record were created.
- **MCA public pages inspected:** normal browser navigation displayed MCA's public homepage, its Notifications & Updates area, and visible public PDF links.
- **Automated MCA access not verified:** a direct HTTP GET to MCA returned HTTP 403, and the local automated browser has also returned 403. The application reports this as `MCA document discovery unavailable: HTTP 403` and stops that discovery cycle.
- **No access bypass:** this project does not bypass CAPTCHA, authentication, or anti-bot restrictions; it does not use undocumented/private endpoints.
- **Local demo is not MCA downloading:** the local source and `--demo` report `LOCAL` / `LOCAL DEMO` explicitly. Their success demonstrates the downstream pipeline only. Automatic MCA discovery and downloading remain unverified.

Automated MCA discovery/download could not be verified because the MCA portal returned HTTP 403 to the automated client. The implementation does not bypass this restriction. Live public-UI pagination could not be inspected while MCA access returned 403, so discovery coverage and pagination remain unverified. The bounded static HTML crawler follows linked HTML pages where present; this is not evidence that all MCA documents are found.

The public MCA homepage exposes visible update sections and PDF entries, but a browser being able to display those links does not establish that the agent can fetch them from its runtime environment. The MCA source filters visible candidate titles/source URLs for Companies Act relevance before downloading. This may miss related records whose titles do not mention the Act. The only documented fallback is to save public PDFs through the regular browser and import them locally.

## Architecture

```text
DocumentSource
  +-- MCADocumentSource  public MCA homepage/categories and visible document links
  +-- LocalDocumentSource PDFs in LOCAL_PDF_DIR or a one-file demo
             |
             v
  PDF validation -> SHA-256 duplicate check -> raw storage -> OCR/text extraction
             -> rule-based document type -> category copy -> SQLite status
```

`app/sources` defines the source interface and its MCA/local implementations. `app/discovery` finds public MCA candidates, `app/downloader` validates and stages PDFs, `app/ocr` handles embedded text and OCR providers, `app/classifier` applies document type rules, `app/database` stores restart-safe state, and `app/agent` coordinates processing and the document cap.

## Project structure

```text
app/                 Agent, sources, discovery, downloader, OCR, classifier, SQLite
tests/               Unit and workflow tests; MCA access is mocked
samples/             Companies Act PDF fixture for the local demo
data/                Runtime PDFs, category folders, OCR text, SQLite, and logs (gitignored)
run.py               Command-line entry point
README.md             Setup, operation, limitations, and verification
DESIGN.md             Architecture and design decisions
```

Original PDFs are kept at `data/downloads/raw/`. Classified copies are placed in `data/documents/<Category>/`. Extracted text is kept at `data/ocr/text/`. The SQLite database and JSON-lines logs are under `data/metadata/` and `data/logs/`.

## Installation

Requirements: Python 3.11+, Playwright Chromium for MCA UI discovery, and the Tesseract executable for scanned PDFs when using local OCR.

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

## Dependencies

`requirements.txt` contains Requests, PyMuPDF, pytesseract, Pillow, and Playwright. `requirements-dev.txt` adds pytest. `requirements-aws.txt` adds boto3 for the optional AWS Textract provider. Python package installation alone does not install the Tesseract executable or Playwright Chromium; follow the setup commands above.

Install Tesseract for Windows and ensure `tesseract.exe` is available on `PATH`. PDFs that already contain enough embedded text are read by PyMuPDF and do not require the Tesseract executable.

## Configuration

Environment variables can be set in `.env` or in the shell. Shell variables take precedence.

| Setting | Default | Purpose |
| --- | --- | --- |
| `MAX_DOCUMENTS` | `100` | Maximum unique, successfully validated PDF contents in the selected database. |
| `INTERVAL_MINUTES` | `30` | Delay after each completed scheduled cycle. `1` can be used for a short scheduling check. |
| `LOCAL_PDF_DIR` | `./data/inbox` | Folder scanned by `--source local`. |
| `DATA_DIR` | `./data` | Root folder for source PDFs, categorized copies, OCR output, state, and logs. |
| `OCR_PROVIDER` | `tesseract` | `tesseract` or `textract`. |
| `AWS_REGION` | unset | AWS region used by Textract. |
| `MCA_BASE_URL` | `https://www.mca.gov.in/` | Official MCA host; other hosts are rejected. |
| `REQUEST_TIMEOUT_SECONDS` | `20` | Timeout for MCA page and document requests. |
| `REQUEST_DELAY_SECONDS` | `2` | Delay between public page interactions. |
| `DISCOVERY_MAX_PAGES` | `40` | Bound for the HTTP HTML discovery path. |
| `DISCOVERY_MAX_DEPTH` | `2` | Crawl depth for that path. |
| `OCR_MAX_PDF_PAGES` | `100` | Page limit per PDF. |
| `OCR_MIN_TEXT_CHARS` | `80` | Minimum embedded text threshold before OCR is considered. |

## Run locally

Put PDFs in `data/inbox/` (or the folder configured by `LOCAL_PDF_DIR`) and run one local-source cycle:

```powershell
python run.py --source local --once
```

Run the local source on the configured schedule:

```powershell
python run.py --source local
```

The local source never labels a file as an MCA download. To manually download public PDFs using a regular browser and then process them:

```powershell
python run.py --import-dir "C:\Users\ANIKET\Downloads\MCA-PDFs"
```

One PDF can be imported with:

```powershell
python run.py --import-pdf "C:\Users\ANIKET\Downloads\CompaniesAct2013.pdf" --title "Companies Act, 2013"
```

## Run the MCA source

One discovery/download cycle:

```powershell
python run.py --source mca --once
```

Keep it running on the scheduler:

```powershell
python run.py --source mca
```

Each process runs its first cycle immediately, then waits `INTERVAL_MINUTES` after completion. SQLite leases prevent overlapping local cycles. If MCA responds with HTTP 403, the application logs `MCA document discovery unavailable: HTTP 403` and does not claim discovery succeeded. In the current observed runtime, automated MCA collection is blocked by that response.

## Deterministic demo

The project includes a public Companies Act PDF at `samples/Companies Act, 2013.pdf`. Run:

```powershell
python run.py --demo
python run.py --status
```

Each demo invocation uses a fresh SQLite database named `data/demo_state/companies-act-demo-<run-id>.sqlite3`, so each run processes the sample and repeated demos do not affect the MCA collection counter. It writes the usual document artifacts to the configured `DATA_DIR`, including `data/documents/Acts/`. Its summary reports the isolated demo database. `python run.py --status` reports the main collection database. Expected demo console output includes:

```text
MCA AI DOCUMENT AGENT
Source: LOCAL DEMO
Discovered: 1
Downloaded: 1
OCR Processed: 1
Classified: 1
Errors: 0
Classification:
  Acts: 1
Document limit: 1 / 100
Status: SUCCESS
```

This is a **local PDF processing demonstration**, not an MCA download demonstration.

## OCR setup

PyMuPDF first extracts text already embedded in the PDF. If the total text falls below `OCR_MIN_TEXT_CHARS`, the Tesseract provider renders pages incrementally and calls the local Tesseract OCR engine through `pytesseract`. OCR output is stored per document in `data/ocr/text/`, and `ocr_status` is saved in SQLite. OCR errors are recorded for the affected document; the agent continues to classification and the next candidate.

## Optional AWS Textract

Tesseract is a local OCR engine. Amazon Textract is a separate AWS-managed OCR service, not “AWS Tesseract.” To use Textract:

```powershell
python -m pip install -r requirements-aws.txt
```

Set `OCR_PROVIDER=textract` and `AWS_REGION` in `.env`, then configure AWS credentials through the standard AWS credential chain. The provider sends rendered page images to Textract. AWS account access and request charges apply.

## Classification

Document title and extracted text are checked against ordered keyword rules. Supported categories are `Acts`, `Notifications`, `Circulars`, `Rules`, `Orders`, `Amendments`, and `Other`. Title matches get `rule_score=0.95`; body-text matches get `rule_score=0.75`; unmatched documents go to `Other` with `rule_score=0.35`. These are **heuristic rule weights**, not validated ML confidence scores. The classification is a filing aid and should be reviewed when accuracy matters.

## SQLite state, duplicates, and 100-document limit

Each record stores `source_url`, `source_kind` (`MCA`, `LOCAL`, or `LOCAL DEMO`), title, local path, SHA-256, document type, download/OCR/classification/processing status, timestamps, and any error. The schema is created and upgraded automatically. Pending downloaded files can be resumed:

```powershell
python run.py --process-existing
```

Content SHA-256 is used to detect duplicate PDFs from different source records. Only unique validated PDFs with `download_status=success` count toward `MAX_DOCUMENTS`. Failed transfers, duplicate content, and invalid PDFs do not add to the count. The cap and completed count persist across restarts as long as the same SQLite database is retained. The demo uses separate SQLite state intentionally.

View status and logs:

```powershell
python run.py --status
Get-Content .\data\logs\agent.log -Tail 30
```

Status includes `discovery_errors` for source-level failures such as MCA HTTP 403. These are recorded as agent events; they do not create fake document rows or increase download counts.

## Logging

The app writes JSON-lines log events to the console and `data/logs/agent.log`. Records include discovery results, source-level failures, transfer/hash decisions, OCR, classification, and errors. MCA discovery failures are retained in SQLite and appear in `python run.py --status` as `discovery_errors`.

## Security considerations

MCA URLs are restricted to HTTPS on the official MCA host. The collector stops when the portal returns an access challenge and does not bypass CAPTCHA, authentication, anti-bot controls, or use private/undocumented endpoints. Local import validates the PDF but does not assert its provenance. AWS credentials are not stored in the repository; Textract uses boto3's standard credential chain.

## Tests

Install the development requirements and run the suite:

```powershell
python -m pytest
```

Tests use mocked MCA responses and local PDF fixtures; they do not repeatedly contact MCA or download a hundred real documents. They cover the 100 unique document cap, failed and duplicate downloads, restart state, OCR behavior/failure, classification, the local source/demo, scheduler interval, and the mocked MCA 403 response.

## Current limitations and next steps

- Automated MCA discovery/download remains blocked by HTTP 403 in this runtime; public normal-browser access has been observed separately.
- The agent currently supports the public MCA homepage's visible update categories and their PDF links. It does not establish complete coverage of every historic Companies Act-related document.
- Broader automated access requires an MCA-approved route, such as an explicitly supported download/API mechanism or permission from the portal owner. Until then, browser download plus local import is the supported fallback.
- Rule-based classification and OCR can make errors; review category and extracted text for important documents.

See [README_AGENT_REQUIREMENTS.md](README_AGENT_REQUIREMENTS.md) for the assignment-oriented demonstration walkthrough and [DESIGN.md](DESIGN.md) for design details.

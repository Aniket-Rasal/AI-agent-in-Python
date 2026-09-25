# MCA Companies Act Agent: Requirements and Demonstration

This document describes the Python agent built for the Companies Act, 2013 document collection use case, how to run it, and how to demonstrate its working pipeline.

## What the agent does

- Checks the public MCA website for PDF documents exposed in the homepage's public Notifications & Updates sections. The Companies Act, 2013 PDF is also included as a seed candidate.
- Validates downloaded or locally imported PDFs, records a SHA-256 hash, and tracks progress in SQLite.
- Extracts embedded PDF text and uses OCR for scanned pages when needed.
- Classifies each document into a category folder, such as `Acts`, `Notifications`, `Circulars`, `Rules`, `Orders`, `Amendments`, or `Other`.
- Runs one cycle immediately, then waits 30 minutes between cycles in continuous mode.
- Stops when the database contains 100 unique successful PDF downloads. Duplicate files and failed transfers do not count toward the limit.

The cap and interval can be changed using `MAX_DOCUMENTS` and `INTERVAL_MINUTES` in `.env`; their defaults are `100` and `30`.

## Requirements

- Python 3.11 or newer.
- Playwright's Chromium browser for public MCA pages: `python -m playwright install chromium`.
- Tesseract OCR executable installed and on `PATH` for scanned PDFs when using the default OCR provider.
- MCA access from the machine running the agent. Public site availability can vary by browser, network, and access controls.

Install Python packages from PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

## Run the agent

Run one discovery and processing cycle:

```powershell
python run.py --once
```

Run continuously. The agent starts a cycle immediately and waits 30 minutes after that cycle finishes before starting the next one. It exits when the 100-document limit is reached. Press `Ctrl+C` to stop it manually.

```powershell
python run.py
```

Check its persisted counts at any time:

```powershell
python run.py --status
```

Resume OCR and classification for downloaded PDFs that are still pending, without discovering new documents:

```powershell
python run.py --process-existing
```

## Demonstrate the working document pipeline

The MCA portal has returned HTTP 403 to the agent's automated browser in the observed run. When that happens, download the public PDFs through your regular browser into a folder, then import that folder. This uses the same PDF validation, duplicate tracking, OCR, categorization, and 100-document counter as an agent download.

To make a clean demonstration without changing the project's existing database, point this demo at a separate data directory. Use a folder containing one or more MCA PDFs:

```powershell
$env:DATA_DIR = ".\demo-data"
python run.py --import-dir "C:\Users\ANIKET\Downloads\MCA-PDFs"
python run.py --status
Get-ChildItem .\demo-data\documents -Recurse -File
Get-Content .\demo-data\logs\agent.log -Tail 30
```

For a single PDF, use:

```powershell
python run.py --import-pdf "C:\Users\ANIKET\Downloads\CompaniesAct2013.pdf" --title "Companies Act, 2013"
```

Expected evidence of a successful run:

1. The log reports a successful PDF import or download.
2. The log reports OCR/text extraction and a classification category.
3. `python run.py --status` shows the successful unique download and processing counts.
4. The PDF appears under `demo-data\documents\<Category>\` and extracted text under `demo-data\ocr\text\`.

The single-PDF import was demonstrated with the Companies Act PDF: the application reported a 3,276,594-byte import, completed text extraction/OCR processing, and classified it as `Acts` with a rule-based score of `0.95`. The score is a heuristic title-match weight, not ML confidence. The categorized copy is stored under `data\documents\Acts\` in the project's current data directory.

To demonstrate automatic discovery as well, run `python run.py --once` and show the discovery and download logs. If the MCA site returns 403, show that error as the current access limitation; then demonstrate the complete processing pipeline with `--import-dir` or `--import-pdf`. A regular browser being able to open the website does not guarantee that an automated browser session from another process or network will receive the same access.

## Document storage

```text
data/
  downloads/raw/       Validated original PDFs named by SHA-256
  documents/Acts/      Categorized copies
  documents/Notifications/
  documents/Circulars/
  documents/Rules/
  documents/Orders/
  documents/Amendments/
  documents/Other/
  ocr/text/            Extracted text, one text file per document
  metadata/            SQLite processing and 100-document count
  logs/                JSON-lines application log
```

The 100-document count is stored in the SQLite database under the configured data directory. Keep that database to retain the count across restarts. Starting with a new `DATA_DIR` creates an independent counter.

## OCR choices: Tesseract and AWS Textract

'AWS Tesseract' combines two different OCR options. **Tesseract** is the local open-source OCR engine; this project calls it through the Python `pytesseract` wrapper. PyMuPDF first checks for text already embedded in the PDF and renders pages to images only when OCR is needed. Tesseract is the default and does not require an AWS account.

**Amazon Textract** is AWS's managed OCR service, not a version of Tesseract. This project has an optional Textract provider that sends rendered page images to AWS using `boto3`. It needs AWS credentials and a configured region, and AWS may charge for requests.

To select Textract:

```powershell
python -m pip install -r requirements-aws.txt
```

Then set `OCR_PROVIDER=textract` and `AWS_REGION=ap-south-1` (or a region enabled for your account) in `.env`, and configure AWS credentials using the standard AWS credential chain. Leave `OCR_PROVIDER=tesseract` for local OCR.

## Current limitations

- The demonstrated local run of automated MCA discovery returned HTTP 403 for the homepage. Automatic download of all related MCA documents is therefore not confirmed working in that environment. Use browser downloads plus `--import-dir` while access is blocked.
- Discovery is limited to PDF links the public MCA pages expose to the agent. It cannot guarantee that every Companies Act-related document across all MCA pages and archives has been found.
- The agent does not log in, solve CAPTCHA, or bypass MCA access restrictions.
- Classification uses document titles and extracted text; it is a filing aid and may need manual review.
- The 100 limit counts unique validated PDF content recorded in the configured SQLite database, not merely files copied into a folder.

See [README.md](README.md) for the complete project setup and [DESIGN.md](DESIGN.md) for architecture and design decisions.

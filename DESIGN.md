# Design

## Architecture

`run.py` selects a `DocumentSource` and creates an `AgentRunner`. The source discovers candidate records and supplies PDF bytes or a local path to the common processing workflow:

```text
DocumentSource
  |-- MCADocumentSource
  `-- LocalDocumentSource
        -> validate PDF -> SHA-256 deduplication -> publish original
        -> extract text/OCR -> classify -> category copy -> persist status
```

Source records carry a `source_kind` field so MCA collection and local demonstrations remain distinguishable. Local demo state uses a separate database; its PDF artifact still follows the normal raw/OCR/category layout.

## Source abstraction and MCA discovery

`app/sources/base.py` defines the discover/download/close interface. `MCADocumentSource` composes `MCADiscovery`, `MCAWebPortal`, and `DocumentDownloader`. It inspects public homepage update categories and follows visible PDF links through Chromium. It restricts URLs to the official MCA HTTPS host. Candidates are filtered by visible title/source text for Companies Act relevance; related records without those title signals may be missed. `LocalDocumentSource` enumerates PDFs in `LOCAL_PDF_DIR` or a specified one-file demo input and passes them through the same PDF validation and downstream pipeline.

Public MCA investigation found ordinary visible update categories, search/filter controls, and PDF links on the MCA homepage. A direct HTTP request from the agent environment returned 403. A normal browser session displayed the public page and visible links, but that does not grant the app's automated session access. When the agent receives 403, it reports discovery unavailable and does not claim success. It does not bypass CAPTCHA, authentication, anti-bot controls, or use undocumented/private endpoints.

`--source mca` selects the MCA implementation; `--source local` selects `LOCAL_PDF_DIR`. `--demo` uses the included Companies Act PDF and isolated SQLite demo state. The local source is never presented as MCA acquisition.

## Download and file safety

MCA requests and browser candidates are restricted to HTTPS MCA domains. PDFs must have a `%PDF-` signature and pass PyMuPDF readability checks when installed. Files are staged to a temporary location, hashed, then atomically published to `data/downloads/raw/<sha256>.pdf`. External redirect targets are rejected. Local PDFs use equivalent validation and hashing without a network request.

## OCR architecture

PyMuPDF extracts embedded text before image OCR is considered. If the total extracted text is below a configured threshold, the Tesseract provider renders bounded pages and calls `pytesseract`. `OCRProvider` abstracts extraction; `AWSTextractOCRProvider` optionally sends rendered page images through boto3 and Amazon Textract. OCR text is stored at `data/ocr/text/<document-id>.txt`, with status and errors persisted. An OCR exception is isolated to one document and does not prevent the following candidate from being processed.

## Classification

The deterministic classifier checks document title before extracted body text. Ordered indicators choose among `Amendments`, `Notifications`, `Circulars`, `Orders`, `Rules`, and `Acts`; unmatched documents become `Other`. The returned `rule_score` is a rule weight (title match 0.95, body match 0.75, fallback 0.35), not a calibrated probability or ML confidence. The rationale is logged. Category output is a filing aid and can need review.

## Database and restart behavior

SQLite is the source of truth. Documents store source URL and source kind, title, local path, SHA-256, byte size, type, download/OCR/classification/processing statuses, timestamps, OCR text path, and error text. Agent-level failures such as discovery HTTP 403 are stored in `agent_events` and exposed separately as `discovery_errors` in status. Schema initialization performs a migration for the `source_kind` column on existing databases. Unique source URLs prevent relisting the same candidate; successful SHA-256 hashes catch identical content listed at multiple URLs.

Originals, OCR output, category copies, SQLite state, and logs are separate under `DATA_DIR`. Pending successful downloads are resumed after a restart. Failed downloads and OCR errors are retained for inspection. The 100-document count is the number of unique successful hashes in the selected database and survives restarts when that database is retained.

## Scheduling

Without a one-shot mode, the scheduler runs one cycle immediately and waits `INTERVAL_MINUTES` after that cycle completes. The default is 30 minutes; tests can set it to 1 minute. This is a completion-to-next-start delay, so cycle duration is additional time between starts. A SQLite lease protects against overlapping local cycles and a heartbeat renews the lease while processing. The scheduler exits when the unique successful document cap is reached.

## Failure handling and logging

Discovery errors are logged, written to SQLite `agent_events`, and returned as unavailable rather than converted into an apparent discovery success. For MCA 403 the message is `MCA document discovery unavailable: HTTP 403`. Individual download or OCR failures are recorded against their document; they do not increment the unique count. JSON-lines logs go to the console and `data/logs/agent.log`. Secrets and browser session data are not collected or logged.

## Tests

Offline tests use fake responses, deterministic local PDFs, and a fake clock/wait event where appropriate. They cover hashing, persistence, duplicate content, failed download counts, exact 100-document stopping and restart behavior, OCR provider paths and errors, rule categories, scheduler cadence, local source/demo, and mocked MCA 403 handling. No test downloads real MCA documents.

## Security considerations

- Only visible, public document links on the official MCA host are eligible for automated acquisition.
- The crawler stops on HTTP 403/access challenges. It does not spoof tokens, authenticate, solve CAPTCHA, bypass anti-bot measures, or replay private endpoints.
- Local import validates PDFs and records them as `LOCAL`; it does not assert their provenance.
- Textract requires user-managed AWS credentials and may incur per-request charges. Credentials are obtained through boto3's normal credential chain and are not committed.
- Filenames are generated from safe title stems and stable document identifiers; remote URL path fragments are not used as filesystem paths.

## MCA limitation and future improvement

Automatic MCA collection has not been demonstrated because direct HTTP and the application's automated browser received HTTP 403 from this runtime. A separate regular browser displayed the public homepage. The safe next step for unattended MCA collection is to obtain an MCA-approved API or bulk-access method, or authorization for the app's origin. Until then, use regular browser downloads and `--import-dir`. With approved access, expand discovery to all relevant public categories and date/search pages, store pagination/crawl progress, and verify coverage without bypassing access controls.

# Submission Checklist

## Functional

- [x] Python agent and selectable MCA/local document sources
- [x] 30-minute scheduler (first cycle runs immediately; interval follows cycle completion)
- [x] 100-document unique successful PDF limit
- [x] OCR pipeline and OCR status persistence
- [x] Tesseract provider implemented; the scanned-page call path is covered with a mocked OCR engine
- [x] Optional AWS Textract provider implemented; covered with a mocked boto3 client, not a live AWS account
- [x] Rule-based document classification with honest `rule_score` naming
- [x] Category folders: Acts, Notifications, Circulars, Rules, Orders, Amendments, Other
- [x] SHA-256 duplicate detection
- [x] SQLite state, restart handling, schema migration, and source-level discovery error events
- [x] JSON-lines logging
- [x] Tests
- [ ] Automated MCA download (blocked: automated client received HTTP 403)


## Evidence

Run from the project directory after installing `requirements-dev.txt` and Playwright Chromium:

```powershell
python -m pytest
```

Expected current result: `44 passed`. Tests use local fixtures and mocked MCA responses; they do not download 100 real MCA documents.

Run the deterministic local demonstration:

```powershell
python run.py --demo
```

Expected result: `Source: LOCAL DEMO`, `Discovered: 1`, `Downloaded: 1`, `OCR Processed: 1`, `Classified: 1`, `Errors: 0`, and `Acts: 1`. The resulting category copy is under `data/documents/Acts/`. Each demo run uses a separate database at `data/demo_state/companies-act-demo-<run-id>.sqlite3` and is not an MCA download.

Inspect the main collection state:

```powershell
python run.py --status
```

The current main database contains one previously processed local Companies Act PDF, one historical document-processing error, and one persisted source discovery error from the 403 check: `downloaded: 1`, `ocr_processed: 1`, `classified: 1`, `errors: 1`, `discovered: 2`, `discovery_errors: 1`, `remaining: 99`.

Check the local-folder workflow:

```powershell
$env:LOCAL_PDF_DIR = "C:\path\to\MCA-PDFs"
python run.py --source local --once
```

Check the MCA source only when you want to reproduce the access result:

```powershell
python run.py --source mca --once
```

Observed result in this environment: `MCA document discovery unavailable: HTTP 403` and a nonzero exit code. The implementation stops; it does not work around the response. Direct HTTP returned 403 as well. A separate normal browser displayed MCA's public homepage and update listings.

## Git and video still required

The project folder was not a Git repository at the start of submission preparation. A local repository has now been initialized on `master`, reviewed project files have been staged, and no remote is configured. No commit or push has been made. Configure the intended GitHub remote after choosing the destination, then review the staged files before a human chooses whether to commit or push. Record a 3-5 minute demonstration using [DEMO_SCRIPT.md](DEMO_SCRIPT.md); no video file has been recorded yet.

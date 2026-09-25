# 3-5 Minute Demonstration Script

## 0:00-0:30 | Set expectations

Say: “This is a Python document-processing agent for the Companies Act, 2013. OCR, classification, persistent state, the scheduler, and the 100-document cap are implemented. Automated MCA access is not verified because the automated client receives HTTP 403. The local demo shows the processing pipeline only; it does not represent an MCA download.”

## 0:30-1:00 | Show the repository

Show `app/sources/`, `app/agent/runner.py`, `app/ocr/`, `app/classifier/`, `app/database/`, `tests/`, `samples/`, and the README. Point out `MCADocumentSource` and `LocalDocumentSource` are separate.

## 1:00-1:40 | Run the tests

```powershell
python -m pytest
```

Show the final summary: `36 passed`. Explain that MCA responses are mocked in the tests and no hundred-document MCA download is attempted.

## 1:40-2:30 | Run the local demo

```powershell
python run.py --demo
```

Show these output fields:

```text
Source: LOCAL DEMO
Discovered: 1
Downloaded: 1
OCR Processed: 1
Classified: 1
Errors: 0
  Acts: 1
Document limit: 1 / 100
Status: SUCCESS
```

Say: “This input came from the bundled local sample. It demonstrates validation, text extraction/OCR, classification, and persistence. It is not evidence of an MCA download.”

## 2:30-3:00 | Show files and state

Open `data/documents/Acts/` and show the categorized PDF. Then run:

```powershell
python run.py --status
```

Explain that this command reports the main collection database. The demo uses a separate SQLite database under `data/demo_state/` so it does not alter the main 100-document count.

## 3:00-3:40 | Explain the cap, scheduler, and OCR options

Show `tests/test_agent.py` and point out that the test accepts exactly 100 unique documents, does not start document 101, and verifies the count after reopening SQLite. Explain that `python run.py --source mca` starts immediately and waits 30 minutes after each completed cycle; `INTERVAL_MINUTES=1` is available for a short scheduling check. Tesseract runs locally for scanned pages; Textract is optional and requires AWS credentials and may incur charges.

## 3:40-4:30 | Show the local import and MCA result

Explain the browser-download fallback, then show:

```powershell
$env:LOCAL_PDF_DIR = "C:\path\to\MCA-PDFs"
python run.py --source local --once
```

If reproducing the MCA check, run:

```powershell
python run.py --source mca --once
```

Show the actual response: `MCA document discovery unavailable: HTTP 403`. Say: “The collector records this failure and stops. No CAPTCHA, anti-bot, or access-control bypass was attempted. Automatic MCA downloading remains blocked in this environment.”

## 4:30-5:00 | Close

Summarize: “The local pipeline and requirements around OCR, classification, persistence, scheduling, and the cap are demonstrated. The official MCA pages are publicly visible in a normal browser, but automated collection from this runtime receives HTTP 403. The repository and video still need to be published/recorded for final submission.”

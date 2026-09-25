import tempfile
import unittest
from pathlib import Path

from app.agent.runner import AgentRunner
from app.config import Config
from app.database.repository import Repository
from app.sources.local import LocalDocumentSource


def make_config(root: Path, limit: int = 100) -> Config:
    data = root / "data"
    return Config("https://www.mca.gov.in/", limit, 30, 1, 0, 4, 1, 100, 80, "tesseract", None, data, data / "db.sqlite3", data / "agent.log", "test-agent", data / "inbox")


class FixedOCR:
    def extract_text(self, path: Path) -> str:
        return "Companies Act, 2013"


class SourceTests(unittest.TestCase):
    def test_local_source_runs_shared_pipeline_and_records_source(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "Companies Act, 2013.pdf"
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory))
            repository = Repository(config.database_path)
            source = LocalDocumentSource(config, files=[sample])
            runner = AgentRunner(config, repository=repository, source=source, ocr_provider=FixedOCR())
            self.assertEqual(runner.run_once(owner="local-source"), "complete")
            self.assertEqual(runner.last_discovered, 1)
            rows = repository.connect()
            with rows as db:
                row = db.execute("SELECT source_kind, download_status, ocr_status, classification_status, document_type FROM documents").fetchone()
            self.assertEqual(tuple(row), ("LOCAL", "success", "success", "success", "Acts"))
            self.assertEqual(len(list((config.data_dir / "documents" / "Acts").glob("*.pdf"))), 1)

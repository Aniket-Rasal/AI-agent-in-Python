import contextlib
import io
import os
import tempfile
import unittest
from unittest.mock import patch

import run
from app.config import Config
from app.database.repository import Repository


class DemoTests(unittest.TestCase):
    def test_local_demo_processes_sample_and_persists_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DATA_DIR": directory, "MAX_DOCUMENTS": "100"}, clear=True):
            config = Config.from_env()
            config.create_directories()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run._print_demo(config)
            self.assertEqual(result, 0)
            self.assertIn("Source: LOCAL DEMO", output.getvalue())
            self.assertIn("Status: SUCCESS", output.getvalue())
            database_path = next((config.data_dir / "demo_state").glob("companies-act-demo-*.sqlite3"))
            repository = Repository(database_path)
            self.assertEqual(repository.status()["downloaded"], 1)
            self.assertEqual(repository.status()["classified"], 1)
            with repository.connect() as db:
                row = db.execute("SELECT source_kind, document_type FROM documents").fetchone()
            self.assertEqual(tuple(row), ("LOCAL DEMO", "Acts"))
            self.assertEqual(len(list((config.data_dir / "documents" / "Acts").glob("*.pdf"))), 1)

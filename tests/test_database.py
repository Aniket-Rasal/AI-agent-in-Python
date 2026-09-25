import tempfile
import unittest
import sqlite3
from pathlib import Path

from app.database.repository import Repository


class RepositoryTests(unittest.TestCase):
    def test_state_persists_and_duplicate_hash_counts_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            repo = Repository(path)
            repo.add_candidate("one", "https://www.mca.gov.in/a.pdf", "A")
            repo.add_candidate("two", "local-pdf://sha256/hash2", "B", source_kind="LOCAL")
            repo.update("one", download_status="success", sha256="same")
            repo.update("two", download_status="duplicate", sha256="same")
            reopened = Repository(path)
            self.assertEqual(reopened.downloaded_count(), 1)
            self.assertEqual(reopened.get("one")["download_status"], "success")
            self.assertEqual(reopened.get("two")["source_kind"], "LOCAL")
            self.assertTrue(reopened.get("one")["created_at"])
            self.assertTrue(reopened.get("one")["updated_at"])

    def test_cycle_lease_blocks_second_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repository(Path(directory) / "state.sqlite3")
            self.assertTrue(repo.acquire_lease("first"))
            self.assertFalse(repo.acquire_lease("second"))
            repo.release_lease("first")
            self.assertTrue(repo.acquire_lease("second"))

    def test_existing_schema_is_migrated_with_source_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            Repository(path)
            db = sqlite3.connect(path)
            try:
                db.execute("ALTER TABLE documents DROP COLUMN source_kind")
                db.commit()
            finally:
                db.close()
            migrated = Repository(path)
            with migrated.connect() as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(documents)")}
            self.assertIn("source_kind", columns)

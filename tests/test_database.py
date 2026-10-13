from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from matharchive.database import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "data")

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_create_save_search_and_sidecars(self) -> None:
        question_id = self.db.create_question({
            "title": "二次関数の問題",
            "subject": "数学I",
            "topic": "二次関数",
            "exam_year": "2026",
            "question_md": "\\[x^2-1=0\\]",
            "answer_md": "\\(x=\\pm1\\)",
            "ocr_status": "未確認",
        })
        self.assertEqual(self.db.count(), 1)
        record = self.db.get_question(question_id)
        assert record is not None
        self.assertEqual(record["subject"], "数学I")
        hits = self.db.list_questions(query="二次関数", subject="数学I")
        self.assertEqual([item["id"] for item in hits], [question_id])
        sidecar = Path(self.temp.name) / "data" / "questions" / f"q{question_id:06d}" / "question.md"
        self.assertTrue(sidecar.exists())
        self.assertIn("x^2", sidecar.read_text(encoding="utf-8"))
        self.db.save_question(question_id, {"ocr_status": "確認済み", "tags": "因数分解"})
        self.assertEqual(self.db.get_question(question_id)["ocr_status"], "確認済み")
        self.assertEqual(self.db.distinct_values("topic"), ["二次関数"])

    def test_delete_removes_record_and_question_sidecar(self) -> None:
        question_id = self.db.create_question({"title": "削除テスト"})
        folder = Path(self.temp.name) / "data" / "questions" / f"q{question_id:06d}"
        self.assertTrue(folder.exists())
        self.db.delete_question(question_id)
        self.assertIsNone(self.db.get_question(question_id))
        self.assertFalse(folder.exists())

    def test_unknown_filter_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.db.distinct_values("id; DROP TABLE questions")


if __name__ == "__main__":
    unittest.main()

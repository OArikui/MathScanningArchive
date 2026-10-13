"""SQLite persistence and sidecar-file management for MathArchive."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FIELDS = {
    "title", "subject", "topic", "exam_year", "difficulty", "tags",
    "source_name", "source_path", "original_path", "source_page",
    "question_md", "answer_md", "solution_md", "ocr_text", "ocr_json", "ocr_status",
}
FILTER_FIELDS = {"subject", "topic", "exam_year", "ocr_status", "difficulty"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Database:
    """Database whose paths are relative to data_dir, making the archive portable."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "originals").mkdir(exist_ok=True)
        (self.data_dir / "questions").mkdir(exist_ok=True)
        self.db_path = self.data_dir / "math_archive.sqlite3"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                topic TEXT NOT NULL DEFAULT '',
                exam_year TEXT NOT NULL DEFAULT '',
                difficulty TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                source_path TEXT NOT NULL DEFAULT '',
                original_path TEXT NOT NULL DEFAULT '',
                source_page INTEGER NOT NULL DEFAULT 1,
                question_md TEXT NOT NULL DEFAULT '',
                answer_md TEXT NOT NULL DEFAULT '',
                solution_md TEXT NOT NULL DEFAULT '',
                ocr_text TEXT NOT NULL DEFAULT '',
                ocr_json TEXT NOT NULL DEFAULT '',
                ocr_status TEXT NOT NULL DEFAULT '未実行',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_questions_year ON questions(exam_year)")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def resolve(self, stored_path: str | None) -> Path | None:
        if not stored_path:
            return None
        path = Path(stored_path)
        return path if path.is_absolute() else (self.data_dir / path).resolve()

    def store_path(self, path: str | Path | None) -> str:
        if not path:
            return ""
        absolute = Path(path).resolve()
        try:
            return absolute.relative_to(self.data_dir).as_posix()
        except ValueError:
            # Imports are copied into the archive first; this is a defensive fallback.
            return absolute.as_posix()

    def create_question(self, values: dict[str, Any] | None = None) -> int:
        values = dict(values or {})
        stamp = now_iso()
        allowed = {key: value for key, value in values.items() if key in FIELDS}
        keys = list(allowed)
        insert_columns = keys + ["created_at", "updated_at"]
        insert_values = [allowed[k] for k in keys] + [stamp, stamp]
        sql = f"INSERT INTO questions ({', '.join(insert_columns)}) VALUES ({', '.join('?' for _ in insert_columns)})"
        cur = self.conn.execute(sql, insert_values)
        question_id = int(cur.lastrowid)
        self.conn.commit()
        self._write_sidecars(question_id, allowed)
        return question_id

    def save_question(self, question_id: int, values: dict[str, Any]) -> None:
        allowed = {key: value for key, value in values.items() if key in FIELDS}
        if not allowed:
            return
        assignments = ", ".join(f"{key} = ?" for key in allowed)
        params = list(allowed.values()) + [now_iso(), question_id]
        self.conn.execute(
            f"UPDATE questions SET {assignments}, updated_at = ? WHERE id = ?", params
        )
        self.conn.commit()
        self._write_sidecars(question_id, allowed)

    def _write_sidecars(self, question_id: int, values: dict[str, Any]) -> None:
        folder = self.data_dir / "questions" / f"q{question_id:06d}"
        folder.mkdir(parents=True, exist_ok=True)
        names = {
            "question_md": "question.md",
            "answer_md": "answer.md",
            "solution_md": "solution.md",
            "ocr_text": "ocr.md",
        }
        for field, filename in names.items():
            if field in values:
                (folder / filename).write_text(str(values[field] or ""), encoding="utf-8")
        if "ocr_json" in values and values["ocr_json"]:
            try:
                parsed = json.loads(str(values["ocr_json"]))
                (folder / "ocr.json").write_text(
                    json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except (json.JSONDecodeError, TypeError):
                (folder / "ocr.json").write_text(str(values["ocr_json"]), encoding="utf-8")

    def get_question(self, question_id: int) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        return dict(row) if row else None

    def list_questions(
        self,
        query: str = "",
        subject: str = "",
        topic: str = "",
        status: str = "",
        year: str = "",
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM questions WHERE 1=1"
        params: list[Any] = []
        for field, value in (("subject", subject), ("topic", topic), ("ocr_status", status), ("exam_year", year)):
            if value and value != "すべて":
                sql += f" AND {field} = ?"
                params.append(value)
        query = query.strip()
        if query:
            like = f"%{query}%"
            sql += " AND (title LIKE ? OR subject LIKE ? OR topic LIKE ? OR exam_year LIKE ? OR tags LIKE ? OR source_name LIKE ? OR question_md LIKE ? OR answer_md LIKE ? OR solution_md LIKE ?)"
            params.extend([like] * 9)
        sql += " ORDER BY updated_at DESC, id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def distinct_values(self, field: str) -> list[str]:
        if field not in FILTER_FIELDS:
            raise ValueError(f"Unsupported filter field: {field}")
        rows = self.conn.execute(
            f"SELECT DISTINCT {field} FROM questions WHERE TRIM({field}) <> '' ORDER BY {field} COLLATE NOCASE"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def delete_question(self, question_id: int) -> None:
        self.conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        self.conn.commit()
        import shutil
        shutil.rmtree(self.data_dir / "questions" / f"q{question_id:06d}", ignore_errors=True)

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0])

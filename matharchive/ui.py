"""PySide6 user interface for MathArchive."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageOps
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSplitter,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .database import Database
from .ocr import environment_credentials, recognize_image
from .pdf_export import PdfExportJob, build_html


APP_NAME = "MathArchive"
BASE_DIR = Path(__file__).resolve().parent.parent


class ImagePreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._source_text = "原本画像がありません。"
        self.label = QLabel(self._source_text)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(160, 180)
        self.label.setStyleSheet("background:#f5f6f8;color:#5c6572;border:1px solid #d8dce3;border-radius:8px;")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

    def set_image(self, path: Path | None) -> None:
        self._pixmap = QPixmap(str(path)) if path and path.exists() else QPixmap()
        self._source_text = str(path) if path else "原本画像がありません。"
        self._update_pixmap()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._update_pixmap()

    def _update_pixmap(self) -> None:
        if self._pixmap.isNull():
            self.label.setPixmap(QPixmap())
            self.label.setText(self._source_text)
            self.label.setMinimumSize(160, 180)
            return
        size = self.scroll.viewport().size()
        scaled = self._pixmap.scaled(
            max(160, size.width() - 16), max(180, size.height() - 16),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.label.setText("")
        self.label.setPixmap(scaled)
        self.label.setMinimumSize(scaled.size())


class CredentialDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, initial: tuple[str, str] = ("", "")) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mathpix OCR 設定")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        warning = QLabel(
            "OCR には Mathpix API を使用します。選択した原本画像は外部サービスへ送信されます。\n"
            "機密情報・第三者のテストを送信する前に、利用許可とサービスの規約を確認してください。\n"
            "認証情報はこのセッション中だけ保持し、アプリのデータベースには保存しません。"
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("background:#fff5dc;border:1px solid #e9cf8b;padding:10px;border-radius:6px;")
        layout.addWidget(warning)
        form = QFormLayout()
        self.app_id = QLineEdit(initial[0])
        self.app_id.setPlaceholderText("MATHPIX_APP_ID")
        self.app_key = QLineEdit(initial[1])
        self.app_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.app_key.setPlaceholderText("MATHPIX_APP_KEY")
        form.addRow("App ID", self.app_id)
        form.addRow("App Key", self.app_key)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("続行")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def credentials(self) -> tuple[str, str]:
        return self.app_id.text().strip(), self.app_key.text().strip()


class ExportDialog(QDialog):
    def __init__(self, parent: QWidget, has_selection: bool) -> None:
        super().__init__(parent)
        self.setWindowTitle("PDF 出力")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem("問題のみ", "questions")
        self.mode.addItem("解答・解説のみ", "answers")
        self.mode.addItem("問題＋解答・解説", "both")
        self.scope = QComboBox()
        self.scope.addItem("現在の検索結果", "filtered")
        self.scope.addItem("全問題", "all")
        if has_selection:
            self.scope.insertItem(0, "選択した問題", "selected")
        form.addRow("出力内容", self.mode)
        form.addRow("対象", self.scope)
        layout.addLayout(form)
        note = QLabel("数式は MathJax を利用して組版します。初回の数式レンダリングにはインターネット接続が必要です。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#596273")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("出力先を選択")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def options(self) -> tuple[str, str]:
        return str(self.mode.currentData()), str(self.scope.currentData())


class OCRWorker(QThread):
    succeeded = Signal(int, object)
    failed = Signal(int, str)
    status = Signal(str)

    def __init__(self, question_id: int, image_path: Path, app_id: str, app_key: str) -> None:
        super().__init__()
        self.question_id = question_id
        self.image_path = image_path
        self.app_id = app_id
        self.app_key = app_key

    def run(self) -> None:
        self.status.emit("Mathpix OCR を実行中…")
        try:
            result = recognize_image(self.image_path, self.app_id, self.app_key)
            self.succeeded.emit(self.question_id, result)
        except Exception as exc:
            self.failed.emit(self.question_id, str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — 数学テスト電子化アーカイブ")
        self.resize(1450, 900)
        self.setMinimumSize(1000, 650)
        self.db = Database(BASE_DIR / "data")
        self.current_id: int | None = None
        self.loaded_record: dict[str, Any] | None = None
        self._loading = False
        self._credentials = environment_credentials()
        self._cloud_warning_accepted = False
        self._worker: OCRWorker | None = None
        self._busy = False
        self._busy_widgets: list[QWidget] = []
        self._pdf_jobs: list[PdfExportJob] = []
        self._build_ui()
        self.refresh_filters()
        self.refresh_table()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background:#f3f5f8; }
            QWidget { font-family:'Yu Gothic UI','Meiryo',sans-serif; font-size:10pt; }
            QLineEdit, QComboBox, QPlainTextEdit, QTableWidget { background:white; border:1px solid #d6dbe4; border-radius:5px; padding:5px; }
            QPushButton { padding:7px 12px; border:1px solid #c8ced8; border-radius:6px; background:white; }
            QPushButton:hover { background:#e9eef7; }
            QPushButton#primary { background:#2457a7; color:white; border-color:#2457a7; font-weight:600; }
            QPushButton#primary:hover { background:#194687; }
            QTabWidget::pane { border:1px solid #d6dbe4; background:white; border-radius:5px; }
            QHeaderView::section { background:#e9edf3; padding:6px; border:none; border-right:1px solid #d6dbe4; }
        """)
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("MathArchive")
        title.setStyleSheet("font-size:22pt;font-weight:700;color:#172844;")
        subtitle = QLabel("スキャンした数学テストを整理・検索・再出力")
        subtitle.setStyleSheet("color:#687386;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch(1)
        self.import_button = QPushButton("画像・PDFを取り込む")
        self.import_button.clicked.connect(self.import_sources)
        self.new_button = QPushButton("＋ 新規問題")
        self.new_button.clicked.connect(self.new_question)
        self.ocr_button = QPushButton("OCRを実行")
        self.ocr_button.setObjectName("primary")
        self.ocr_button.clicked.connect(self.run_ocr)
        self.export_button = QPushButton("PDF出力")
        self.export_button.clicked.connect(self.export_pdf)
        for button in (self.import_button, self.new_button, self.ocr_button, self.export_button):
            header.addWidget(button)
        root.addLayout(header)

        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("問題文・解答・問題名・タグを検索…")
        self.subject_filter = QComboBox()
        self.topic_filter = QComboBox()
        self.year_filter = QComboBox()
        self.status_filter = QComboBox()
        self.search_edit.setClearButtonEnabled(True)
        filters.addWidget(self.search_edit, 3)
        filters.addWidget(QLabel("科目"))
        filters.addWidget(self.subject_filter, 1)
        filters.addWidget(QLabel("単元"))
        filters.addWidget(self.topic_filter, 1)
        filters.addWidget(QLabel("年度"))
        filters.addWidget(self.year_filter, 1)
        filters.addWidget(QLabel("OCR"))
        filters.addWidget(self.status_filter, 1)
        root.addLayout(filters)
        self.search_edit.textChanged.connect(self.on_filter_change)
        self.subject_filter.currentTextChanged.connect(self.on_filter_change)
        self.topic_filter.currentTextChanged.connect(self.on_filter_change)
        self.year_filter.currentTextChanged.connect(self.on_filter_change)
        self.status_filter.currentTextChanged.connect(self.on_filter_change)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.count_label = QLabel("0 件")
        self.count_label.setStyleSheet("color:#687386;font-weight:600;")
        left_layout.addWidget(self.count_label)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "問題名", "科目", "単元", "年度", "OCR"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 60)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(self.on_table_current_changed)
        left_layout.addWidget(self.table, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.title_edit = QLineEdit()
        self.subject_edit = QComboBox(); self.subject_edit.setEditable(True)
        self.topic_edit = QComboBox(); self.topic_edit.setEditable(True)
        self.year_edit = QLineEdit(); self.year_edit.setPlaceholderText("例：2026")
        self.difficulty_edit = QComboBox(); self.difficulty_edit.setEditable(True)
        self.difficulty_edit.addItems(["", "基礎", "標準", "応用", "発展"])
        self.tags_edit = QLineEdit(); self.tags_edit.setPlaceholderText("例：二次関数, 因数分解, 頻出")
        self.status_edit = QComboBox(); self.status_edit.addItems(["未実行", "未確認", "要確認", "確認済み"])
        form.addRow("問題名", self.title_edit)
        form.addRow("科目 / 単元", self._pair(self.subject_edit, self.topic_edit))
        form.addRow("年度 / 難易度", self._pair(self.year_edit, self.difficulty_edit))
        form.addRow("タグ（カンマ区切り）", self.tags_edit)
        form.addRow("OCR確認状態", self.status_edit)
        right_layout.addLayout(form)

        content_split = QSplitter(Qt.Orientation.Horizontal)
        content_split.setChildrenCollapsible(False)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        source_header = QHBoxLayout()
        source_header.addWidget(QLabel("原本ページ"))
        source_header.addStretch(1)
        self.open_source_button = QPushButton("原本を開く")
        self.open_source_button.setEnabled(False)
        self.open_source_button.clicked.connect(self.open_source)
        source_header.addWidget(self.open_source_button)
        preview_layout.addLayout(source_header)
        self.image_preview = ImagePreview()
        preview_layout.addWidget(self.image_preview, 1)
        self.source_label = QLabel("原本未登録")
        self.source_label.setWordWrap(True)
        self.source_label.setStyleSheet("color:#687386;font-size:9pt;")
        preview_layout.addWidget(self.source_label)
        content_split.addWidget(preview_panel)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.question_edit = QPlainTextEdit()
        self.question_edit.setPlaceholderText("問題文を Markdown + LaTeX で入力します。例：\n次の方程式を解きなさい。\n\n\\[x^2 - 5x + 6 = 0\\]")
        self.answer_edit = QPlainTextEdit()
        self.answer_edit.setPlaceholderText("解答を入力。問題文とは独立して保存されます。")
        self.solution_edit = QPlainTextEdit()
        self.solution_edit.setPlaceholderText("途中式や解法の説明を入力します。")
        self.ocr_edit = QPlainTextEdit()
        self.ocr_edit.setPlaceholderText("OCRで認識した原文。原本と照合して修正してください。")
        self.tabs.addTab(self.question_edit, "問題本文")
        self.tabs.addTab(self.answer_edit, "解答")
        self.tabs.addTab(self.solution_edit, "解説")
        self.tabs.addTab(self.ocr_edit, "OCR結果")
        editor_layout.addWidget(self.tabs, 1)
        content_split.addWidget(editor_panel)
        content_split.setSizes([350, 550])
        right_layout.addWidget(content_split, 1)

        buttons = QHBoxLayout()
        self.delete_button = QPushButton("問題を削除")
        self.delete_button.clicked.connect(self.delete_current)
        self.duplicate_button = QPushButton("このページから設問を複製")
        self.duplicate_button.setToolTip("同じ原本ページを参照する問題レコードを複製し、本文を設問単位に編集できます。")
        self.duplicate_button.clicked.connect(self.duplicate_question)
        self.save_button = QPushButton("変更を保存")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_and_refresh)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.duplicate_button)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)
        right_layout.addLayout(buttons)
        splitter.addWidget(right)
        splitter.setSizes([520, 900])
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self._busy_widgets = [
            self.import_button, self.new_button, self.ocr_button, self.export_button,
            self.search_edit, self.subject_filter, self.topic_filter, self.year_filter,
            self.status_filter, self.table, self.title_edit, self.subject_edit,
            self.topic_edit, self.year_edit, self.difficulty_edit, self.tags_edit,
            self.status_edit, self.tabs, self.delete_button, self.duplicate_button, self.save_button,
            self.open_source_button,
        ]
        self.statusBar().showMessage(f"保存先: {self.db.data_dir}")

    @staticmethod
    def _pair(left: QWidget, right: QWidget) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(left, 1)
        layout.addWidget(right, 1)
        return container

    def refresh_filters(self) -> None:
        self._loading = True
        combos = ((self.subject_filter, "subject"), (self.topic_filter, "topic"), (self.year_filter, "exam_year"), (self.status_filter, "ocr_status"))
        for combo, field in combos:
            previous = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("すべて")
            combo.addItems(self.db.distinct_values(field))
            index = combo.findText(previous)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)
        for combo, field in ((self.subject_edit, "subject"), (self.topic_edit, "topic")):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            combo.addItems(self.db.distinct_values(field))
            combo.setCurrentText(current)
            combo.blockSignals(False)
        self._loading = False

    def on_filter_change(self, *_args: Any) -> None:
        if self._loading:
            return
        self.save_current()
        self.refresh_table()

    def refresh_table(self, selected_id: int | None = None) -> None:
        if selected_id is None:
            selected_id = self.current_id
        records = self.db.list_questions(
            query=self.search_edit.text(),
            subject=self.subject_filter.currentText(),
            topic=self.topic_filter.currentText(),
            status=self.status_filter.currentText(),
            year=self.year_filter.currentText(),
        )
        self._loading = True
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        row_for_id: dict[int, int] = {}
        for record in records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [f"{record['id']:06d}", record.get("title", ""), record.get("subject", ""), record.get("topic", ""), record.get("exam_year", ""), record.get("ocr_status", "未実行")]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(record["id"]))
                self.table.setItem(row, col, item)
            row_for_id[int(record["id"])] = row
        self.count_label.setText(f"{len(records)} 件")
        if records:
            wanted_row = row_for_id.get(selected_id, 0)
            self.table.setCurrentCell(wanted_row, 0)
            self.table.selectRow(wanted_row)
        else:
            self.table.setCurrentCell(-1, -1)
        self.table.blockSignals(False)
        self._loading = False
        if records:
            record_id = int(records[row_for_id.get(selected_id, 0) if selected_id in row_for_id else 0]["id"])
            self.load_question(record_id)
        else:
            self.load_question(None)

    def on_table_current_changed(self, current_row: int, _current_col: int, _previous_row: int, _previous_col: int) -> None:
        if self._loading:
            return
        self.save_current()
        if current_row < 0:
            return
        item = self.table.item(current_row, 0)
        if item is not None:
            record_id = item.data(Qt.ItemDataRole.UserRole)
            if record_id is not None:
                self.load_question(int(record_id))

    def load_question(self, question_id: int | None) -> None:
        self._loading = True
        self.current_id = question_id
        self.loaded_record = self.db.get_question(question_id) if question_id is not None else None
        record = self.loaded_record or {}
        self.title_edit.setText(str(record.get("title", "")))
        self.subject_edit.setCurrentText(str(record.get("subject", "")))
        self.topic_edit.setCurrentText(str(record.get("topic", "")))
        self.year_edit.setText(str(record.get("exam_year", "")))
        self.difficulty_edit.setCurrentText(str(record.get("difficulty", "")))
        self.tags_edit.setText(str(record.get("tags", "")))
        status = str(record.get("ocr_status", "未実行"))
        self.status_edit.setCurrentText(status if self.status_edit.findText(status) >= 0 else "未実行")
        self.question_edit.setPlainText(str(record.get("question_md", "")))
        self.answer_edit.setPlainText(str(record.get("answer_md", "")))
        self.solution_edit.setPlainText(str(record.get("solution_md", "")))
        self.ocr_edit.setPlainText(str(record.get("ocr_text", "")))
        image_path = self.db.resolve(record.get("original_path"))
        source_path = self.db.resolve(record.get("source_path"))
        self.image_preview.set_image(image_path)
        if record:
            page_info = f"ページ {record.get('source_page', 1)}" if record.get("source_page") else ""
            self.source_label.setText(" / ".join(x for x in [str(record.get("source_name", "")), page_info, str(source_path or "")] if x))
        else:
            self.source_label.setText("原本未登録。新規問題を作成するか、画像・PDFを取り込んでください。")
        self.open_source_button.setEnabled(bool(source_path and source_path.exists()))
        self._sync_controls()
        self._loading = False

    def _sync_controls(self) -> None:
        for widget in self._busy_widgets:
            widget.setEnabled(not self._busy)
        if self._busy:
            return
        record = self.loaded_record or {}
        image_path = self.db.resolve(record.get("original_path"))
        source_path = self.db.resolve(record.get("source_path"))
        self.delete_button.setEnabled(bool(record))
        self.duplicate_button.setEnabled(bool(record))
        self.save_button.setEnabled(bool(record))
        self.open_source_button.setEnabled(bool(source_path and source_path.exists()))
        self.ocr_button.setEnabled(bool(record and image_path and image_path.exists() and self._worker is None))

    def _values_from_editor(self) -> dict[str, Any]:
        old = self.loaded_record or {}
        return {
            "title": self.title_edit.text().strip(),
            "subject": self.subject_edit.currentText().strip(),
            "topic": self.topic_edit.currentText().strip(),
            "exam_year": self.year_edit.text().strip(),
            "difficulty": self.difficulty_edit.currentText().strip(),
            "tags": self.tags_edit.text().strip(),
            "source_name": old.get("source_name", ""),
            "source_path": old.get("source_path", ""),
            "original_path": old.get("original_path", ""),
            "source_page": old.get("source_page", 1),
            "question_md": self.question_edit.toPlainText(),
            "answer_md": self.answer_edit.toPlainText(),
            "solution_md": self.solution_edit.toPlainText(),
            "ocr_text": self.ocr_edit.toPlainText(),
            "ocr_json": old.get("ocr_json", ""),
            "ocr_status": self.status_edit.currentText(),
        }

    def save_current(self) -> None:
        if self._loading or self.current_id is None:
            return
        values = self._values_from_editor()
        self.db.save_question(self.current_id, values)
        self.loaded_record = self.db.get_question(self.current_id)

    def save_and_refresh(self) -> None:
        if self.current_id is None:
            return
        self.save_current()
        self.refresh_filters()
        self.refresh_table(self.current_id)
        self.statusBar().showMessage("変更を保存しました。", 3500)

    def new_question(self) -> None:
        self.save_current()
        self.search_edit.blockSignals(True); self.search_edit.clear(); self.search_edit.blockSignals(False)
        for combo in (self.subject_filter, self.topic_filter, self.year_filter, self.status_filter):
            combo.blockSignals(True); combo.setCurrentIndex(0); combo.blockSignals(False)
        question_id = self.db.create_question({"title": "新しい問題"})
        self.refresh_filters()
        self.refresh_table(question_id)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def import_sources(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "数学テストの画像・PDFを選択", "",
            "画像・PDF (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;すべてのファイル (*.*)",
        )
        if not file_paths:
            return
        self.save_current()
        imported_ids: list[int] = []
        errors: list[str] = []
        for file_path in file_paths:
            try:
                imported_ids.extend(self._import_one(Path(file_path)))
            except Exception as exc:
                errors.append(f"{Path(file_path).name}: {exc}")
        self.search_edit.blockSignals(True); self.search_edit.clear(); self.search_edit.blockSignals(False)
        for combo in (self.subject_filter, self.topic_filter, self.year_filter, self.status_filter):
            combo.blockSignals(True); combo.setCurrentIndex(0); combo.blockSignals(False)
        self.refresh_filters()
        self.refresh_table(imported_ids[-1] if imported_ids else None)
        message = f"{len(imported_ids)} 件のページを登録しました。"
        if errors:
            message += "\n\n取り込めなかったファイル:\n" + "\n".join(errors[:10])
        QMessageBox.information(self, "取り込み結果", message)

    def _import_one(self, source: Path) -> list[int]:
        if not source.exists():
            raise FileNotFoundError("ファイルが見つかりません")
        folder = self.db.data_dir / "originals" / uuid.uuid4().hex
        folder.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix.lower()
        base_name = source.stem
        records: list[dict[str, Any]] = []
        if suffix == ".pdf":
            source_copy = folder / "source.pdf"
            shutil.copy2(source, source_copy)
            document = fitz.open(source_copy)
            if document.needs_pass:
                document.close()
                raise ValueError("パスワード付き PDF は取り込めません")
            try:
                for page_index, page in enumerate(document):
                    page_path = folder / f"page_{page_index + 1:04d}.png"
                    page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False).save(page_path)
                    records.append({
                        "title": f"{base_name} - P{page_index + 1:03d}",
                        "source_name": source.name,
                        "source_path": self.db.store_path(source_copy),
                        "original_path": self.db.store_path(page_path),
                        "source_page": page_index + 1,
                        "ocr_status": "未実行",
                    })
            finally:
                document.close()
        else:
            source_copy = folder / f"source_original{suffix}"
            shutil.copy2(source, source_copy)
            page_path = folder / "page_0001.png"
            with Image.open(source_copy) as image:
                normalized = ImageOps.exif_transpose(image)
                if normalized.mode not in ("RGB", "L"):
                    normalized = normalized.convert("RGB")
                normalized.save(page_path, format="PNG", optimize=True)
            records.append({
                "title": base_name,
                "source_name": source.name,
                "source_path": self.db.store_path(source_copy),
                "original_path": self.db.store_path(page_path),
                "source_page": 1,
                "ocr_status": "未実行",
            })
        if not records:
            raise ValueError("PDFにページがないか、画像を読み込めませんでした")
        return [self.db.create_question(record) for record in records]

    def open_source(self) -> None:
        if not self.loaded_record:
            return
        path = self.db.resolve(self.loaded_record.get("source_path"))
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def duplicate_question(self) -> None:
        if self.current_id is None or not self.loaded_record:
            return
        self.save_current()
        values = self._values_from_editor()
        current_title = values.get("title", "").strip() or "無題"
        values["title"] = f"{current_title}（複製）"
        values["ocr_status"] = "未確認" if values.get("ocr_text", "").strip() else "未実行"
        new_id = self.db.create_question(values)
        self.refresh_filters()
        self.refresh_table(new_id)
        self.statusBar().showMessage("原本ページを共有する問題レコードを複製しました。本文を設問単位に編集してください。", 6000)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def delete_current(self) -> None:
        if self.current_id is None:
            return
        record_id = self.current_id
        answer = QMessageBox.question(
            self, "問題を削除", f"問題 ID {record_id:06d} を削除しますか？\n原本画像ファイルは、他のページから参照される可能性があるため削除しません。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_question(record_id)
        self.current_id = None
        self.refresh_filters()
        self.refresh_table()

    def run_ocr(self) -> None:
        if self.current_id is None or not self.loaded_record:
            QMessageBox.information(self, "OCR", "先に問題を選択してください。")
            return
        if self._worker is not None:
            QMessageBox.information(self, "OCR", "OCR を実行中です。")
            return
        image_path = self.db.resolve(self.loaded_record.get("original_path"))
        if not image_path or not image_path.exists():
            QMessageBox.warning(self, "OCR", "原本ページ画像が見つかりません。画像または PDF を取り込んでください。")
            return
        if not self._cloud_warning_accepted:
            answer = QMessageBox.warning(
                self, "外部 OCR サービスへの送信",
                "選択したページ画像を Mathpix API に送信します。\n個人情報や送信許可のないテストが含まれていないことを確認してください。\n\n続行しますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._cloud_warning_accepted = True
        app_id, app_key = self._credentials
        if not app_id or not app_key:
            dialog = CredentialDialog(self, self._credentials)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            app_id, app_key = dialog.credentials()
            if not app_id or not app_key:
                QMessageBox.warning(self, "OCR", "App ID と App Key を入力してください。")
                return
            self._credentials = (app_id, app_key)
        self.save_current()
        question_id = self.current_id
        self._worker = OCRWorker(question_id, image_path, app_id, app_key)
        self._worker.succeeded.connect(self._ocr_succeeded)
        self._worker.failed.connect(self._ocr_failed)
        self._worker.status.connect(self.statusBar().showMessage)
        self._worker.finished.connect(self._ocr_thread_finished)
        self._busy = True
        self._sync_controls()
        self.statusBar().showMessage("Mathpix OCR を実行中…")
        self._worker.start()

    def _ocr_succeeded(self, question_id: int, result: object) -> None:
        if not isinstance(result, dict):
            return
        record = self.db.get_question(question_id)
        if not record:
            return
        recognized = str(result.get("text", ""))
        values: dict[str, Any] = {
            "ocr_text": recognized,
            "ocr_json": json.dumps(result, ensure_ascii=False),
            "ocr_status": "未確認",
        }
        if not str(record.get("question_md", "")).strip():
            values["question_md"] = recognized
        self.db.save_question(question_id, values)
        self.refresh_filters()
        self.refresh_table(question_id)
        self.tabs.setCurrentIndex(3)
        QMessageBox.information(
            self, "OCR 完了",
            "認識結果を保存しました。状態は「未確認」です。\n原本と照合し、数式・符号・添字・図表を確認してから「確認済み」に変更してください。\n"
            + ("問題本文が空だったため OCR 結果を転記しました。" if "question_md" in values else "問題本文は上書きしていません。"),
        )
        self.statusBar().showMessage("OCR 結果を保存しました。内容を確認してください。", 6000)

    def _ocr_failed(self, question_id: int, message: str) -> None:
        record = self.db.get_question(question_id)
        if record:
            self.db.save_question(question_id, {"ocr_status": "要確認"})
        self.refresh_filters()
        self.refresh_table(question_id)
        QMessageBox.critical(self, "OCR エラー", message)
        self.statusBar().showMessage("OCR に失敗しました。認証情報、通信、利用制限を確認してください。", 7000)

    def _ocr_thread_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        self._worker = None
        self._busy = False
        self._sync_controls()

    def export_pdf(self) -> None:
        selected_rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        selected_ids: list[int] = []
        for row in selected_rows:
            item = self.table.item(row, 0)
            if item:
                value = item.data(Qt.ItemDataRole.UserRole)
                if value is not None:
                    selected_ids.append(int(value))
        dialog = ExportDialog(self, bool(selected_ids))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode, scope = dialog.options()
        if scope == "selected":
            ids = selected_ids
            records = [self.db.get_question(item_id) for item_id in ids]
            records = [item for item in records if item]
        elif scope == "all":
            records = self.db.list_questions()
        else:
            records = self.db.list_questions(
                query=self.search_edit.text(), subject=self.subject_filter.currentText(),
                topic=self.topic_filter.currentText(), status=self.status_filter.currentText(),
                year=self.year_filter.currentText(),
            )
        if not records:
            QMessageBox.information(self, "PDF出力", "出力対象の問題がありません。")
            return
        suggested = "math_questions.pdf" if mode == "questions" else "math_answers_solutions.pdf" if mode == "answers" else "math_test_bundle.pdf"
        output, _ = QFileDialog.getSaveFileName(self, "PDFの保存先", str(BASE_DIR / suggested), "PDFファイル (*.pdf)")
        if not output:
            return
        if not output.lower().endswith(".pdf"):
            output += ".pdf"
        html_text = build_html(records, mode)
        self.statusBar().showMessage("PDF を生成しています…")
        job = PdfExportJob(self, html_text, output, self._pdf_finished)
        self._pdf_jobs.append(job)

    def _pdf_finished(self, success: bool, message: str, output_path: str) -> None:
        self._pdf_jobs = [job for job in self._pdf_jobs if getattr(job, "output_path", "") != output_path]
        if success:
            self.statusBar().showMessage(message, 6000)
            QMessageBox.information(self, "PDF出力", f"{message}\n\n{output_path}")
        else:
            self.statusBar().showMessage(message, 7000)
            QMessageBox.critical(self, "PDF出力", f"{message}\n\n出力先: {output_path}")

    def closeEvent(self, event: Any) -> None:
        self.save_current()
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.warning(self, "処理中", "OCR が実行中です。完了してから終了してください。")
            event.ignore()
            return
        self.db.close()
        event.accept()

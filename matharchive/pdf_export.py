"""Build print-ready HTML and export it to PDF through Qt WebEngine when available."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import markdown


CSS = r"""
@page { size: A4; margin: 16mm 17mm 18mm; }
* { box-sizing: border-box; }
body { font-family: "Yu Gothic", "Meiryo", "Noto Sans CJK JP", sans-serif; color: #20242b; font-size: 11pt; line-height: 1.65; }
h1 { font-size: 22pt; border-bottom: 1px solid #b8bec8; padding-bottom: 5mm; margin-bottom: 8mm; }
h2 { font-size: 15pt; margin: 9mm 0 3mm; }
h3 { font-size: 12pt; margin: 5mm 0 2mm; }
.meta { color: #555d68; font-size: 9pt; margin-bottom: 4mm; }
.question { margin-bottom: 9mm; break-inside: auto; }
.content { margin: 2mm 0 4mm; }
pre { white-space: pre-wrap; border: 1px solid #d6d9df; padding: 3mm; }
blockquote { border-left: 3px solid #aab3c0; margin-left: 0; padding-left: 4mm; color: #444b55; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #aeb4bd; padding: 2mm; }
hr { border: none; border-top: 1px solid #d4d7dd; margin: 7mm 0; }
footer { color: #686f79; font-size: 8pt; }
.math-unavailable { color: #754c00; font-size: 9pt; }
"""


def _md(text: str) -> str:
    return markdown.markdown(text or "", extensions=["tables", "fenced_code", "sane_lists"])


def build_html(records: list[dict[str, Any]], mode: str) -> str:
    title = {
        "questions": "数学テスト — 問題",
        "answers": "数学テスト — 解答・解説",
        "both": "数学テスト — 問題・解答・解説",
    }.get(mode, "数学テスト")
    blocks: list[str] = []
    for number, record in enumerate(records, 1):
        subject = html.escape(str(record.get("subject", "") or ""))
        topic = html.escape(str(record.get("topic", "") or ""))
        year = html.escape(str(record.get("exam_year", "") or ""))
        source = html.escape(str(record.get("source_name", "") or ""))
        meta = " ・ ".join(item for item in [subject, topic, year, source] if item)
        title_text = html.escape(str(record.get("title", "無題") or "無題"))
        section = [f'<article class="question"><h2>{number}. {title_text}</h2>']
        if meta:
            section.append(f'<div class="meta">{meta}</div>')
        if mode in ("questions", "both"):
            section.append('<h3>問題</h3><div class="content">' + _md(str(record.get("question_md", ""))) + "</div>")
        if mode in ("answers", "both"):
            answer = str(record.get("answer_md", "") or "").strip()
            solution = str(record.get("solution_md", "") or "").strip()
            if answer:
                section.append('<h3>解答</h3><div class="content">' + _md(answer) + "</div>")
            if solution:
                section.append('<h3>解説</h3><div class="content">' + _md(solution) + "</div>")
            if not answer and not solution:
                section.append('<p class="meta">解答・解説は未登録です。</p>')
        section.append("</article><hr>")
        blocks.append("\n".join(section))
    mathjax = r'''<script>window.MathJax={tex:{inlineMath:[['\\(','\\)'],['$','$']],displayMath:[['\\[','\\]'],['$$','$$']]},options:{skipHtmlTags:['script','noscript','style','textarea','pre','code']}};</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>'''
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style>{mathjax}</head><body><h1>{html.escape(title)}</h1>
{''.join(blocks)}<footer>MathArchive から出力</footer></body></html>'''


class PdfExportJob:
    """Asynchronous PDF writer. The owner should keep this instance alive until finished."""

    def __init__(self, parent: Any, html_text: str, output_path: str | Path, on_finished: Any) -> None:
        self.parent = parent
        self._fallback_html = html_text
        self.output_path = str(Path(output_path).resolve())
        self.on_finished = on_finished
        self.view = None
        self._started_printing = False
        self._finished = False
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self._QUrl = QUrl
            self.view = QWebEngineView()
            self.view.resize(1000, 1400)
            self.view.page().pdfPrintingFinished.connect(self._pdf_done)
            self.view.loadFinished.connect(self._loaded)
            self.view.setHtml(html_text, QUrl("https://matharchive.local/"))
        except Exception:
            self._fallback(html_text)

    def _loaded(self, ok: bool) -> None:
        if self._started_printing:
            return
        self._started_printing = True
        if not ok:
            self._fallback_print()
            return
        script = r'''(async function(){
          function waitMathJax(){return new Promise(resolve=>{let n=0;function tick(){if(window.MathJax&&window.MathJax.typesetPromise){window.MathJax.typesetPromise().then(()=>resolve(true)).catch(()=>resolve(false));}else if(n++<35){setTimeout(tick,200);}else{resolve(false);}}tick();});}
          return await waitMathJax();
        })()'''
        self.view.page().runJavaScript(script, lambda _ready: self._print())

    def _print(self) -> None:
        if self.view is not None:
            self.view.page().printToPdf(self.output_path)

    def _pdf_done(self, path: str, success: bool) -> None:
        self._finish(bool(success), "PDF を出力しました。" if success else "PDF の出力に失敗しました。")

    def _fallback(self, html_text: str) -> None:
        """Fallback if Qt WebEngine is unavailable; formulas remain as source LaTeX."""
        self._fallback_html = html_text
        if self.view is not None:
            self.view.close()
            self.view.deleteLater()
            self.view = None
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._fallback_print)
        except Exception:
            self._fallback_print()

    def _fallback_print(self) -> None:
        try:
            from PySide6.QtGui import QTextDocument, QPageSize
            from PySide6.QtPrintSupport import QPrinter
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(self.output_path)
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            document = QTextDocument()
            document.setHtml(getattr(self, "_fallback_html", "<html><body>PDF 出力に失敗しました。</body></html>"))
            document.print(printer)
            self._finish(Path(self.output_path).exists(), "PDF を出力しました（数式の組版は簡易表示です）。")
        except Exception as exc:
            self._finish(False, f"PDF の出力に失敗しました: {exc}")

    def _finish(self, success: bool, message: str) -> None:
        if self._finished:
            return
        self._finished = True
        if self.view is not None:
            self.view.close()
            self.view.deleteLater()
            self.view = None
        self.on_finished(success, message, self.output_path)

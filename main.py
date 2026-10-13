"""Start MathArchive."""
from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication, QMessageBox

from matharchive.ui import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MathArchive")
    app.setOrganizationName("MathArchive")
    try:
        window = MainWindow()
    except Exception as exc:
        QMessageBox.critical(None, "起動エラー", f"MathArchive を起動できませんでした。\n\n{exc}")
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

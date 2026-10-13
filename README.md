# MathArchive 0.1.0

スキャンした数学テストを取り込み、OCR 結果を確認・修正して、分類・検索・PDF 出力する Windows 向けデスクトップアプリです。

## 主な機能

- PNG / JPEG / BMP / TIFF / WebP と PDF の取り込み
- PDF はページごとに画像を作成し、ページ単位のレコードとして登録
- 科目・単元・年度・難易度・タグ、OCR 状態の管理
- 問題文・解答・解説・OCR 原文を別々に保存
- 問題名、メタデータ、問題文、解答、解説、タグから検索
- 原本ページと Markdown / LaTeX の編集内容を並べて確認
- Mathpix OCR API 連携。結果は「未確認」として保存し、既存の問題本文を不用意に上書きしない
- 選択した問題、検索結果、全問題の PDF 出力。問題用と解答・解説用の分離に対応
- SQLite と Markdown / JSON サイドカーを併用

## Windows で起動

1. Python 3.11 以降をインストールしてください。
2. ZIP を書き込み可能なフォルダーに展開してください（例：`E:\app\MathArchive`）。
3. `setup.bat` を実行します。仮想環境 `.venv` を作成し、依存パッケージをインストールしてから起動します。
4. 次回以降は `run.bat` で起動できます。

コマンドラインで実行する場合：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

初回インストールでは PySide6 などのパッケージをダウンロードします。容量とネット接続を確保してください。

## 使い方

1. **画像・PDFを取り込む** を押してスキャン画像または PDF を選択します。
2. PDF はページごとのレコードに分けられます。1ページに複数の設問がある場合は **このページから設問を複製** で同じ原本を参照するレコードを増やし、各レコードの本文を設問単位に編集できます。
3. レコードを選び、科目・単元・年度・タグを入力します。
4. **OCRを実行** で Mathpix API を利用できます。最初に App ID / App Key を入力します。
5. **問題本文** と **OCR結果** を原本と照合し、誤認識を修正してください。確認後、OCR確認状態を **確認済み** に変更して保存します。
6. **PDF出力** から「問題のみ」「解答・解説のみ」「問題＋解答・解説」を選択します。

問題本文は Markdown を基本とし、数式は LaTeX で記述します。

```markdown
次の方程式を解きなさい。

\[x^2 - 5x + 6 = 0\]
```

数式の区切りは `\(...\)`（インライン）と `\[...\]`（別行）を推奨します。

## OCR とプライバシー

- OCR は Mathpix のクラウド API を利用します。OCR 実行前に確認ダイアログを表示し、画像が外部へ送信されることを明示します。
- API キーは環境変数 `MATHPIX_APP_ID` / `MATHPIX_APP_KEY`、または OCR 実行時の入力で渡せます。画面から入力したキーはセッション中のみメモリに保持され、データベースや設定ファイルには保存しません。
- 無許可の試験、個人情報、機密資料は送信しないでください。利用条件や料金は Mathpix の現行規約で確認してください。
- **オフラインの数式 OCR はこのバージョンには含まれません。** OCR を使わず、本文を手入力して管理することはできます。

## 保存先とバックアップ

データはアプリの `data` フォルダーへ保存します。

```text
data/
├── math_archive.sqlite3
├── originals/       # 取り込んだ原本とページ画像
└── questions/
    └── q000001/
        ├── question.md
        ├── answer.md
        ├── solution.md
        ├── ocr.md
        └── ocr.json
```

バックアップするときはアプリを終了し、`data` フォルダー全体をコピーしてください。SQLite と外部ファイルを一緒にバックアップする必要があります。

## PDF 出力について

- MathJax による数式の組版を試みます。初回の数式レンダリングにはインターネット接続が必要です。
- Qt WebEngine が利用できない環境では簡易 PDF 出力にフォールバックします。その場合、数式の LaTeX がソース表記のままになる可能性があります。
- 印刷結果を必ず確認してください。OCR 出力と同様、数式・符号・添字・図表の正確性は自動では保証されません。

## 制限事項（初期版）

- 自動設問分割、OCR の信頼度ベース自動判定、ローカル OCR、重複問題検出、図形の再描画は未実装です。設問の切り出しは複製と手動編集で行います。
- PDF はページ単位でレコード化されます。設問が複数あるページは手動編集が必要です。
- 検索は SQLite の文字列検索を使用します。LaTeX の数式はソース文字列で検索されます。

## 開発テスト

```powershell
python -m unittest discover -s tests -v
```

## GitHub 用コミット案

**Commit message**

```text
feat: add MathArchive scanned math test manager
```

**Description**

```text
Add a PySide6 desktop app for importing scanned math tests, storing metadata and Markdown/LaTeX content in SQLite-backed records, reviewing Mathpix OCR output, and exporting separate question and solution PDFs. Include Windows setup scripts and database tests.
```

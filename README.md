# MathArchive 0.2.0

スキャンした数学テストを取り込み、無料 OCR サイトの結果を手動で取り込んで、分類・検索・PDF 出力する Windows 向けデスクトップアプリです。有料 API の契約や API キーは必要ありません。

## 主な機能

- PNG / JPEG / BMP / TIFF / WebP と PDF の取り込み
- PDF はページごとに画像を作成し、ページ単位のレコードとして登録
- 科目・単元・年度・難易度・タグ、OCR 状態の管理
- 問題文・解答・解説・OCR 原文を別々に保存
- 問題名、メタデータ、問題文、解答、解説、タグから検索
- 原本ページと Markdown / LaTeX の編集内容を並べて確認
- 無料 OCR サイトをブラウザーで開き、画像を手動アップロードして結果を貼り付け
- OCR 結果は「未確認」として保存し、必要に応じて空の問題本文へ転記
- 選択した問題、検索結果、全問題の PDF 出力。問題用と解答・解説用の分離に対応
- SQLite と Markdown / JSON サイドカーを併用

## Windows で起動

1. Python 3.11 以降をインストールしてください。
2. ZIP を書き込み可能なフォルダーに展開してください（例：`E:\app\MathArchive`）。
3. `setup.bat` を実行します。`.venv` を作成し、必要な Python パッケージをインストールしてから起動します。
4. 次回以降は `run.bat` で起動できます。

コマンドラインで実行する場合：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

初回インストールでは PySide6 などのパッケージをダウンロードします。アプリの OCR 機能自体には API キーや有料サービスは不要です。

## 無料 OCR の使い方

1. **画像・PDFを取り込む** を押して、スキャンしたテストを登録します。
2. 問題一覧から対象のページを選び、**無料OCR・結果取込** を押します。
3. ダイアログ内の **原本フォルダーを開く** を押して、アップロードする画像ファイルを確認します。
4. **Pix2Text 多言語デモ** などのボタンを押してブラウザーで OCR サイトを開きます。
5. サイト側で画像を手動アップロードし、認識結果をコピーします。
6. アプリのダイアログに戻って結果を貼り付け、**OCR 結果を保存** を押します。
7. 原本画像と OCR 結果を照合し、数式・符号・添字・選択肢・図表を修正してください。確認後、OCR 確認状態を **確認済み** に変更して保存します。

アプリは原本画像を OCR サイトへ自動送信しません。画像はユーザーがサイト側の画面から手動でアップロードします。外部サイトに送信してよい資料か確認してから利用してください。

### 無料 OCR サイト

- **[Pix2Text 多言語デモ](https://huggingface.co/spaces/breezedeus/Pix2Text-Demo)**：日本語を含む文章を試す場合の候補です。デモは混雑状況などで処理に時間がかかる場合があります。
- **[Pix2Text オンライン版](https://p2t.breezedeus.com/)**：公式説明では英語・簡体字中国語向けです。数式部分の認識を試す用途に向きます。
- **[Pix2Text のソースコードと説明](https://github.com/breezedeus/Pix2Text)**：オープンソース版の導入情報を確認できます。ローカル導入には追加パッケージやモデルのダウンロードが必要です。

これらは無料で利用できる公開サービスですが、可用性、利用制限、対応言語、サイトの仕様は変更される場合があります。認識精度は保証されず、特に日本語の設問・図形・複雑な数式は目視確認が必要です。

## 問題の編集

問題本文・解答・解説は別々に編集・保存します。本文は Markdown を基本とし、数式は LaTeX で記述します。

```markdown
次の方程式を解きなさい。

\[x^2 - 5x + 6 = 0\]
```

数式の区切りは `\(...\)`（インライン）と `\[...\]`（別行）を推奨します。

PDF は「問題のみ」「解答・解説のみ」「問題＋解答・解説」から選べます。問題集を作成する場合は、選択した問題、現在の検索結果、または全問題を対象にできます。

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

- 数式の組版には MathJax を利用します。初回の数式レンダリングにはインターネット接続が必要です。
- Qt WebEngine が利用できない環境では簡易 PDF 出力にフォールバックします。その場合、数式の LaTeX がソース表記のままになる可能性があります。
- 印刷結果を確認してください。OCR 出力と同様、数式・符号・添字・図表の正確性は自動では保証されません。

## 開発テスト

```powershell
python -m unittest discover -s tests -v
```

## GitHub 用コミット案

**Commit message**

```text
feat: replace paid OCR API with free manual OCR workflow
```

**Description**

```text
Remove the paid Mathpix API integration and API-key setup.
Add a guided workflow for free Pix2Text web OCR: open the original scan,
launch a public OCR demo, paste Markdown/LaTeX results, and store them as
unverified OCR content. Keep the original question text unless the user
explicitly opts to copy OCR text into the question editor.
Update setup requirements, documentation, version, and tests.
```

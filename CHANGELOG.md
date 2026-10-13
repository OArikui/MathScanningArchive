# Changelog

## 0.2.0 — Free manual OCR workflow

- Remove Mathpix API integration and API-key requirements.
- Add a guided free OCR workflow using public Pix2Text sites.
- Add buttons to open the original image/folder and launch OCR sites in the browser.
- Allow pasted Markdown/LaTeX OCR output to be recorded and reviewed.
- Record the selected source and original OCR text in JSON sidecar metadata.
- Keep OCR results marked as unverified until the user reviews them.
- Remove the unused HTTP client dependency and update tests/documentation.

## 0.1.0 — Initial preview

- Add scanned image/PDF import and page-level records.
- Add SQLite metadata, free-text search, and Markdown/LaTeX sidecars.
- Add separate question/answer/solution editing and PDF export modes.
- Add same-source-page record duplication for splitting multiple questions on one scan page.
- Add Windows setup/launch scripts and database tests.

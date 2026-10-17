# Library CD Rip

Read `README.md` for launch, recovery and architecture. For preparing a user's CD photos, follow `WORKFLOW.md`; `prepare.py` creates a reviewed draft without starting hardware. Keep personal photos, metadata and audio outside this source directory.

Use the isolated unit/HTTP tests and `npm run test:ui` before using a real drive. Browser tests must use the separately identified Playwright Chromium, never the installed primary browser with a temporary profile. The fixture server in `tests/` never touches hardware or the registry.

The child screen must use photos, spoken instructions, clear progress and a visible working indicator. Completion requires successful fre:ac exit plus audio validation and a durable journal. Never introduce automatic tray ejection or run a second CD API while an encoder owns the drive. Do not replace those checks with timers or file-existence checks.

For Yoto uploads, phone linking and labels, follow `YOTO_WORKFLOW.md`. Prepare card groupings before uploading. Reuse private manifests and existing playlist URLs; do not reupload, relink or print a completed batch to test this code. Linking and offline audio download are separate confirmations.

Sessions and dependencies belong under `%LOCALAPPDATA%\LibraryCDRip`. Preserve interrupted output, resume receipts and existing music. AutoPlay changes are temporary and journaled. Native ripping is Windows-only; use Git through WSL for Git operations on Windows.

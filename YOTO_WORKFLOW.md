# From finished CDs to Yoto cards

This is an assistant-operated workflow after the child finishes the ripping mission. Local preparation and actual-size label printing are scripted. Yoto login, uploading, family membership and physical NFC linking still use the official website/app. Do not promise unattended linking or offline playback before checking it.

## Prepare once, reuse the result

1. Verify the rip journal and MP3s first. Ask how many physical Make Your Own cards are available. Group whole albums onto those cards **before uploading** to avoid uploading separate albums and combining them again later. Preserve the photo order unless the user chooses another order.
2. Install optional tools with `python -m pip install -r requirements-yoto.txt`. Copy [examples/yoto-plan.json](examples/yoto-plan.json) to a **private folder outside this repository**. Use absolute album folders or paths relative to that plan. Each album folder contains one disc's MP3s. Covers are optional JPEG/PNG files. Album `label` is the short name printed in the table of contents; `title` names the card/playlist. No passwords belong in a plan.
3. Run:

   ```powershell
   python yoto_prepare.py --plan "<private folder>\plan.json" --output "<private folder>\prepared"
   ```

   The script checks MP3 durations and numeric track tags, stages SHA-256-verified copies with global `001`, `002`… filenames, writes `manifest.json`, and makes `card-labels.pdf`. Original music is never retagged or renamed. Untagged files use natural filename order; mixed or duplicate track tags stop preparation for correction. Limits are conservative decimal values: 100 tracks, 500 MB and five hours per card; 100 MB and one hour per track. See [Yoto's limits](https://support.yotoplay.com/en_gb/how-much-audio-fits-on-a-make-your-own-card-r1ssdFimfl).

   Rerunning the same plan/output verifies and reuses copies. A changed plan/audio version needs a new output folder; existing or differing files are preserved. Keep the plan, manifest and output as the batch's recovery record. Preparation performs no network requests, printing or linking.
4. Inspect the manifest order and render/inspect the PDF before uploading or printing. Default contents rows show album track ranges. For more detail, a card may specify `contents` as `[{"first":1,"last":1,"title":"First story"}, ...]`. These inclusive ranges must cover every track exactly once in order. Use track tags or photographed track numbers as evidence: a story title on a back cover does not necessarily identify a CD track boundary. Long label contents fail preparation rather than silently printing outside the card.

## Upload and record the result

5. Open [My Yoto](https://my.yotoplay.com/) in the signed-in browser. Reuse an existing playlist when `manifest.json` already has its `yoto_url`; do not blindly create duplicates. Create one playlist per physical card, named by its plan title, and choose that card's cover.
6. Upload **only that card folder's MP3s**, in manifest order. Prefer a browser file-chooser/upload API that accepts a list of absolute paths. Typing many quoted paths into a native Windows picker can truncate the selection. If a control tool has a per-upload file limit, use consecutive batches and verify order across each boundary. Keep the assistant's progress visible while waiting.
7. Wait for all tracks to finish processing, save, and reopen the playlist. Check track count, duration and exact order against the manifest. Yoto may deduplicate already uploaded audio and display its **original upload filename**, even when the newly staged filename is different. Use `source_name`, title, duration and audio identity to reconcile; do not infer a failed upload just from reused names. Fix any ordering errors before linking.
8. Record the playlist URL in that card's `yoto_url`, and set `uploaded_order_verified` to `true` only after this check. These receipt fields survive a preparation rerun. Leave them blank/false until verified. Never store a password, browser cookie or access token in the manifest/repo.

## Phone, family and physical cards

9. Use the connected phone through the available computer/device controls. For Machine Control, start with its common CLI and Android platform guide; discover the target at runtime. Keep device selectors and private controller paths out of this public repository. Install the official Yoto app from Google Play if needed. Prefer its existing login or saved password autofill. A biometric/password-manager unlock needs a brief physical handoff; never extract the saved password. Join the user's explicitly supplied family invite before checking that family's player.
10. In the Yoto app, open the saved playlist and its **Link to a card** action. Tell the grown-up which numbered physical card is needed and show the matching cover. Start NFC scanning, then let them hold that **one** card against the phone's NFC area. Wait for the app's linked confirmation before requesting the second card. Record `linked_confirmation` as either observed app success or the user's report of app success; a return to the library screen alone is not evidence. Linking associates a playlist with a card; the phone does not copy all the audio into the card.
11. Keep linking and player downloading separate. Power the intended Yoto player on, connect it to Wi-Fi and charge it. Insert each linked card briefly to start playback, then remove it and leave the player powered/charging and idle to download. In the app, open Settings, select the player, and check **Audio Download Status**. Set `offline_download_verified` only after a verified download or an actual offline playback test. If the player is offline, say so; do not call the entire offline setup finished. See [Yoto's download instructions](https://support.yotoplay.com/en_gb/does-my-yoto-need-to-be-online-to-play-content-rkmbFFj7fg).

## Print once, at actual size

12. `card-labels.pdf` has six credit-card outlines per A4 page, each **85.60 x 53.98 mm**, and a 50 mm scale line. Preview it. Determine the actual printer and its main A4 tray; do not rely on automatic source selection when it reports no paper.

   ```powershell
   .\print_yoto_labels.ps1 -Pdf "<private folder>\prepared\card-labels.pdf" -Printer "<installed printer name>" -Tray "<main tray name>" -DryRun
   # When paper is loaded and the preview is correct, use the same command without -DryRun.
   ```

   The Windows helper renders at 300 dpi, selects A4/simplex/one copy, compensates printer hard margins and draws at actual size. It rejects non-A4 input. `-DryRun` renders and checks the printer/tray without submitting a job. The Python used for rendering must have PyMuPDF; pass `-Python` if using a venv. If printing stalls, inspect the printer's queue/paper state before retrying so duplicate jobs do not emerge later. Queue acceptance is not proof a sheet printed.
13. Ask only for physical help that cannot be automated: load paper, confirm the sheet emerged, measure the 50 mm line, cut/tape labels, hold cards to NFC, unlock the phone, or power/connect the player. Final status should distinguish **uploaded**, **cards linked**, **labels printed**, and **offline download verified**. Preserve that status in the private manifest for the next session.

For a new batch, start with photographs and [WORKFLOW.md](WORKFLOW.md), finish verified ripping, then return here. Login and device setup should normally be reused, not repeated.

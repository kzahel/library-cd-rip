# Library CD Rip

A local Windows app for turning a stack of library CDs into MP3s, with a photo queue, spoken directions and a fullscreen screen a young child can supervise. Built from the fre:ac workflow that copied our six-CD batch successfully.

## Start

Double-click **Start Library CD Rip.cmd**. The first launch installs two small Python libraries and a checksum-verified portable fre:ac into `%LOCALAPPDATA%\LibraryCDRip`. Requires Windows 10/11 x64, Python 3.11+ and a USB audio-CD drive. No administrator access, online account or paid service is needed. The first dependency download needs internet; subsequent ripping works offline.

1. A grown-up adds **front-cover photos**, one per CD. They are sorted by capture time (EXIF, then camera filename, then file time). Move cards up/down to change the order. For a box with several discs, add its photo once per disc and put “CD 1”, “CD 2”… in the names.
2. Check the title and artist/series. Optional back-cover photos help you type track names, one per line. The app does **not** automatically recognise text in photos. Missing track names become numbered tracks. Photos stay on this PC.
3. Connect the drive. Close Windows Media Player and other rippers. Check the drive, music folder and **English or German** voice. Start with an empty tray, turn the volume up, then click **Start the mission with sound**.
4. Your helper follows the pictures and voice: insert the pictured CD, wait while the bar fills, then remove it only after the green finished screen. The app never automatically ejects a CD. There is a big **Hear it again** button; animated dots show when the app is working.

The whole batch ends with a green **All CDs saved!** screen. F11 / Escape exits fullscreen. Grown-up controls can pause, retry or move a troublesome CD to the end. Deferring first stops the encoder; the app then tells the grown-up to remove that CD, leave the tray empty and resume. Pausing preserves completed tracks and the queue. On a later launch, click **Continue with sound**. Use **Edit remaining CD names** to correct metadata or a track-count mismatch before resuming.

For multiple optical drives, match the Windows drive letter and the fre:ac device selector. For the simplest setup, connect only the USB CD drive being used. A newly inserted CD is associated with the next photo in the queue; the app cannot identify the physical cover for you. Keep discs in the chosen order.

## Files and recovery

- Output: `Music\<artist>\<album>\01 <track>.mp3` by default, **192 kbps CBR MP3**. Names are tagged and cleaned for Windows. Existing album folders are preserved; another copy gets `(2)`, `(3)`, etc.
- Photos, drafts, batches, logs and completion journals: `%LOCALAPPDATA%\LibraryCDRip`. No private photos or music live in this source directory.
- Incomplete audio: `<music folder>\.library-cd-rip-staging\<batch>\<disc>`. It is retained for recovery. A resumed track is reused only when its successful encoder receipt, SHA-256 and audio validation all agree.
- Progress is checked each second. The active-track bar estimates encoded audio from CBR bytes; time remaining is an estimate. Green requires successful encoder exit, every MP3 duration within two seconds of the CD, a valid MP3 header, closed files, a four-second settle, and a durable completion record.
- During a mission the app temporarily disables Windows AutoPlay and WMP automatic copying/ejecting, to keep Explorer from covering the child screen. **Pause** or **Close the app** restores the previous settings. After an interrupted process, the next launch restores them before starting. Closing only the browser leaves the local copier running so it can finish; reopen the launcher to reconnect.
- A stopped encoder, wrong disc after an interruption, no output growth for five minutes, missing drive or stale monitor gives an adult-help screen. Nothing ejects automatically. If the USB hardware itself repeatedly opens its tray, pause and check its cable/power before resuming.
- The web server accepts only local requests at `http://127.0.0.1:8735`. It is not published or reachable over the LAN. Start a second time to reopen the same app. No chat session is needed.

Keep the runtime folder with your music if you want to back up progress and original photos. Do not delete staging files while a mission is copying.

## Photo-assisted agent workflow

You can also give an assistant front and back photos and ask it to prepare the queue. See [WORKFLOW.md](WORKFLOW.md). The assistant can transcribe names and use `prepare.py --metadata reviewed.json <front photos>`; a grown-up still reviews the queue before the drive starts. Each CD needs its own front-photo argument, in photo-time order. The reusable app remains fully usable without an assistant.

## Put the albums on Yoto cards

Follow [YOTO_WORKFLOW.md](YOTO_WORKFLOW.md) for grouping albums onto Make Your Own cards, preparing ordered uploads, linking physical cards with a phone and checking player downloads. `yoto_prepare.py` validates card limits, copies audio without changing the originals, generates actual-size contents labels and preserves upload/linking receipts on reruns. `print_yoto_labels.ps1` prints the A4 PDF at 100%, with an explicit printer/tray and a dry-run option. The Yoto stage is an assistant workflow; website uploads and NFC linking still use the official Yoto interfaces.

## Development

```powershell
python bootstrap.py
python app.py --no-browser
python -m pip install -r requirements-yoto.txt
python -m unittest discover -s tests -p 'test_*.py' -v
npm ci
npm run test:ui
```

Python standard-library server; Pillow reads/rotates photos, Mutagen verifies and tags MP3s; fre:ac 1.1.7 portable does the ripping. This tested version is pinned in `bootstrap.py` with its download checksum. The source does not bundle third-party binaries; their license files remain inside the downloaded fre:ac distribution.

`monitor.py` handles Windows MCI, file validation and completion. `freac_monitor.py` owns exactly one encoder process, tracks progress and records verified-track receipts. `storage.py` owns photo intake and durable batches. `app.py` serves the setup and child UI; `windows.py` discovers drives and journals temporary AutoPlay settings. Tests use isolated temporary state and mocked hardware; browser smoke tests use a separate Playwright Chromium binary.

This project was extracted from `dotfiles/scripts/cd-helper`. It uses a separate runtime directory and does not alter the original six-CD session or its MP3s.

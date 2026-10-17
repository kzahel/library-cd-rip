# Prepare a photo-first CD mission with an assistant

1. Start with the user's cover photographs. Inspect each front and back. Sort front covers by capture time, using EXIF or `PXL_YYYYMMDD_HHMMSSmmm` filenames. Ask only about unreadable titles, uncertain disc counts or ambiguous track order. Never invent track names. A multi-disc package needs one queue entry per physical CD, with the disc number in its title.
2. Transcribe album title, artist/series, optional year and numbered track names from the actual photos. Back-cover stories are not necessarily CD track boundaries: leave `titles` empty when unsure. Match each entry by its exact front-photo filename. A reviewed JSON file looks like:

```json
[
  {
    "photo": "PXL_20261017_124259354.jpg",
    "back": "PXL_20261017_124316899.jpg",
    "title": "Papa Moll und das Unwetter",
    "artist": "Papa Moll",
    "year": "2025",
    "titles": []
  }
]
```

3. Run `python bootstrap.py`, then `python prepare.py --metadata <reviewed.json> <front1.jpg> <front2.jpg> ...`. This creates a draft only. It never touches the drive. Keep metadata JSON in a private temporary folder, not the source tree. An existing photo draft is preserved rather than replaced.
4. Open **Start Library CD Rip.cmd**, verify the queue and output folder with the grown-up, choose the voice language, then start with sound. The child sees only the mission screen. Let the app own ripping; do not also launch WMP, another encoder, or a script that ejects trays. Do not announce completion based on a timer or a file existing.
5. If supervising in a chat, check `/api/status` proactively about every ten seconds. The local app itself checks each second. Green completion is based on child-process success plus audio validation. Keep the app in the foreground. A failed CD can be deferred using grown-up controls; do not pretend it was saved. Avoid changing the drive's queue binding while it is active.
6. At the end verify the batch journal and MP3 count. Photos, queue and logs live under `%LOCALAPPDATA%\LibraryCDRip`; completed audio lives in the chosen Music folder. Preserve them for a later resume.

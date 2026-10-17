"use strict";
const $ = (s) => document.querySelector(s);
const el = (name, cls, text) => {
  const node = document.createElement(name);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};
let session,
  draft,
  view = "setup",
  sound = false,
  current,
  lastKey = "",
  lastSpokenAt = 0,
  saving,
  saveWork = Promise.resolve(),
  busy = false,
  stopped = false;
const speech = {
  "en-GB": {
    ready: [
      "Put in this CD!",
      "Choose the CD in the picture. Shiny side down. Close the tray gently.",
      "💿",
    ],
    empty: [
      "Put in this CD!",
      "Choose the CD in the picture. Shiny side down. Close the tray gently.",
      "💿",
    ],
    connecting: [
      "Checking the drive…",
      "Please wait. I am checking the CD drive.",
      "💿",
    ],
    reading: [
      "Checking your CD…",
      "Leave the CD inside. I am getting ready.",
      "💿",
    ],
    ripping: [
      "Wait — copying!",
      "Keep the tray closed. I will tell you when your CD is finished.",
      "💿",
    ],
    done: [
      "Take it out!",
      "Press the drive button. Put this CD back in its case. Then choose the next picture.",
      "✅",
    ],
    finished: [
      "All CDs saved!",
      "Press the drive button and put the last CD in its case. You finished the whole mission. Thank you for helping!",
      "⭐",
    ],
    error: [
      "Ask a grown-up",
      "Please leave the CD inside. I need a grown-up to help.",
      "✋",
    ],
    offline: [
      "Ask a grown-up",
      "The copier is not answering. Please leave the CD inside and ask a grown-up.",
      "✋",
    ],
    paused: [
      "Time for a break",
      "Please ask a grown-up to start the mission again.",
      "⏸",
    ],
    working: "I’m working on it…",
    again: "🔊 Hear it again",
    saved: "CDs saved ⭐",
    next: "Next CD",
    track: "Track",
    of: "of",
    wait: "Working out how long…",
    minute: "About {n} minutes left. Wait for green.",
    checked: "Checked every second",
    fullscreen: "⛶ Full screen",
    adult: "Grown-up controls",
  },
  "de-DE": {
    ready: [
      "Diese CD einlegen!",
      "Nimm die CD auf dem Bild. Die glänzende Seite kommt nach unten. Schließe das Fach vorsichtig.",
      "💿",
    ],
    empty: [
      "Diese CD einlegen!",
      "Nimm die CD auf dem Bild. Die glänzende Seite kommt nach unten. Schließe das Fach vorsichtig.",
      "💿",
    ],
    connecting: [
      "Ich prüfe das Laufwerk…",
      "Bitte warte. Ich prüfe das CD-Laufwerk.",
      "💿",
    ],
    reading: [
      "Ich prüfe deine CD…",
      "Lass die CD im Laufwerk. Ich mache alles bereit.",
      "💿",
    ],
    ripping: [
      "Warten — ich kopiere!",
      "Lass das Fach geschlossen. Ich sage dir, wenn deine CD fertig ist.",
      "💿",
    ],
    done: [
      "CD herausnehmen!",
      "Drücke den Knopf am Laufwerk. Lege diese CD zurück in ihre Hülle. Nimm dann die CD auf dem nächsten Bild.",
      "✅",
    ],
    finished: [
      "Alle CDs gespeichert!",
      "Drücke den Knopf am Laufwerk und lege die letzte CD in ihre Hülle. Alles ist fertig. Danke fürs Helfen!",
      "⭐",
    ],
    error: [
      "Frag einen Erwachsenen",
      "Lass die CD bitte im Laufwerk. Ich brauche Hilfe von einem Erwachsenen.",
      "✋",
    ],
    offline: [
      "Frag einen Erwachsenen",
      "Das Kopierprogramm antwortet nicht. Lass die CD im Laufwerk und hole einen Erwachsenen.",
      "✋",
    ],
    paused: [
      "Zeit für eine Pause",
      "Bitte einen Erwachsenen, die Aufgabe wieder zu starten.",
      "⏸",
    ],
    working: "Ich arbeite daran…",
    again: "🔊 Noch einmal hören",
    saved: "CDs gespeichert ⭐",
    next: "Nächste CD",
    track: "Titel",
    of: "von",
    wait: "Ich schätze die Wartezeit…",
    minute: "Noch ungefähr {n} Minuten. Warte auf Grün.",
    checked: "Wird jede Sekunde geprüft",
    fullscreen: "⛶ Vollbild",
    adult: "Für Erwachsene",
  },
};
const words = () =>
  speech[current?.language || draft?.language || "en-GB"] || speech["en-GB"];
function notice(message) {
  $("#notice").hidden = !message;
  $("#notice").textContent = message || "";
  if (message)
    $("#notice").scrollIntoView({ block: "center", behavior: "smooth" });
}
async function api(path, data) {
  const response = await fetch("/api/" + path, {
    method: data === undefined ? "GET" : "POST",
    headers: data === undefined ? {} : { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(path === "photo" ? 60000 : 35000),
  });
  const result = await response.json();
  if (!response.ok)
    throw Error(result.error || "The app could not finish that step.");
  return result;
}
function settings() {
  if (!draft) return;
  draft.drive = $("#drive").value;
  draft.drive_index = Number($("#encoder").value || 0);
  draft.music = $("#music").value;
  draft.language = $("#language").value;
}
async function save() {
  clearTimeout(saving);
  settings();
  const snapshot = structuredClone(draft);
  saveWork = saveWork.catch(() => {}).then(() => api("draft", snapshot));
  await saveWork;
}
function changed() {
  settings();
  clearTimeout(saving);
  saving = setTimeout(() => save().catch((e) => notice(e.message)), 500);
}
function field(label, value, onchange, textarea = false) {
  const wrapper = el("label", "", label);
  const input = el(textarea ? "textarea" : "input");
  input.value = value || "";
  input.oninput = () => {
    onchange(input.value);
    changed();
  };
  wrapper.append(input);
  return wrapper;
}
function action(label, title, fn) {
  const button = el("button", "", label);
  button.type = "button";
  button.title = title;
  button.setAttribute("aria-label", title);
  button.onclick = fn;
  return button;
}
function renderAlbums() {
  const container = $("#albums");
  const openCards = new Set(
    [...container.querySelectorAll(".album-card")]
      .filter((card) => card.querySelector("details")?.open)
      .map((card) => card.dataset.id),
  );
  container.replaceChildren();
  $("#empty").hidden = !!draft.albums.length;
  draft.albums.forEach((album, index) => {
    const card = el("article", "album-card");
    card.dataset.id = album.id;
    const img = el("img");
    img.src = album.cover;
    img.alt = album.title || `CD ${index + 1} cover`;
    card.append(img);
    const body = el("div");
    card.append(body);
    const head = el("div", "card-head");
    head.append(el("strong", "", `CD ${index + 1}`));
    const actions = el("div", "card-actions");
    actions.append(
      action("↑", "Move CD earlier", () => move(index, -1)),
      action("↓", "Move CD later", () => move(index, 1)),
      action("×", "Remove CD from queue", () => {
        draft.albums.splice(index, 1);
        renderAlbums();
        changed();
      }),
    );
    head.append(actions);
    body.append(head);
    const fields = el("div", "fields");
    fields.append(
      field("Album / story title", album.title, (v) => (album.title = v)),
      field("Artist / series", album.artist, (v) => (album.artist = v)),
    );
    body.append(fields);
    const details = el("details");
    details.open = openCards.has(album.id);
    details.append(
      el(
        "summary",
        "",
        album.back
          ? "Back cover & track names"
          : "Add back cover / track names (optional)",
      ),
    );
    const back = el("div", "back");
    if (album.back) {
      const backImg = el("img");
      backImg.src = album.back;
      backImg.alt = "Back cover with track names";
      back.append(backImg);
    }
    const upload = el("label", "upload", "＋ Back-cover photo");
    const input = el("input");
    input.type = "file";
    input.accept = "image/jpeg,image/png,image/webp";
    upload.append(input);
    back.append(upload);
    input.onchange = async () => {
      try {
        busy = true;
        const photo = await uploadPhoto(input.files[0]);
        album.back = photo.url;
        await save();
        renderAlbums();
      } catch (e) {
        notice(e.message);
      } finally {
        busy = false;
      }
    };
    details.append(
      back,
      el(
        "p",
        "",
        "Optional: type one track name per line from the back cover. If left blank, tracks are numbered. Names must match the CD track count.",
      ),
      field(
        "Track names — one per line",
        (album.titles || []).join("\n"),
        (v) =>
          (album.titles = v
            .split("\n")
            .map((t) => t.trim())
            .filter(Boolean)),
        true,
      ),
      field("Year (optional)", album.year, (v) => (album.year = v)),
    );
    body.append(details);
    container.append(card);
  });
}
function move(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= draft.albums.length) return;
  [draft.albums[index], draft.albums[target]] = [
    draft.albums[target],
    draft.albums[index],
  ];
  renderAlbums();
  changed();
}
function setDrives(devices) {
  $("#drive").replaceChildren();
  for (const letter of devices.letters) {
    const option = el("option", "", letter + " — CD drive");
    option.value = letter;
    $("#drive").append(option);
  }
  if (!devices.letters.length) {
    const option = el("option", "", "Connect your USB CD drive");
    option.value = "";
    $("#drive").append(option);
  }
  if (devices.letters.includes(draft.drive)) $("#drive").value = draft.drive;
  $("#encoder").replaceChildren();
  for (const drive of devices.encoders) {
    const option = el("option", "", `${drive.index}: ${drive.name}`);
    option.value = drive.index;
    $("#encoder").append(option);
  }
  $("#encoder").value = String(draft.drive_index || 0);
  $("#encoderLabel").hidden = devices.encoders.length < 2;
  if (devices.letters.length > 1)
    notice(
      "Multiple CD drives found. Match the Windows drive letter and the fre:ac drive before starting. Use only one connected drive if unsure.",
    );
}
async function refreshSession() {
  session = await api("session");
  draft = session.draft;
  $("#music").value = draft.music || session.default_music;
  $("#language").value = draft.language || "en-GB";
  setDrives(session.devices);
  renderAlbums();
  const active = session.active;
  $("#resume").hidden = !active;
  $("#resumeTitle").textContent = active?.finished
    ? "Last mission complete"
    : "Continue your saved mission";
  $("#resumeDetail").textContent = active
    ? `${active.completed} of ${active.albums.length} CDs saved. ${active.albums[0]?.title || ""}`
    : "";
  $("#resumeButton").textContent = active?.finished
    ? "⭐ Show finished mission"
    : "▶ Continue with sound";
  $("#history").replaceChildren();
  for (const batch of session.history) {
    const button = el(
      "button",
      "",
      `${batch.created.slice(0, 10)} · ${batch.completed}/${batch.albums.length} CDs · ${batch.albums[0]?.title || "Mission"}`,
    );
    button.onclick = () => resume(batch.id);
    $("#history").append(button);
  }
}
function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = () => reject(Error("Could not open photo."));
    reader.readAsDataURL(file);
  });
}
async function uploadPhoto(file) {
  if (!file) throw Error("Choose a photo first.");
  if (file.size > 25 * 1024 * 1024)
    throw Error("Please use photos smaller than 25 MB.");
  return api("photo", {
    name: file.name,
    modified: file.lastModified,
    data: await readFile(file),
  });
}
$("#photos").onchange = async (event) => {
  busy = true;
  $("#start").disabled = true;
  notice("");
  try {
    for (const [index, file] of [...event.target.files].entries()) {
      $("#uploading").textContent =
        `Adding photo ${index + 1} of ${event.target.files.length}…`;
      const photo = await uploadPhoto(file);
      draft.albums.push({
        id: photo.id,
        title: "",
        artist: "",
        cover: photo.url,
        captured: photo.captured,
        titles: [],
      });
    }
    draft.albums.sort((a, b) => a.captured.localeCompare(b.captured));
    renderAlbums();
    await save();
    $("#uploading").textContent = "Photos added. Check the names below.";
  } catch (e) {
    renderAlbums();
    await save().catch(() => {});
    notice(e.message);
  } finally {
    busy = false;
    $("#start").disabled = false;
    event.target.value = "";
  }
};
$("#sort").onclick = () => {
  draft.albums.sort((a, b) => a.captured.localeCompare(b.captured));
  renderAlbums();
  changed();
};
for (const name of ["drive", "encoder", "language", "music"])
  $("#" + name).onchange = changed;
$("#refresh").onclick = async () => {
  try {
    settings();
    setDrives(await api("refresh-drives", {}));
    changed();
  } catch (e) {
    notice(e.message);
  }
};
function say(text) {
  if (!sound || !("speechSynthesis" in window)) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = current?.language || draft?.language || "en-GB";
  utterance.rate = 0.85;
  const voices = speechSynthesis.getVoices();
  const voice =
    voices.find((v) => v.lang === utterance.lang) ||
    voices.find((v) => v.lang.startsWith(utterance.lang.slice(0, 2)));
  if (voice) utterance.voice = voice;
  utterance.onerror = (e) => {
    if (!["canceled", "interrupted"].includes(e.error)) {
      $("#checked").textContent =
        "Voice needs help — check volume and press 🔊";
    }
  };
  speechSynthesis.speak(utterance);
  lastSpokenAt = Date.now();
}
function unlockSound() {
  sound = true;
  say(
    draft?.language === "de-DE"
      ? "Ich bin bereit. Bitte warte einen Moment."
      : "Sound is on. Please wait while I get ready.",
  );
}
function showMission() {
  view = "mission";
  $("#setup").hidden = true;
  $("#mission").hidden = false;
  lastKey = "";
  if ($("#soundGate").open) $("#soundGate").close();
}
function fullScreen() {
  if (!document.fullscreenElement)
    document.documentElement.requestFullscreen().catch(() => {});
}
async function begin() {
  if (busy) return;
  notice("");
  settings();
  if (
    !draft.albums.length ||
    draft.albums.some((a) => !a.title.trim() || !a.artist.trim())
  )
    return notice(
      "Please check the title and artist / series on every CD card.",
    );
  if (!draft.drive)
    return notice("Connect your USB CD drive, then press Find drives.");
  $("#start").disabled = true;
  unlockSound();
  fullScreen();
  try {
    await save();
    await api("start", draft);
    showMission();
    await pollOnce();
  } catch (e) {
    notice(e.message);
    await refreshSession().catch(() => {});
  } finally {
    $("#start").disabled = false;
  }
}
async function resume(identity) {
  if (busy) return;
  notice("");
  unlockSound();
  fullScreen();
  try {
    await save();
    await api("resume", {
      id: identity || session.active.id,
      drive: draft.drive,
      drive_index: draft.drive_index,
      language: draft.language,
    });
    showMission();
    await pollOnce();
  } catch (e) {
    notice(e.message);
    await refreshSession().catch(() => {});
  }
}
$("#start").onclick = begin;
$("#resumeButton").onclick = () => resume();
function instructions(status) {
  const dictionary = words();
  return dictionary[status.phase] || dictionary.error;
}
function spoken(status) {
  const line = instructions(status);
  return (
    line[0] +
    ". " +
    line[1] +
    (["ready", "empty"].includes(status.phase) && status.next_title
      ? " " + status.next_title + "."
      : "")
  );
}
function renderMission(status) {
  current = status;
  const w = words(),
    line = instructions(status);
  document.documentElement.lang = (status.language || "en-GB").slice(0, 2);
  document.body.className = "playing " + status.phase;
  $("#childTitle").textContent = line[0];
  $("#childInstruction").textContent = line[1];
  $("#symbol").textContent = line[2];
  $("#saved").textContent = `${status.completed || 0} ${w.saved}`;
  const working = ["connecting", "reading", "ripping"].includes(status.phase);
  $("#thinking").hidden = !working;
  $("#thinkingText").textContent = w.working;
  const showCover =
    !!status.next_cover && ["ready", "empty", "done"].includes(status.phase);
  $("#coverPanel").hidden = !showCover;
  if (showCover) {
    if ($("#cover").getAttribute("src") !== status.next_cover)
      $("#cover").src = status.next_cover;
    $("#coverTitle").textContent = status.next_title;
    $("#coverCaption").textContent =
      `${w.next} · ${status.queue_position} / ${status.queue_total}`;
  }
  $("#symbol").hidden = showCover;
  $("#progress").hidden = !["ripping", "done"].includes(status.phase);
  const p = Math.max(0, Math.min(100, status.progress || 0));
  $("#fill").style.width = p + "%";
  $("#rail").setAttribute("aria-valuenow", p);
  $("#percent").textContent = p + "%";
  $("#track").textContent =
    `${w.track} ${status.track || 1} ${w.of} ${status.tracks || "…"}`;
  $("#eta").textContent =
    status.phase === "done"
      ? "✓"
      : status.eta > 0
        ? w.minute.replace("{n}", Math.max(1, Math.ceil(status.eta / 60)))
        : w.wait;
  $("#currentAlbum").textContent = status.album || "";
  $("#repeat").textContent = w.again;
  $("#checked").textContent = w.checked;
  $("#fullscreen").textContent = w.fullscreen;
  $("#adultLabel").textContent = w.adult;
  $("#diagnostic").textContent = status.detail || "";
  $("#retry").hidden = !["error", "offline"].includes(status.phase);
  $("#defer").hidden = !["error", "offline", "ready", "empty"].includes(
    status.phase,
  );
  const key = [status.batch, status.phase, status.next_cover].join("|");
  if (key !== lastKey) {
    lastKey = key;
    say(spoken(status));
  } else if (
    Date.now() - lastSpokenAt > 60000 &&
    ["ready", "empty", "done", "ripping"].includes(status.phase)
  ) {
    say(spoken(status));
  }
}
async function pollOnce() {
  try {
    const status = await api("status");
    current = status;
    if (view === "mission") renderMission(status);
  } catch (e) {
    if (view === "mission" && current?.phase !== "finished")
      renderMission({
        phase: "offline",
        language: current?.language,
        completed: current?.completed,
      });
    else if (view === "setup")
      notice("Cannot reach the local app. Open Start Library CD Rip again.");
  }
}
async function poll() {
  if (stopped) return;
  await pollOnce();
  setTimeout(poll, 1000);
}
$("#repeat").onclick = () => {
  sound = true;
  say(spoken(current));
};
$("#fullscreen").onclick = fullScreen;
async function showSetup() {
  view = "setup";
  sound = false;
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  document.body.className = "";
  document.documentElement.lang = "en";
  $("#setup").hidden = false;
  $("#mission").hidden = true;
  $("#saved").textContent = "Photo → CD → music";
  if ($("#soundGate").open) $("#soundGate").close();
  await refreshSession();
}
$("#editSaved").onclick = async () => {
  try {
    await api("pause", {});
    await refreshSession();
    const fields = $("#savedFields");
    fields.replaceChildren();
    for (const album of session.active.albums) {
      if (album.saved) continue;
      const card = el("div", "panel");
      const image = el("img");
      image.src = album.cover;
      image.alt = "CD cover";
      image.width = 120;
      card.append(image);
      const body = el("div");
      body.append(
        field("Title", album.title, (v) => (album.title = v)),
        field("Artist / series", album.artist, (v) => (album.artist = v)),
        field(
          "Track names — one per line",
          (album.titles || []).join("\n"),
          (v) =>
            (album.titles = v
              .split("\n")
              .map((t) => t.trim())
              .filter(Boolean)),
          true,
        ),
      );
      card.append(body);
      fields.append(card);
    }
    $("#savedEditor").hidden = false;
    $("#savedEditor").scrollIntoView({ block: "start", behavior: "smooth" });
  } catch (e) {
    notice(e.message);
  }
};
$("#saveNames").onclick = async () => {
  try {
    await api("edit-batch", { albums: session.active.albums });
    $("#savedEditor").hidden = true;
    await refreshSession();
    notice("Corrections saved. Continue the saved mission when you are ready.");
  } catch (e) {
    notice(e.message);
  }
};
$("#pause").onclick = async () => {
  if (
    !confirm(
      "Pause copying and return to setup? Keep an unfinished CD in its case for resuming.",
    )
  )
    return;
  try {
    await api("pause", {});
    await showSetup();
  } catch (e) {
    alert(e.message);
  }
};
$("#retry").onclick = async () => {
  try {
    await api("retry", {});
  } catch (e) {
    alert(e.message);
  }
};
$("#defer").onclick = async () => {
  if (
    !confirm(
      "Stop this CD and move it to the end of the queue? Wait for the next message before removing it.",
    )
  )
    return;
  try {
    const result = await api("defer", {});
    await showSetup();
    notice(result.message);
  } catch (e) {
    await showSetup();
    notice(e.message);
  }
};
$("#quit").onclick = async () => {
  try {
    await save();
    await api("quit", {});
    stopped = true;
    notice("App closed. You can close this window.");
  } catch (e) {
    notice(e.message);
  }
};
$("#soundContinue").onclick = () => {
  unlockSound();
  fullScreen();
  showMission();
  if (current) renderMission(current);
};
$("#gateSetup").onclick = () => showSetup().catch((e) => notice(e.message));
async function init() {
  try {
    await refreshSession();
    if (session.running) {
      $("#soundGate").showModal();
    }
    poll();
  } catch (e) {
    notice(e.message);
  }
}
init();

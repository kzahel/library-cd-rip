// Uses a separately identified Playwright Chromium, never the normal browser.
const { chromium } = require("playwright-core");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "..");
const artifacts = path.join(root, ".artifacts");
fs.mkdirSync(artifacts, { recursive: true });
const candidates = fs
  .readdirSync(path.join(process.env.LOCALAPPDATA, "ms-playwright"))
  .filter((n) => /^chromium-\d+$/.test(n))
  .sort((a, b) => Number(b.split("-")[1]) - Number(a.split("-")[1]));
const executable =
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ||
  path.join(
    process.env.LOCALAPPDATA,
    "ms-playwright",
    candidates[0] || "missing",
    "chrome-win64",
    "chrome.exe",
  );
if (!fs.existsSync(executable))
  throw Error(
    "Install a Playwright Chromium build, or set PLAYWRIGHT_CHROMIUM_EXECUTABLE.",
  );
const fixture = spawn("python", ["tests/fixture_server.py"], {
  cwd: root,
  windowsHide: true,
  stdio: ["ignore", "pipe", "inherit"],
});
let browser;
const timeout = setTimeout(() => {
  fixture.kill();
  process.exitCode = 1;
}, 90000);
(async () => {
  const url = await new Promise((resolve, reject) => {
    fixture.stdout.once("data", (data) => resolve(data.toString().trim()));
    fixture.once("error", reject);
    fixture.once("exit", (code) => reject(Error("Fixture exited: " + code)));
  });
  browser = await chromium.launch({
    executablePath: executable,
    headless: true,
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    window.testSpeech = [];
    Object.defineProperty(window, "speechSynthesis", {
      value: {
        cancel() {},
        getVoices() {
          return [];
        },
        speak(utterance) {
          window.testSpeech.push(utterance.text);
        },
      },
    });
  });
  await page.goto(url);
  await page
    .getByRole("heading", { name: "Start with the pictures." })
    .waitFor();
  // A valid tiny PNG; upload order is intentionally the reverse of photo order.
  const pixel = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cOioAAAAASUVORK5CYII=",
    "base64",
  );
  await page.locator("#photos").setInputFiles([
    {
      name: "PXL_20261017_124630034.png",
      mimeType: "image/png",
      buffer: pixel,
    },
    {
      name: "PXL_20261017_124619666.png",
      mimeType: "image/png",
      buffer: pixel,
    },
  ]);
  await page.getByText("Photos added. Check the names below.").waitFor();
  const cards = page.locator(".album-card");
  assert.equal(await cards.count(), 2);
  const draft = await (await page.request.get(url + "/api/session")).json();
  assert(
    draft.draft.albums[0].captured < draft.draft.albums[1].captured,
    "photo order must be chronological",
  );
  await cards.nth(0).getByLabel("Album / story title").fill("First story");
  await cards.nth(0).getByLabel("Artist / series").fill("Storyteller");
  await cards.nth(1).getByLabel("Album / story title").fill("Second story");
  await cards.nth(1).getByLabel("Artist / series").fill("Storyteller");
  await cards.nth(0).locator("summary").click();
  await cards
    .nth(0)
    .locator('input[type="file"]')
    .setInputFiles({ name: "back.png", mimeType: "image/png", buffer: pixel });
  await cards.nth(0).getByAltText("Back cover with track names").waitFor();
  await cards
    .nth(0)
    .getByLabel("Track names — one per line")
    .fill("First chapter\nSecond chapter");
  await page.screenshot({
    path: path.join(artifacts, "setup.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Start the mission with sound", exact: false })
    .click();
  await page
    .getByRole("heading", { name: "Put in this CD!", exact: true })
    .waitFor();
  assert.equal(await page.locator("#coverTitle").textContent(), "First story");
  assert(
    (await page.evaluate(() => testSpeech)).some((text) =>
      text.includes("Shiny side down"),
    ),
  );
  await page.screenshot({ path: path.join(artifacts, "ready.png") });
  const phase = async (values) => {
    const response = await page.request.post(url + "/test/phase", {
      headers: { Origin: url },
      data: values,
    });
    assert(response.ok(), await response.text());
  };
  await phase({ phase: "ripping", progress: 42, track: 1, tracks: 2, eta: 80 });
  await page.getByRole("heading", { name: "Wait — copying!" }).waitFor();
  assert.equal(await page.locator("#rail").getAttribute("aria-valuenow"), "42");
  assert.equal(await page.locator("#thinking").isVisible(), true);
  await page.screenshot({ path: path.join(artifacts, "ripping.png") });
  await phase({ phase: "error" });
  await page
    .getByRole("heading", { name: "Ask a grown-up", exact: true })
    .waitFor();
  assert(
    (await page.evaluate(() => testSpeech)).some((text) =>
      text.includes("grown-up to help"),
    ),
  );
  await phase({ phase: "finished" });
  await page
    .getByRole("heading", { name: "All CDs saved!", exact: true })
    .waitFor();
  await page.screenshot({ path: path.join(artifacts, "finished.png") });
  await page.getByText("Grown-up controls", { exact: true }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Pause & setup", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Start with the pictures." })
    .waitFor();
  assert.equal(
    (await page.locator("#resumeDetail").textContent()).includes("2 of 2"),
    true,
  );
  await page
    .getByRole("button", { name: "Show finished mission", exact: false })
    .click();
  await page
    .getByRole("heading", { name: "All CDs saved!", exact: true })
    .waitFor();
  // New mission in German, then a page reload requires a fresh sound gesture.
  const germanDraft = structuredClone(draft.draft);
  germanDraft.language = "de-DE";
  germanDraft.drive = "E:";
  germanDraft.music = artifacts;
  for (const [index, album] of germanDraft.albums.entries()) {
    album.title = `Geschichte ${index + 1}`;
    album.artist = "Erzähler";
  }
  const started = await page.request.post(url + "/api/start", {
    headers: { Origin: url },
    data: germanDraft,
  });
  assert(started.ok(), await started.text());
  await page.reload();
  await page
    .getByRole("button", { name: "▶ Start with sound", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Diese CD einlegen!", exact: true })
    .waitFor();
  assert(
    (await page.evaluate(() => testSpeech)).some((text) =>
      text.includes("glänzende Seite"),
    ),
  );
  await page.screenshot({ path: path.join(artifacts, "german-ready.png") });
  assert.deepEqual(errors, [], "browser errors");
  console.log(
    "PASS: photos, chronological queue, names, sound gesture, cover, progress, error voice, completion, saved mission",
  );
})()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    clearTimeout(timeout);
    if (browser) await browser.close();
    fixture.kill();
  });

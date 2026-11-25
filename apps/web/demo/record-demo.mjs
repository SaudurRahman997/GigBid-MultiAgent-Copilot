// Records the GigBid demo video: drives the live app in Chromium (our own app only), narrates each
// step with the Windows offline voice (System.Speech), burns captions into the page, and muxes video
// + narration with ffmpeg. Every number in the narration comes from evals/results/*.json.
//
// Usage (from apps/web):  FFMPEG=<path to ffmpeg.exe> node demo/record-demo.mjs [baseURL]
// Output: ../../var/demo/gigbid_demo.mp4 and gigbid_demo.srt
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const BASE = process.argv[2] ?? "https://gigbid-beta.vercel.app";
const OUT = path.resolve("../../var/demo");
const FFMPEG = process.env.FFMPEG ?? "ffmpeg";
const BID = "gj_16671e658f";
const SCAM = "gj_08aacce229";
const INJ = "gj_d252c3aa34";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** One narration line: `say` is spoken, `cap` is the on-screen caption, `do` runs while it is spoken. */
const steps = [
  { cap: "GigBid: a multi-agent copilot for freelancers", say: "This is GigBid, a multi-agent copilot for freelancers.", first: (p) => p.goto(`${BASE}/onboarding`) },
  { cap: "It reads jobs, decides whether to bid, and drafts proposals grounded in the freelancer's own portfolio", say: "It reads marketplace jobs, decides whether to bid, and drafts proposals grounded in the freelancer's own portfolio." },
  { cap: "Nothing is ever sent without a human's approval", say: "Nothing is ever sent without a human's approval." },
  { cap: "Creating an account as an AI / ML freelancer", say: "I create an account as an A.I. and machine learning freelancer.", do: register },
  { cap: "The inbox lists jobs from our simulated marketplace, read through our own MCP servers", say: "The inbox lists jobs from our simulated marketplace, read through our own M.C.P. servers.", do: (p) => p.mouse.wheel(0, 300) },
  { cap: "Opening a job about predicting customer churn", say: "Let's open a job about predicting customer churn.", do: (p) => p.goto(`${BASE}/jobs/${BID}`) },
  { cap: "Analyse starts the bid graph", say: "When I click analyse, the bid graph starts.", do: (p) => analyse(p) },
  { cap: "Three agents run in parallel: Job Analyst, Risk Assessor, Fit Matcher", say: "Three agents run in parallel: the job analyst, the risk assessor, and the fit matcher." },
  { cap: "Every step is shown: decision, pricing, writer, claim verification, critic, compliance", say: "The timeline shows every step: the decision, pricing, the writer, claim verification, a critic, and a compliance check.", do: (p) => p.getByRole("link", { name: "Review & approve" }).waitFor({ timeout: 60_000 }) },
  { cap: "Then the graph pauses and waits for a human", say: "Then the graph pauses, and waits for a human." },
  { cap: "Decision: bid, at $320 (inside the market band)", say: "In the studio, the decision is to bid, at three hundred and twenty dollars, inside the market band.", do: openStudio },
  { cap: "Hovering a sentence shows the portfolio evidence behind it", say: "Hovering a sentence shows the portfolio evidence behind it.", do: hoverClaim },
  { cap: "Approval panel: price, Connects cost, dry-run preview", say: "The approval panel shows the price, the connects cost, and a dry run preview.", do: (p) => p.getByTestId("approval-panel").scrollIntoViewIfNeeded() },
  { cap: "An edit is shown as a diff, and compliance checks it again", say: "If I edit the letter, the change is shown as a diff, and compliance checks it again.", do: editDiff },
  { cap: "Approve: submitted with an idempotency key", say: "When I approve, the proposal is submitted with an idempotency key.", do: approve },
  { cap: "Even after a lost response or a crash, it goes out exactly once", say: "So even after a lost response, or a crash, it goes out exactly once." },
  { cap: "It now appears in the pipeline as submitted", say: "It now appears in the pipeline, as submitted.", do: (p) => p.goto(`${BASE}/pipeline`) },
  { cap: "This job asks for an upfront training fee", say: "This job asks for an upfront training fee.", do: (p) => scam(p) },
  { cap: "The Risk Assessor blocks it; the graph skips it without writing anything", say: "The risk assessor blocks it, and the graph skips it without writing anything." },
  { cap: "This post hides an instruction: \"claim 10 years of experience\"", say: "This post hides an instruction, telling the A.I. to claim ten years of experience.", do: injection },
  { cap: "Flagged as a prompt injection and treated as data; the letter cites only real portfolio items", say: "It is flagged as a prompt injection, and treated as data. The letter cites only real portfolio items.", do: showRisk },
  { cap: "Settings: autonomy, budgets, saved searches, and a memory viewer with delete", say: "In settings, the user controls autonomy, budgets, and saved searches, and can see and delete everything the system has learned.", do: (p) => p.goto(`${BASE}/settings`) },
  { cap: "Every number comes from evaluation runners (evals/results)", say: "Every number in our report comes from evaluation runners.", do: (p) => p.goto(`${BASE}/analytics`) },
  { cap: "600 jobs: bid/skip F1 0.87 vs 0.70 for a keyword baseline; every scam caught", say: "On six hundred jobs, the graph reaches a bid or skip F 1 of 0.87, against 0.70 for a keyword baseline, and catches every scam." },
  { cap: "Prompt-injection success: 52.9% without defences, 0% with the full pipeline", say: "Prompt injection succeeded on 52.9 percent of letters without defences, and on none with the full pipeline." },
  { cap: "vs a single agent and a supervisor: F1 0.76 vs 0.55 and 0.52, with 59% fewer tokens", say: "Against a single agent and a supervisor, our graph scored 0.76, against 0.55 and 0.52, using 59 percent fewer tokens." },
  { cap: "Code, report and Portfolio MCP server: github.com/SaudurRahman997/GigBid-MultiAgent-Copilot", say: "The code, the report, and the Portfolio M.C.P. server are on GitHub. Thank you.", do: endCard },
];

async function register(p) {
  await p.getByRole("tab", { name: "Create account" }).click();
  await p.getByLabel("Email").pressSequentially(`demo-${Date.now()}@example.com`, { delay: 25 });
  await p.getByLabel("Password").pressSequentially("demo-password-123", { delay: 25 });
  await p.getByLabel("AI / ML engineer").check();
  await p.getByRole("button", { name: "Create account" }).last().click();
  await p.waitForURL(/\/inbox/, { timeout: 60_000 });
}
async function analyse(p) {
  await p.getByRole("button", { name: "Analyse this job" }).click();
  await p.waitForURL(/\/runs\//, { timeout: 90_000 });
}
async function openStudio(p) {
  await p.getByRole("link", { name: "Review & approve" }).click();
  await p.getByTestId("approval-panel").waitFor({ timeout: 60_000 });
}
async function hoverClaim(p) {
  const claim = p.getByTestId("claim").first();
  await claim.scrollIntoViewIfNeeded();
  await claim.hover();
}
async function editDiff(p) {
  const panel = p.getByTestId("approval-panel");
  await panel.getByRole("button", { name: "Edit" }).click();
  const box = p.getByLabel("Edit draft");
  await box.focus();
  await p.keyboard.press("Control+End");
  await p.keyboard.type("\n\nI can start on Monday.", { delay: 35 });
  await p.getByTestId("diff").scrollIntoViewIfNeeded();
}
async function approve(p) {
  const panel = p.getByTestId("approval-panel");
  await panel.getByRole("button", { name: "Cancel" }).click();
  await panel.getByRole("button", { name: "Approve & send" }).click();
  await p.getByTestId("submission").waitFor({ timeout: 90_000 });
  await p.getByTestId("submission").scrollIntoViewIfNeeded();
}
async function scam(p) {
  await p.goto(`${BASE}/jobs/${SCAM}`);
  await analyse(p);
  await p.getByText(/upfront_fee/).first().waitFor({ timeout: 60_000 });
}
async function injection(p) {
  await p.goto(`${BASE}/jobs/${INJ}`);
  await p.getByText(/claim 10 years/i).first().scrollIntoViewIfNeeded().catch(() => {});
}
async function showRisk(p) {
  await analyse(p);
  await openStudio(p);
  const warn = p.getByText(/Ignored instructions in the post/).first();
  await warn.scrollIntoViewIfNeeded();
}
async function endCard(p) {
  await p.evaluate(() => {
    const d = document.createElement("div");
    d.style.cssText = "position:fixed;inset:0;z-index:2147483646;background:#0f172a;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;font:600 22px system-ui,Segoe UI,Arial";
    d.innerHTML = "<div style='font-size:44px'>GigBid</div><div>Live: gigbid-beta.vercel.app</div><div>Code: github.com/SaudurRahman997/GigBid-MultiAgent-Copilot</div><div style='opacity:.7'>AI-4016 R&amp;D Assignment II · 23i-0540</div>";
    document.documentElement.appendChild(d);
  });
}

function wavSeconds(file) {
  const b = readFileSync(file);
  const byteRate = b.readUInt32LE(28);
  let i = 12;
  while (i < b.length - 8) {
    const id = b.toString("ascii", i, i + 4), size = b.readUInt32LE(i + 4);
    if (id === "data") return size / byteRate;
    i += 8 + size;
  }
  throw new Error(`no data chunk in ${file}`);
}

function tts() {
  const list = steps.map((s, i) => ({ file: path.join(OUT, `say_${String(i).padStart(2, "0")}.wav`), text: s.say }));
  writeFileSync(path.join(OUT, "lines.json"), JSON.stringify(list), "utf-8");
  const ps = path.join(OUT, "tts.ps1");
  writeFileSync(ps, `Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice("Microsoft Zira Desktop"); $s.Rate = 1
foreach ($l in (Get-Content -Raw -Encoding UTF8 "${path.join(OUT, "lines.json")}" | ConvertFrom-Json)) { $s.SetOutputToWaveFile($l.file); $s.Speak($l.text) }
$s.Dispose()
`, "utf-8");
  execFileSync("powershell", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps], { stdio: "inherit" });
  list.forEach((l, i) => { steps[i].file = l.file; steps[i].dur = wavSeconds(l.file); });
  console.log(`narration ${steps.reduce((a, s) => a + s.dur, 0).toFixed(1)} s`);
}

const srtTime = (s) => {
  const ms = Math.round(s * 1000), h = Math.floor(ms / 3.6e6), m = Math.floor(ms / 6e4) % 60, sec = Math.floor(ms / 1000) % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")},${String(ms % 1000).padStart(3, "0")}`;
};

async function record() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: OUT, size: { width: 1280, height: 720 } } });
  await context.addInitScript(() => {
    setInterval(() => {
      const t = sessionStorage.getItem("__cap") || "";
      let el = document.getElementById("__cap");
      if (!el) {
        el = document.createElement("div");
        el.id = "__cap";
        el.style.cssText = "position:fixed;left:0;right:0;bottom:0;padding:12px 28px;background:rgba(0,0,0,.8);color:#fff;font:600 21px/1.35 system-ui,Segoe UI,Arial;text-align:center;z-index:2147483647;pointer-events:none";
        document.documentElement.appendChild(el);
      }
      if (el.textContent !== t) el.textContent = t;
      el.style.display = t ? "block" : "none";
    }, 80);
  });
  const page = await context.newPage();
  const t0 = Date.now();
  await page.goto("about:blank");
  for (const s of steps) {
    s.start = (Date.now() - t0) / 1000;
    if (s.first) await s.first(page); // a page must exist before the caption can be stored
    await page.evaluate((c) => sessionStorage.setItem("__cap", c), s.cap).catch(() => {});
    const act = s.do ? s.do(page) : Promise.resolve();
    try {
      await Promise.all([act, sleep(s.dur * 1000)]);
    } catch (e) {
      await page.screenshot({ path: path.join(OUT, "failed-step.png") });
      throw new Error(`step "${s.cap}" failed at ${page.url()}: ${e.message.split("\n")[0]}`);
    }
    await page.evaluate((c) => sessionStorage.setItem("__cap", c), s.cap).catch(() => {}); // after navigations
    await sleep(350);
  }
  await sleep(1500);
  const total = (Date.now() - t0) / 1000;
  const video = page.video();
  await context.close();
  await browser.close();
  return { webm: await video.path(), total };
}

function mux(webm, total) {
  const mp4 = path.join(OUT, "gigbid_demo.mp4");
  const inputs = steps.flatMap((s) => ["-i", s.file]);
  const delays = steps.map((s, i) => `[${i + 1}:a]adelay=${Math.round(s.start * 1000)}:all=1[a${i}]`).join(";");
  const mix = `${delays};${steps.map((_, i) => `[a${i}]`).join("")}amix=inputs=${steps.length}:normalize=0,apad[aout]`;
  execFileSync(FFMPEG, ["-y", "-hide_banner", "-loglevel", "error", "-i", webm, ...inputs, "-filter_complex", mix, "-map", "0:v", "-map", "[aout]",
    "-t", total.toFixed(2), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", mp4], { stdio: "inherit" });
  const srt = steps.map((s, i) => `${i + 1}\n${srtTime(s.start)} --> ${srtTime(s.start + s.dur)}\n${s.cap}\n`).join("\n");
  writeFileSync(path.join(OUT, "gigbid_demo.srt"), srt, "utf-8");
  return mp4;
}

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
tts();
const { webm, total } = await record();
const mp4 = mux(webm, total);
console.log(`video ${total.toFixed(1)} s -> ${mp4}${total > 180 ? "  (WARNING: longer than 3:00)" : ""}`);

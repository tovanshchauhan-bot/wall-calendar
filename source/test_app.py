#!/usr/bin/env python3
"""End-to-end check of the built app (run via test.sh).

Signs in against the local Auth emulator, imports a made-up backup, ticks days,
adds an assessment, then goes offline and checks the app still opens, keeps its
data, saves new ticks and survives a reload. Firestore is pointed at a port with
nothing listening, so the app behaves exactly as it does with no internet.
"""
import datetime as dt, json, os, re, sys, tempfile
from zoneinfo import ZoneInfo
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
today = dt.datetime.now(ZoneInfo("Australia/Sydney")).date()
day = lambda n: (today + dt.timedelta(days=n)).isoformat()
sample = {"app": "wall-calendar", "version": 1,
          "items": [{"id": "sample-test", "date": day(7), "subject": "Physics", "name": "Sample test", "type": "Assessment Task", "weight": "", "notes": "", "done": False},
                    {"id": "sample-event", "date": day(30), "subject": "Other", "name": "Sample event", "type": "Event", "weight": "", "notes": "", "done": False}],
          "gym": [day(-1), day(-2), day(-5)], "run": [day(-2), day(-4)]}
tmp = tempfile.mkdtemp(); BACKUP = os.path.join(tmp, "sample-backup.json"); json.dump(sample, open(BACKUP, "w"))
NOISE = ("Could not reach Cloud Firestore", "net::ERR_", "WebChannelConnection", "Firestore (")
results = []
def check(cond, msg): results.append(("PASS " if cond else "FAIL ") + msg)
squash = lambda x: re.sub(r"\s+", " ", x).strip()

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 860}, timezone_id="Australia/Sydney", accept_downloads=True)
    pg = ctx.new_page(); errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and not any(n in m.text for n in NOISE) else None)
    pg.on("pageerror", lambda e: errors.append("PAGE ERROR " + str(e)))
    train = lambda: squash(pg.inner_text("#train"))
    pressed = lambda kind: pg.get_attribute(f'.day.today .lane[data-act="{kind}"]', "aria-pressed")

    pg.goto(URL); pg.wait_for_timeout(1200)
    check(pg.is_visible("#gate") and pg.is_enabled("#gateBtn"), "first visit shows the sign-in screen")
    pg.evaluate("window.__wcTestSignIn()"); pg.wait_for_selector("#gate", state="hidden", timeout=15000); pg.wait_for_timeout(1500)
    check(pg.get_attribute(".day.today", "data-date") == day(0), "signed in; today's square is " + day(0))

    pg.click("#tab-settings"); pg.set_input_files("#restoreFile", BACKUP); pg.wait_for_selector("#doRestore")
    found = squash(pg.inner_text("#restoreMsg")); pg.click("#doRestore")
    pg.wait_for_function("document.getElementById('restoreMsg').innerText.includes('Restored')", timeout=10000)
    check("Found 2 items, 3 gym days and 2 runs" in found, "backup file read: " + found[:60])
    pg.click("#tab-calendar"); pg.wait_for_timeout(500)
    check(re.search(r"GYM \d+ this month 3 last 7 days 3 last 30 days", train()) and re.search(r"RUN \d+ this month 2 last 7 days 2 last 30 days", train()), "imported ticks counted: " + train()[:150])
    check("Sample test" in pg.inner_text("#nextup") and "7 days" in pg.inner_text("#nextup"), "imported assessment in Next up, 7 days away")

    pg.click('.day.today .lane[data-act="run"]'); pg.wait_for_timeout(300)
    check(pressed("run") == "true" and "RUN" in train() and re.search(r"RUN \d+ this month 3 last 7 days", train()), "one click ticks a run today")
    pg.click("#addBtn"); pg.fill("#f-date", day(10)); pg.select_option("#f-subject", "Chemistry"); pg.fill("#f-name", "Module test"); pg.click("#f-save"); pg.wait_for_timeout(400)
    check("Module test" in pg.inner_text("#nextup"), "new assessment added through the form")
    check(squash(pg.inner_text("#sync")) in ("Syncing…", "Synced"), "sync pill online: " + squash(pg.inner_text("#sync")))

    pg.evaluate("navigator.serviceWorker.ready.then(() => true)"); pg.reload(); pg.wait_for_timeout(1500)
    check(pg.evaluate("!!navigator.serviceWorker.controller"), "service worker installed and in control")

    ctx.set_offline(True); pg.reload(); pg.wait_for_timeout(2500)
    check(pg.is_hidden("#gate") and pg.get_attribute(".day.today", "data-date") == day(0), "OFFLINE: app opens and stays signed in")
    check(re.search(r"RUN \d+ this month 3 last 7 days", train()) and "Module test" in pg.inner_text("#nextup"), "OFFLINE: all data present")
    check(squash(pg.inner_text("#sync")).startswith("Offline"), "OFFLINE: pill says " + squash(pg.inner_text("#sync")))
    pg.click('.day.today .lane[data-act="gym"]'); pg.wait_for_timeout(300)
    pg.reload(); pg.wait_for_timeout(2500)
    check(pressed("gym") == "true" and re.search(r"GYM \d+ this month 4 last 7 days", train()), "OFFLINE: a tick survives closing and reopening")
    fams = pg.evaluate("document.fonts.ready.then(() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/\"/g, '')))")
    check("Archivo" in fams and "IBM Plex Sans" in fams, "OFFLINE: fonts load from the device")
    check(not pg.evaluate("document.documentElement.scrollWidth > window.innerWidth"), "no sideways scroll at 1440px")

    ctx.set_offline(False); pg.wait_for_timeout(800); pg.click("#tab-settings")
    with pg.expect_download() as dl: pg.click("#dlJson")
    data = json.load(open(dl.value.path()))
    check(day(0) in data["gym"] and any(i.get("name") == "Module test" for i in data["items"]), "backup download contains the latest changes")
    pg.click("#signOutBtn"); pg.click("#signOutBtn"); pg.wait_for_selector("#gate", state="visible", timeout=8000)
    pg.evaluate("window.__wcTestSignIn()"); pg.wait_for_selector("#gate", state="hidden", timeout=15000); pg.click("#tab-calendar"); pg.wait_for_timeout(1500)
    check(re.search(r"GYM \d+ this month 4 last 7 days", train()), "sign out and back in keeps everything")
    check(not errors, "no unexpected console errors " + str(errors[:3]))
    browser.close()

print("\n".join(results)); passed = sum(r.startswith("PASS") for r in results)
print(f"{passed} / {len(results)} passed"); sys.exit(0 if passed == len(results) else 1)

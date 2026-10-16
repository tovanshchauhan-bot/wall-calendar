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
SHOTS = os.environ.get("WC_SHOTS")  # optional folder for screenshots
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
    nexttitles = lambda: " | ".join(pg.eval_on_selector_all("#nextup .chip", "cs => cs.map(c => c.title)"))
    nextlabels = lambda: [squash(x) for x in pg.eval_on_selector_all("#nextup .chip .ct", "cs => cs.map(c => c.textContent)")]
    def show_day(date):  # page forward until that day is on screen
        for _ in range(3):
            if pg.locator(f'.day[data-date="{date}"]').count(): return True
            pg.click("#nextBtn"); pg.wait_for_timeout(250)
        return False
    def day_tiles(date):
        if not show_day(date): return None
        return pg.evaluate("""d=>{const c=document.querySelector('.day[data-date="'+d+'"]'),h=c.getBoundingClientRect().height;
          return {cell:Math.round(h),tiles:[...c.querySelectorAll('.tile')].map(t=>{const b=t.querySelector('b'),l=[...b.children].find(x=>getComputedStyle(x).display!=='none');
            return {text:l.textContent,h:Math.round(t.getBoundingClientRect().height),fits:b.scrollWidth<=b.clientWidth+1,upper:getComputedStyle(b).textTransform}}),
            bars:[...c.querySelectorAll('.evbar')].map(e=>e.textContent)}}""", date)

    pg.goto(URL); pg.wait_for_timeout(1200)
    check(pg.is_visible("#gate") and pg.is_enabled("#gateBtn"), "first visit shows the sign-in screen")
    pg.evaluate("window.__wcTestSignIn()"); pg.wait_for_selector("#gate", state="hidden", timeout=15000); pg.wait_for_timeout(1500)
    check(pg.get_attribute(".day.today", "data-date") == day(0), "signed in; today's square is " + day(0))
    layout = pg.evaluate("""()=>{const out={pads:document.querySelectorAll('.day.pad').length,bad:[],counts:[]};
      document.querySelectorAll('.month').forEach(mo=>{const hs=[...mo.querySelectorAll('.wk span')].slice(1).map(x=>x.getBoundingClientRect().left);
        const days=[...mo.querySelectorAll('.day')],ds=days.map(c=>c.dataset.date),[y,m]=ds[0].split('-').map(Number);
        out.counts.push([ds.length,new Date(y,m,0).getDate(),ds[0].endsWith('-01')]);
        days.forEach(c=>{const w=(new Date(c.dataset.date+'T12:00:00').getDay()+6)%7;if(Math.abs(c.getBoundingClientRect().left-hs[w])>2)out.bad.push(c.dataset.date)})});return out}""")
    check(layout["pads"] == 0 and not layout["bad"] and all(c[0] == c[1] and c[2] for c in layout["counts"]), "each month shows only its own days, each under the right weekday: " + str(layout["counts"]))
    edges = pg.evaluate("""()=>{const r=s=>document.querySelector(s).getBoundingClientRect(),g=[...document.querySelectorAll('.mhead')],a=r('.top'),b=r('.summary');
      const L=Math.min(...g.map(x=>x.getBoundingClientRect().left)),R=Math.max(...g.map(x=>x.getBoundingClientRect().right));
      return {top:[a.left,a.right],summary:[b.left,b.right],grid:[L,R],legend:!!document.getElementById('legend'),fits:document.documentElement.scrollHeight<=innerHeight+1}}""")
    same = lambda x, y: abs(x[0] - y[0]) <= 1.5 and abs(x[1] - y[1]) <= 1.5
    check(not edges["legend"] and same(edges["top"], edges["summary"]) and same(edges["summary"], edges["grid"]), "no legend; header, summary and calendar share the same left and right edges: " + str(edges))
    check(edges["fits"], "the calendar fits the window without scrolling at 1440 x 860")
    hdr = lambda: pg.evaluate("""()=>{const r=s=>document.querySelector(s).getBoundingClientRect(),t=r('.top'),p=document.getElementById('pager'),c=r('.controls'),tl=document.getElementById('todayline'),tr=document.querySelector('.titlerow');
      return {apart:p.hidden||(r('.brand').right<=p.getBoundingClientRect().left&&p.getBoundingClientRect().right<=c.left),tabsRight:Math.abs(c.right-t.right)<1.5,pagerShown:!p.hidden,
        textFits:tl.scrollWidth<=tl.clientWidth&&(!tr||tr.scrollWidth<=tr.clientWidth)}}""")
    h = hdr()
    check(h["apart"] and h["tabsRight"] and h["textFits"] and h["pagerShown"], "header: title, month controls and tabs sit apart, nothing cut off: " + str(h))

    pg.click("#tab-settings"); pg.set_input_files("#restoreFile", BACKUP); pg.wait_for_selector("#doRestore")
    found = squash(pg.inner_text("#restoreMsg")); pg.click("#doRestore")
    pg.wait_for_function("document.getElementById('restoreMsg').innerText.includes('Restored')", timeout=10000)
    check("Found 2 items, 3 gym days and 2 runs" in found, "backup file read: " + found[:60])
    pg.click("#tab-calendar"); pg.wait_for_timeout(500)
    check(re.search(r"GYM \d+ this month 3 last 7 days 3 last 30 days", train()) and re.search(r"RUN \d+ this month 2 last 7 days 2 last 30 days", train()), "imported ticks counted: " + train()[:150])
    check("Sample test" in nexttitles() and "Physics" in nextlabels() and "7 days" in pg.inner_text("#nextup"), "imported assessment in Next up by subject, 7 days away: " + str(nextlabels()))

    pg.click('.day.today .lane[data-act="run"]'); pg.wait_for_timeout(300)
    check(pressed("run") == "true" and "RUN" in train() and re.search(r"RUN \d+ this month 3 last 7 days", train()), "one click ticks a run today")
    pg.click("#addBtn"); pg.fill("#f-date", day(10)); pg.select_option("#f-subject", "Chemistry"); pg.fill("#f-name", "Module test"); pg.click("#f-save"); pg.wait_for_timeout(400)
    check("Module test" in nexttitles() and "Chemistry" in nextlabels(), "new assessment added through the form: " + str(nextlabels()))

    # event colours: a picked colour sticks to that event; the Events setting recolours the rest
    rowc = lambda name: (pg.evaluate("n=>{const r=[...document.querySelectorAll('#view-items tbody tr')].find(t=>t.innerText.includes(n));return r?getComputedStyle(r.querySelector('.subj')).getPropertyValue('--c').trim().toLowerCase():null}", name) or "")
    pg.click("#addBtn"); pg.fill("#f-date", day(3)); pg.select_option("#f-type", "Event")
    check(pg.is_visible("#f-colorRow"), "choosing Event shows the colour picker")
    pg.fill("#f-name", "Sample formal"); pg.click('#f-swatches [data-sw="#8e3b8e"]')
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, "event-form.png"))
    pg.click("#f-save"); pg.wait_for_timeout(400)
    pg.click("#tab-items"); pg.wait_for_timeout(200)
    check(rowc("Sample formal") == "#8e3b8e" and rowc("Sample event") == "#2d7a73", "event keeps its picked colour; other events use the default")
    pg.click("#tab-settings"); pg.evaluate("()=>{const i=document.getElementById('col-event');i.value='#55657a';i.dispatchEvent(new Event('change',{bubbles:true}))}"); pg.wait_for_timeout(200)
    pg.click("#tab-items"); pg.wait_for_timeout(200)
    check(rowc("Sample event") == "#55657a" and rowc("Sample formal") == "#8e3b8e", "changing the Events colour recolours only default-coloured events")
    pg.click("#tab-calendar"); pg.wait_for_timeout(300)

    # day tiles: the subject only, filling the square; two on one day get half each; events stay thin bars
    pg.click("#addBtn"); pg.fill("#f-date", day(7)); pg.select_option("#f-subject", "Mathematics Advanced"); pg.fill("#f-name", "Paper 1"); pg.click("#f-save"); pg.wait_for_timeout(400)
    pg.click('#monthsSeg [data-m="2"]'); pg.wait_for_timeout(300)  # the two-month view, as used day to day
    one, two, ev = day_tiles(day(10)), None, None
    pg.evaluate("document.getElementById('todayBtn').click()"); pg.wait_for_timeout(200); two = day_tiles(day(7))
    pg.evaluate("document.getElementById('todayBtn').click()"); pg.wait_for_timeout(200); ev = day_tiles(day(3))
    pg.evaluate("document.getElementById('todayBtn').click()"); pg.wait_for_timeout(250)
    check(one and [t["text"] for t in one["tiles"]] == ["Chemistry"] and one["tiles"][0]["upper"] == "uppercase" and one["tiles"][0]["h"] >= one["cell"] * .5, "one assessment: a tile saying just its subject, filling the square: " + str(one))
    check(two and [t["text"] for t in two["tiles"]] == ["Maths Advanced", "Physics"] and abs(two["tiles"][0]["h"] - two["tiles"][1]["h"]) <= 1 and sum(t["h"] for t in two["tiles"]) >= two["cell"] * .5, "two on one day: half the square each: " + str(two))
    check(ev and not ev["tiles"] and ev["bars"] == ["Sample formal"], "an event shows as a named bar, not a tile: " + str(ev))
    check(all(t["fits"] for x in (one, two) if x for t in x["tiles"]), "tile names fit without being cut")
    if SHOTS: show_day(day(7)); pg.screenshot(path=os.path.join(SHOTS, "tiles.png")); pg.evaluate("document.getElementById('todayBtn').click()"); pg.wait_for_timeout(200)
    pg.click('#monthsSeg [data-m="3"]'); pg.wait_for_timeout(300)

    # term weeks: point the first term at dates where today falls in week 3
    mon = today - dt.timedelta(days=today.weekday())
    tstart, tend = (mon - dt.timedelta(days=14)).isoformat(), (mon + dt.timedelta(days=48)).isoformat()
    pg.click("#tab-settings"); pg.wait_for_timeout(150)
    h = hdr(); check(h["tabsRight"] and not h["pagerShown"], "on other tabs the month controls hide and the tabs stay on the right: " + str(h))
    pg.evaluate("([a,b])=>{for(const [id,v] of [['term-name-0','Test term'],['term-start-0',a],['term-end-0',b]]){const i=document.getElementById(id);i.value=v;i.dispatchEvent(new Event('change',{bubbles:true}))}}", [tstart, tend])
    pg.click("#tab-calendar"); pg.wait_for_timeout(300)
    wn = pg.evaluate("()=>{let p=document.querySelector('.day.today');while(p&&!p.classList.contains('wn'))p=p.previousElementSibling;return p?[p.innerText.trim(),p.className]:null}")
    check(bool(wn) and wn[0] == "W3" and "now" in wn[1], "term week shows in the margin beside today's week: " + str(wn))
    check("Test term, week 3" in pg.inner_text("#todayline"), "today's line shows the term week")
    if SHOTS: pg.screenshot(path=os.path.join(SHOTS, "calendar.png"))
    check(squash(pg.inner_text("#sync")) in ("Syncing…", "Synced"), "sync pill online: " + squash(pg.inner_text("#sync")))

    pg.evaluate("navigator.serviceWorker.ready.then(() => true)"); pg.reload(); pg.wait_for_timeout(1500)
    check(pg.evaluate("!!navigator.serviceWorker.controller"), "service worker installed and in control")

    ctx.set_offline(True); pg.reload(); pg.wait_for_timeout(2500)
    check(pg.is_hidden("#gate") and pg.get_attribute(".day.today", "data-date") == day(0), "OFFLINE: app opens and stays signed in")
    check(re.search(r"RUN \d+ this month 3 last 7 days", train()) and "Module test" in nexttitles(), "OFFLINE: all data present")
    check(squash(pg.inner_text("#sync")).startswith("Offline"), "OFFLINE: pill says " + squash(pg.inner_text("#sync")))
    pg.click("#tab-items"); pg.wait_for_timeout(200)
    check(rowc("Sample formal") == "#8e3b8e", "OFFLINE: event colour kept")
    pg.click("#tab-calendar"); pg.wait_for_timeout(300)
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

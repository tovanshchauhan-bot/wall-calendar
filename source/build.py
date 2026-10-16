#!/usr/bin/env python3
"""Build the Wall Calendar offline web app (PWA) from the published calendar page.

Usage: python3 build.py <config.js source> <empty output dir>   (build.sh does this for you)
"""
import hashlib, json, os, re, shutil, subprocess, sys
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_PAGE = os.path.join(ROOT, "calendar.html")  # the calendar UI (same file as the claude.ai version)
cfg_src, OUT = sys.argv[1], sys.argv[2]
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT + "/fonts")

page = open(SRC_PAGE).read()
css = page.split('<style id="css">', 1)[1].split("</style>", 1)[0]
markup = page.split("</style>", 1)[1].split("<script>", 1)[0]
script = page.split("<script>", 1)[1].split("</script>", 1)[0]

def rep(s, a, b, n=1):
    assert s.count(a) == n, ("count", s.count(a), a[:80]); return s.replace(a, b)
def rex(s, pat, b):
    m = list(re.finditer(pat, s, re.S)); assert len(m) == 1, ("regex", len(m), pat[:60])
    return s[:m[0].start()] + b + s[m[0].end():]

# ---------------- fonts (self-hosted so the app looks right offline) ----------------
FS = ROOT + "/node_modules/@fontsource"
fonts = {
  "archivo-wdth.woff2": ROOT + "/node_modules/@fontsource-variable/archivo/files/archivo-latin-wdth-normal.woff2",
  "plex-400.woff2": FS + "/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2",
  "plex-500.woff2": FS + "/ibm-plex-sans/files/ibm-plex-sans-latin-500-normal.woff2",
  "plex-600.woff2": FS + "/ibm-plex-sans/files/ibm-plex-sans-latin-600-normal.woff2",
  "plex-700.woff2": FS + "/ibm-plex-sans/files/ibm-plex-sans-latin-700-normal.woff2",
  "plex-cond-400.woff2": FS + "/ibm-plex-sans-condensed/files/ibm-plex-sans-condensed-latin-400-normal.woff2",
  "plex-cond-500.woff2": FS + "/ibm-plex-sans-condensed/files/ibm-plex-sans-condensed-latin-500-normal.woff2",
  "plex-cond-600.woff2": FS + "/ibm-plex-sans-condensed/files/ibm-plex-sans-condensed-latin-600-normal.woff2",
}
for name, src in fonts.items(): shutil.copy(src, f"{OUT}/fonts/{name}")
face = lambda fam, f, w, extra="": f'@font-face{{font-family:"{fam}";font-style:normal;font-display:swap;font-weight:{w};{extra}src:url(fonts/{f}) format("woff2")}}'
FONT_CSS = "\n".join([
  face("Archivo", "archivo-wdth.woff2", "100 900", "font-stretch:62% 125%;"),
  *[face("IBM Plex Sans", f"plex-{w}.woff2", w) for w in (400, 500, 600, 700)],
  *[face("IBM Plex Sans Condensed", f"plex-cond-{w}.woff2", w) for w in (400, 500, 600)],
])

# ---------------- CSS ----------------
css = rep(css, ":root{\n  --paper:#F7F7F4;", ":root{\n  color-scheme:light;\n  --paper:#F7F7F4;")
css = rep(css, "  .hint{display:none}\n", "  .hint,.sync,.gate{display:none!important}\n")
css = FONT_CSS + "\n" + css + """
/* app-only: sign-in gate and sync status */
.titlerow{display:flex;align-items:center;gap:12px;min-width:0}
.sync{display:inline-flex;align-items:center;gap:7px;padding:3px 10px;border-radius:999px;background:var(--chip);color:var(--ink-2);font-size:12px;line-height:1.2;font-weight:500;white-space:nowrap}
.sync i{width:7px;height:7px;border-radius:50%;background:var(--gym)}
.sync.pending i{background:var(--ink-3)}
.sync.off i{background:var(--run)}
.gate{position:fixed;inset:0;z-index:70;display:grid;place-items:center;padding-inline:16px;padding-block:24px;background:var(--paper)}
.gatecard{width:min(460px,100%);display:flex;flex-direction:column;align-items:flex-start;gap:16px}
.gatecard h1{margin:0;font-family:var(--font-display);font-stretch:118%;font-weight:800;font-size:28px;line-height:1.08;text-wrap:balance}
.gatecard p{margin:0;color:var(--ink-2);max-width:46ch}
.btn.big{padding:10px 18px;font-size:14px;border-radius:10px}
.week{display:grid;grid-template-columns:repeat(7,34px);gap:4px}
.week span{position:relative;height:34px;border:1px solid var(--rule);border-radius:4px;background:var(--panel);overflow:hidden}
.week span.p{background-color:var(--past);background-image:linear-gradient(to top right,transparent calc(50% - .7px),var(--cross) calc(50% - .7px),var(--cross) calc(50% + .7px),transparent calc(50% + .7px)),linear-gradient(to bottom right,transparent calc(50% - .7px),var(--cross) calc(50% - .7px),var(--cross) calc(50% + .7px),transparent calc(50% + .7px))}
.week span.t{box-shadow:inset 0 9px 0 var(--today),inset 0 0 0 1.5px var(--today);border-color:var(--today)}
.week b{position:absolute;bottom:3px;height:4px;width:calc(50% - 5px);border-radius:2px;background:var(--a)}
.week b.g{left:3px;--a:var(--gym)} .week b.r{right:3px;--a:var(--run)}
"""

# ---------------- markup ----------------
markup = rep(markup, '      <div class="wordmark">Wall Calendar</div>\n',
             '      <div class="titlerow"><div class="wordmark">Wall Calendar</div><span class="sync" id="sync" role="status" hidden></span></div>\n')
GATE = """<div class="gate" id="gate" hidden>
  <div class="gatecard">
    <div class="week" aria-hidden="true"><span class="p"><b class="g"></b></span><span class="p"><b class="r"></b></span><span class="p"><b class="g"></b><b class="r"></b></span><span class="p"></span><span class="p"><b class="g"></b></span><span class="t"></span><span></span></div>
    <div class="wordmark">Wall Calendar</div>
    <h1>Sign in once, then it works offline</h1>
    <p>Your calendar is saved to your own Google account. After this first sign-in it opens and saves without internet, and syncs whenever you reconnect.</p>
    <button class="btn primary big" id="gateBtn" type="button">Continue with Google</button>
    <p class="muted" id="gateOffline" hidden>You're offline. Connect to the internet once to sign in.</p>
    <p class="err" id="gateMsg" hidden></p>
  </div>
</div>
"""
markup = rep(markup, '<div class="overlay" id="overlay" hidden>', GATE + '<div class="overlay" id="overlay" hidden>')

# ---------------- script (UI) ----------------
s = script
s = rep(s, "const S={items:new Map(),", "const S={user:null,items:new Map(),")
s = rex(s, r"/\* ---------- connect to storage ---------- \*/.*?(?=/\* ---------- derived ---------- \*/)", r'''/* ---------- connect to storage ---------- */
function connect(db){
  S.db=db;S.readOnly=false;setStatus("");
  const fail=e=>{const c=e&&e.code||"";if(c==="permission-denied"||c==="unauthenticated")setStatus("Firebase won't share this calendar with this Google account. Check the email address in your Firestore rules, or sign out in Settings and use the right account.",true);else setStatus("Couldn't load your calendar data ("+(c||"error")+"). Reload to try again.",true)};
  const u=[];
  u.push(db.collection("items").onSnapshot(snap=>{S.items=new Map(snap.docs.map(d=>[d.id,d.data()]));S.loaded.items=true;render()},fail));
  for(const kind of ["gym","run"])u.push(db.collection(kind).onSnapshot(snap=>{const next=new Set(snap.docs.map(d=>d.id));for(const k of S.busy)if(k.startsWith(kind+"/")){const d=k.slice(kind.length+1);S[kind].has(d)?next.add(d):next.delete(d)}S[kind]=next;S.loaded[kind]=true;render()},fail));
  u.push(db.doc("config/settings").onSnapshot(snap=>{if(snap.exists){S.settings=mergeSettings(snap.data());applyColors()}render()},fail));
  return ()=>{u.forEach(f=>{try{f()}catch(e){}});S.db=null;S.items=new Map();S.gym=new Set();S.run=new Set();S.loaded={items:false,gym:false,run:false};S.settings=clone(DEFAULTS);applyColors()};
}
''')
s = rex(s, r"function writeError\(e\)\{.*?else toast\(\"Couldn't save just now\. Try again in a moment\.\"\);\}",
        '''function writeError(e){const c=e&&e.code||"";
  if(c==="permission-denied"||c==="unauthenticated")setStatus("Firebase refused a change because this Google account isn't the one allowed in your Firestore rules. Sign out in Settings and use the right account.",true);
  else if(c==="resource-exhausted")setStatus("Firebase's free daily limit was reached. Your changes stay on this laptop and sync once it resets.",true);
  else toast("Couldn't save that change ("+(c||"error")+").");}''')
s = rex(s, r"function canWrite\(\)\{.*?return true\}", 'function canWrite(){if(!S.db){toast("Sign in first.");return false}return true}')
s = rex(s, r'function printable\(\)\{.*?</html>"\}', "")
s = rex(s, r'  else if\(id==="dlPrint"\)\{.*?\+"\.html",html\)\}\}\);',
        '''  else if(id==="printBtn"){setView("calendar");setTimeout(()=>window.print(),250)}
  else if(id==="signOutBtn"){const b=e.target;if(b.dataset.armed!=="1"){b.dataset.armed="1";b.textContent="Click again to sign out";return}platform&&platform.signOut()}});''')
s = rep(s, "<p>Download a backup now and then. The printable page opens in your browser, where Cmd+P (or Ctrl+P) prints it landscape.</p>",
        "<p>Everything syncs to your Google account. A backup file is a second copy you keep yourself.</p>")
s = rep(s, '<button class="btn" type="button" id="dlPrint">Printable page (.html)</button>', '<button class="btn" type="button" id="printBtn">Print calendar</button>')
s = rep(s, "<div class=\"settings\">'+\n  '<div class=\"card\"><h3>Calendar</h3>", "<div class=\"settings\">'+accountCard()+\n  '<div class=\"card\"><h3>Calendar</h3>")
s = rep(s, "/* ---------- render: settings ---------- */", '''/* ---------- render: settings ---------- */
function accountCard(){if(!S.user)return "";return '<div class="card"><h3>Account</h3><p>Signed in as <b>'+esc(S.user.email||"your Google account")+'</b>. Changes save on this laptop straight away and sync to Firebase whenever you\\'re online.</p><div class="row"><button class="btn" type="button" id="signOutBtn">Sign out</button></div></div>'}''')
s = rep(s, '"<li><b>Later months.</b>', '"<li><b>Offline.</b> No internet needed. Changes save on this laptop and sync to your Google account when you reconnect. The pill at the top says Synced, Syncing or Offline.</li>"+\n  "<li><b>Later months.</b>')
s = rep(s, 'applyColors();if(S.view==="settings")renderSettings();render();connect();', r'''applyColors();if(S.view==="settings")renderSettings();render();
S.dl=downloads;
const gate=$("gate");
function showGate(msg){gate.hidden=false;$("app").setAttribute("aria-hidden","true");const m=$("gateMsg");m.textContent=msg||"";m.hidden=!msg;$("gateBtn").disabled=!platform||!navigator.onLine;$("gateOffline").hidden=navigator.onLine}
function hideGate(){gate.hidden=true;$("app").removeAttribute("aria-hidden")}
function renderSync(){const el=$("sync");if(!platform||!S.user){el.hidden=true;return}const pending=platform.syncState().pending,on=navigator.onLine;
  let cls="sync",txt="Synced",tip="Everything is saved to your Google account.";
  if(!on){cls+=" off";txt=pending?"Offline · will sync":"Offline";tip=pending?"Changes are saved on this laptop and upload when you're back online.":"Working offline. Changes save on this laptop."}
  else if(pending){cls+=" pending";txt="Syncing…";tip="Uploading your latest changes."}
  el.className=cls;el.innerHTML="<i></i>"+txt;el.title=tip;el.hidden=false}
if(!platform)showGate("This app isn't connected to a Firebase project yet.");
else{
  platform.setWriteErrorHandler(writeError);
  platform.onSync(renderSync);
  window.addEventListener("online",()=>{renderSync();if(!gate.hidden)showGate()});
  window.addEventListener("offline",()=>{renderSync();if(!gate.hidden)showGate()});
  let stop=null;
  platform.onUser(user=>{
    if(stop){stop();stop=null}
    S.user=user||null;
    if(!user){render();showGate();renderSync();return}
    hideGate();stop=connect(platform.store(user.uid));platform.checkPending();renderSync();if(S.view==="settings")renderSettings()});
  $("gateBtn").addEventListener("click",async()=>{const b=$("gateBtn");b.disabled=true;$("gateMsg").hidden=true;
    try{await platform.signIn()}
    catch(e){const c=e&&e.code||"";const known={"auth/popup-blocked":"Chrome blocked the sign-in window. Allow pop-ups for this site, then try again.","auth/unauthorized-domain":"This web address isn't approved in Firebase yet. Add it under Authentication → Settings → Authorized domains.","auth/network-request-failed":"No internet connection. Connect once to sign in.","auth/operation-not-allowed":"Google sign-in isn't switched on in Firebase yet (Authentication → Sign-in method → Google)."};
      if(c!=="auth/popup-closed-by-user"&&c!=="auth/cancelled-popup-request")showGate(known[c]||"Sign-in didn't work ("+(c||"unknown error")+"). Try again.")}
    finally{b.disabled=!navigator.onLine}});
  if(platform.testSignIn)window.__wcTestSignIn=platform.testSignIn;
}''')

PLATFORM = r'''import {initializeApp} from "firebase/app";
import {getAuth,GoogleAuthProvider,signInWithPopup,signOut,onAuthStateChanged,connectAuthEmulator,signInWithCredential} from "firebase/auth";
import {initializeFirestore,persistentLocalCache,persistentMultipleTabManager,connectFirestoreEmulator,collection,doc,setDoc,deleteDoc,onSnapshot,waitForPendingWrites} from "firebase/firestore";

/* Firebase: Google sign-in + Firestore with an on-device cache, so reads and writes work offline
   and queued writes upload automatically on reconnect. */
const CFG=window.WC_FIREBASE_CONFIG||null;
const platform=(()=>{
  if(!CFG||!CFG.apiKey||!CFG.projectId)return null;
  const {emulator,...fbcfg}=CFG;
  const app=initializeApp(fbcfg);
  const auth=getAuth(app);
  const fs=initializeFirestore(app,{localCache:persistentLocalCache({tabManager:persistentMultipleTabManager()})});
  if(emulator){if(emulator.auth)connectAuthEmulator(auth,emulator.auth,{disableWarnings:true});if(emulator.firestore)connectFirestoreEmulator(fs,emulator.firestore[0],emulator.firestore[1])}
  let pending=false,seq=0,onWriteError=()=>{};const subs=new Set();
  const notify=()=>subs.forEach(f=>{try{f()}catch(e){}});
  const track=()=>{pending=true;const my=++seq;notify();waitForPendingWrites(fs).then(()=>{if(my===seq){pending=false;notify()}}).catch(()=>{})};
  function store(uid){
    const base="users/"+uid;
    const wrap=s=>({id:s.id,exists:s.exists(),data:()=>s.data(),metadata:s.metadata});
    const write=p=>{track();p.catch(e=>onWriteError(e));return Promise.resolve()};
    const docRef=path=>{const r=doc(fs,base+"/"+path);return {id:r.id,path,set:d=>write(setDoc(r,d)),delete:()=>write(deleteDoc(r)),onSnapshot:(next,err)=>onSnapshot(r,s=>next(wrap(s)),e=>err&&err(e))}};
    const collRef=path=>{const c=collection(fs,base+"/"+path);return {path,doc:id=>docRef(path+"/"+(id||doc(c).id)),onSnapshot:(next,err)=>onSnapshot(c,s=>next({docs:s.docs.map(wrap),size:s.size,empty:s.empty,metadata:s.metadata}),e=>err&&err(e))}};
    return {doc:docRef,collection:collRef};
  }
  return {
    store,
    onUser:cb=>onAuthStateChanged(auth,cb),
    signIn:()=>signInWithPopup(auth,new GoogleAuthProvider()),
    signOut:()=>signOut(auth),
    syncState:()=>({pending}),
    onSync:f=>{subs.add(f);return ()=>subs.delete(f)},
    setWriteErrorHandler:f=>{onWriteError=f},
    checkPending:track,
    testSignIn:emulator?()=>signInWithCredential(auth,GoogleAuthProvider.credential(JSON.stringify({sub:"test-user",email:"test@example.com",email_verified:true}))):null
  };
})();

/* Files are saved with an ordinary browser download. */
const downloads={save:async({filename,data})=>{const ext=(filename.split(".").pop()||"").toLowerCase();const type={json:"application/json",csv:"text/csv"}[ext]||"application/octet-stream";const url=URL.createObjectURL(new Blob([data],{type}));const a=document.createElement("a");a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),4000);return {status:"saved"}}};

if("serviceWorker" in navigator&&location.protocol.startsWith("http"))window.addEventListener("load",()=>{navigator.serviceWorker.register("./sw.js").catch(()=>{})});
'''
os.makedirs(ROOT + "/.build", exist_ok=True)
open(ROOT + "/.build/main.js", "w").write(PLATFORM + "\n" + s)
subprocess.run([ROOT + "/node_modules/.bin/esbuild", ROOT + "/.build/main.js", "--bundle", "--format=esm", "--minify",
                "--target=chrome100,safari15,firefox100", "--legal-comments=none", "--outfile=" + OUT + "/app.js"], check=True)

# ---------------- icons ----------------
INK, PAPER, BAND, CROSS, GYM, RUN = "#15181C", "#F7F7F4", "#4A5058", "#C9CCC5", "#2E7D4F", "#D0A21C"
def draw_icon(size, maskable=False, rounded=True):
    S = 1024; im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    if maskable or not rounded: d.rectangle([0, 0, S, S], fill=INK)
    else: d.rounded_rectangle([0, 0, S - 1, S - 1], radius=224, fill=INK)
    k = 0.74 if maskable else 1.0
    t = lambda v: S / 2 + (v - S / 2) * k
    box = lambda a, b, c, e: [t(a), t(b), t(c), t(e)]
    d.rounded_rectangle(box(212, 236, 812, 836), radius=72 * k, fill=PAPER)
    d.rounded_rectangle(box(212, 236, 812, 376), radius=72 * k, fill=BAND)
    d.rectangle(box(212, 316, 812, 376), fill=BAND)
    for cx in (372, 652): d.rounded_rectangle(box(cx - 26, 180, cx + 26, 296), radius=26 * k, fill=PAPER)
    w = int(26 * k)
    d.line([t(300), t(440), t(724), t(690)], fill=CROSS, width=w); d.line([t(300), t(690), t(724), t(440)], fill=CROSS, width=w)
    d.rounded_rectangle(box(262, 728, 502, 784), radius=20 * k, fill=GYM)
    d.rounded_rectangle(box(522, 728, 762, 784), radius=20 * k, fill=RUN)
    return im.resize((size, size), Image.LANCZOS)
draw_icon(192).save(OUT + "/icon-192.png"); draw_icon(512).save(OUT + "/icon-512.png")
draw_icon(512, maskable=True).save(OUT + "/icon-maskable-512.png")
draw_icon(180, rounded=False).convert("RGB").save(OUT + "/apple-touch-icon.png")
draw_icon(48).save(OUT + "/favicon.png")

# ---------------- config, manifest, html, sw ----------------
shutil.copy(cfg_src, OUT + "/config.js")
h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:10]
app_v, cfg_v = h(OUT + "/app.js"), h(OUT + "/config.js")
json.dump({"id": "./", "name": "Wall Calendar", "short_name": "Calendar",
           "description": "Three-month wall calendar with gym and run tracking and assessment countdowns.",
           "start_url": "./", "scope": "./", "display": "standalone", "background_color": PAPER, "theme_color": INK,
           "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
                     {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
                     {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]},
          open(OUT + "/manifest.webmanifest", "w"), indent=1)
html = f'''<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Wall Calendar</title>
<meta name="description" content="Three-month wall calendar with gym and run tracking and assessment countdowns.">
<meta name="theme-color" content="{INK}">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="favicon.png" type="image/png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="preload" href="fonts/archivo-wdth.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="fonts/plex-400.woff2" as="font" type="font/woff2" crossorigin>
<style id="css">
{css}
</style>
</head>
<body>
{markup.strip()}
<script src="config.js?v={cfg_v}"></script>
<script type="module" src="app.js?v={app_v}"></script>
</body>
</html>
'''
open(OUT + "/index.html", "w").write(html)
shell = ["./", "./index.html", f"./app.js?v={app_v}", f"./config.js?v={cfg_v}", "./manifest.webmanifest", "./favicon.png",
         "./icon-192.png", "./icon-512.png", "./icon-maskable-512.png", "./apple-touch-icon.png"] + [f"./fonts/{f}" for f in fonts]
ver = hashlib.sha256((html + app_v + cfg_v).encode()).hexdigest()[:10]
SW = '''/* Wall Calendar service worker: keeps the app itself on this device so it opens without internet.
   Your data is handled separately by Firebase's own offline cache. */
const VERSION="wc-%s";
const SHELL=%s;
self.addEventListener("install",e=>{e.waitUntil(caches.open(VERSION).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener("activate",e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.startsWith("wc-")&&k!==VERSION).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
function page(req){
  return new Promise(resolve=>{
    let done=false;const finish=r=>{if(!done&&r){done=true;resolve(r)}};
    const fallback=()=>caches.match("./").then(m=>m||caches.match("./index.html"));
    const timer=setTimeout(()=>fallback().then(finish),3500);
    fetch(new Request(req.url,{cache:"no-cache",credentials:"same-origin"})).then(res=>{
      clearTimeout(timer);
      if(res.ok){const copy=res.clone();caches.open(VERSION).then(c=>c.put("./",copy))}
      finish(res);
    }).catch(()=>{clearTimeout(timer);fallback().then(m=>finish(m||Response.error()))});
  });
}
self.addEventListener("fetch",e=>{
  const req=e.request;if(req.method!=="GET")return;
  const url=new URL(req.url);if(url.origin!==location.origin)return;
  if(req.mode==="navigate"){e.respondWith(page(req));return}
  e.respondWith(caches.match(req).then(m=>m||fetch(req)));
});
''' % (ver, json.dumps(shell))
open(OUT + "/sw.js", "w").write(SW)
open(OUT + "/.nojekyll", "w").write("")
open(OUT + "/README.md", "w").write("""# Wall Calendar

A three-month wall calendar for school assessments, gym days and runs.
Installable web app: it opens and saves without internet, and syncs to Firebase when online.

Data lives in this project's Firestore database, locked by its security rules to one Google account.
The Firebase settings in `config.js` identify the project; they are not a password.

The files here are built output. To change the app, edit `source/` and run `source/build.sh` (see `source/README.md`).
""")
print("built", OUT, "app.js", os.path.getsize(OUT + "/app.js"), "bytes; version", ver)

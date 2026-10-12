/* Wall Calendar service worker: keeps the app itself on this device so it opens without internet.
   Your data is handled separately by Firebase's own offline cache. */
const VERSION="wc-0c1362a82b";
const SHELL=["./", "./index.html", "./app.js?v=b9f0315ca9", "./config.js?v=3e4a4910ec", "./manifest.webmanifest", "./favicon.png", "./icon-192.png", "./icon-512.png", "./icon-maskable-512.png", "./apple-touch-icon.png", "./fonts/archivo-wdth.woff2", "./fonts/plex-400.woff2", "./fonts/plex-500.woff2", "./fonts/plex-600.woff2", "./fonts/plex-700.woff2", "./fonts/plex-cond-400.woff2", "./fonts/plex-cond-500.woff2", "./fonts/plex-cond-600.woff2"];
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

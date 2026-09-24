// CalorPulse alert server. Node 18+, no dependencies.
// Checks every 10 min and sends a push ~15 min before WBGT crosses each user's threshold.
const http = require('http'), fs = require('fs');
const F = 'users.json'; let U = {};
try { U = JSON.parse(fs.readFileSync(F)); } catch {}
const save = () => { try { fs.writeFileSync(F, JSON.stringify(U)); } catch {} };
const wbgt = (t, rh, s, w) => 0.567 * t + 0.393 * (rh / 100 * 6.105 * Math.exp(17.27 * t / (237.7 + t))) + 3.94 + s / 1000 * 1.5 - Math.min(w / 3.6, 4) * 0.3;
const dist = (a, b, c, d) => { const r = x => x * Math.PI / 180, h = Math.sin(r(c - a) / 2) ** 2 + Math.cos(r(a)) * Math.cos(r(c)) * Math.sin(r(d - b) / 2) ** 2; return Math.round(12742e3 * Math.asin(Math.sqrt(h))); };

async function nearestShade(lat, lon) {
  try {
    const q = `[out:json][timeout:15];(way["leisure"="park"](around:900,${lat},${lon});node["amenity"="shelter"](around:900,${lat},${lon}););out center 20;`;
    const o = await (await fetch('https://overpass-api.de/api/interpreter', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'data=' + encodeURIComponent(q) })).json();
    const l = o.elements.map(e => ({ name: e.tags?.name || 'Shaded spot', d: dist(lat, lon, e.lat ?? e.center.lat, e.lon ?? e.center.lon) })).sort((a, b) => a.d - b.d);
    return l[0] ? ` Nearest shade: ${l[0].name}, ${l[0].d} m.` : '';
  } catch { return ''; }
}

async function check() {
  for (const [tok, u] of Object.entries(U)) {
    try {
      const age = +u.age || 0, thr = 32 - (age >= 60 || (age && age <= 12) ? 2 : 0) - (u.cond?.length ? 1.5 : 0);
      const r = await (await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${u.lat}&longitude=${u.lon}&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation&forecast_days=2&timezone=auto`)).json();
      const off = r.utc_offset_seconds * 1000, h = r.hourly;
      for (let i = 0; i < h.time.length; i++) {
        const w = wbgt(h.temperature_2m[i], h.relative_humidity_2m[i], h.shortwave_radiation[i], h.wind_speed_10m[i]);
        const mins = (new Date(h.time[i] + ':00Z').getTime() - off - Date.now()) / 60000;
        if (w >= thr && mins > -30 && mins <= 15 && u.last !== h.time[i]) {
          const shade = u.shade === false ? '' : await nearestShade(u.lat, u.lon);
          await fetch('https://exp.host/--/api/v2/push/send', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ to: tok, title: `${w >= 32 ? 'Extreme' : 'High'} heat in 15 min`, body: `WBGT ~${w.toFixed(1)}°C. Move indoors, drink water.${shade}`, sound: 'default', priority: 'high', channelId: 'default' }) });
          u.last = h.time[i]; save(); console.log('alert sent', tok.slice(-8), h.time[i]); break;
        }
      }
    } catch (e) { console.log('check error', e.message); }
  }
}

http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/register') {
    let b = ''; req.on('data', c => b += c);
    req.on('end', () => { try { const u = JSON.parse(b); U[u.token] = { ...U[u.token], ...u }; save(); res.end('ok'); } catch { res.statusCode = 400; res.end('bad request'); } });
    return;
  }
  res.end('CalorPulse server running. Users: ' + Object.keys(U).length);
}).listen(process.env.PORT || 3000);
setInterval(check, 10 * 60 * 1000); setTimeout(check, 5000);

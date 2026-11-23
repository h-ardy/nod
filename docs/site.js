// ---------- topographic contours: gradient noise, then marching squares. Used by the page backdrop and the 3D desk.
window.drawContours = function (ctx, w, h, o = {}) {
  const step = o.step || 6, levels = o.levels || 26, sc = o.scale || 1 / 520, seed = o.seed || 7;
  const P = new Uint8Array(512); { const p = [...Array(256).keys()]; let x = seed * 9301 + 49297;
    for (let i = 255; i > 0; i--) { x = (x * 9301 + 49297) % 233280; const j = Math.floor((x / 233280) * (i + 1)); [p[i], p[j]] = [p[j], p[i]]; }
    for (let i = 0; i < 512; i++) P[i] = p[i & 255]; }
  const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10), lerp = (a, b, t) => a + (b - a) * t;
  const grad = (hh, x, y) => { const g = hh & 7, u = g < 4 ? x : y, v = g < 4 ? y : x; return ((g & 1) ? -u : u) + ((g & 2) ? -2 * v : 2 * v); };
  function noise(x, y) {
    const X = Math.floor(x) & 255, Y = Math.floor(y) & 255; x -= Math.floor(x); y -= Math.floor(y);
    const u = fade(x), v = fade(y), a = P[X] + Y, b = P[X + 1] + Y;
    return lerp(lerp(grad(P[a], x, y), grad(P[b], x - 1, y), u), lerp(grad(P[a + 1], x, y - 1), grad(P[b + 1], x - 1, y - 1), u), v) * 0.5;
  }
  const field = (x, y) => { x *= sc; y *= sc; return noise(x, y) + 0.5 * noise(x * 2.1 + 5.2, y * 2.1 + 1.3) + 0.22 * noise(x * 4.3 + 9.7, y * 4.3 + 3.1); };
  const nx = Math.ceil(w / step) + 1, ny = Math.ceil(h / step) + 1, v = new Float32Array(nx * ny);
  let lo = 1e9, hi = -1e9;
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) { const f = field(i * step, j * step); v[j * nx + i] = f; if (f < lo) lo = f; if (f > hi) hi = f; }
  for (let k = 1; k < levels; k++) {
    const L = lo + ((hi - lo) * k) / levels, major = k % 5 === 0;
    ctx.beginPath();
    for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
      const a = v[j * nx + i], b = v[j * nx + i + 1], c = v[(j + 1) * nx + i + 1], d = v[(j + 1) * nx + i];
      const idx = (a > L ? 8 : 0) | (b > L ? 4 : 0) | (c > L ? 2 : 0) | (d > L ? 1 : 0);
      if (idx === 0 || idx === 15) continue;
      const x = i * step, y = j * step, t = (p, q) => (L - p) / (q - p);
      const T = [x + step * t(a, b), y], R = [x + step, y + step * t(b, c)], B = [x + step * t(d, c), y + step], Lf = [x, y + step * t(a, d)];
      const seg = (p, q) => { ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); };
      switch (idx) {
        case 1: case 14: seg(Lf, B); break; case 2: case 13: seg(B, R); break; case 3: case 12: seg(Lf, R); break;
        case 4: case 11: seg(T, R); break; case 6: case 9: seg(T, B); break; case 7: case 8: seg(Lf, T); break;
        case 5: seg(Lf, T); seg(B, R); break; case 10: seg(T, R); seg(Lf, B); break;
      }
    }
    ctx.strokeStyle = major ? (o.major || 'rgba(237,235,228,.13)') : (o.line || 'rgba(237,235,228,.055)');
    ctx.lineWidth = major ? (o.mw || 1.3) : (o.lw || 1);
    ctx.stroke();
  }
};
// the page backdrop: drawn once, then drifts slowly as you scroll
(() => {
  const el = document.getElementById('topo'), c = document.createElement('canvas');
  c.width = 1800; c.height = 1500;
  const x = c.getContext('2d');
  window.drawContours(x, c.width, c.height, { step: 5, levels: 34, scale: 1 / 600, seed: 11 });
  el.style.backgroundImage = `url(${c.toDataURL('image/png')})`;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let ticking = false;
  const move = () => {
    ticking = false;
    const max = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    el.style.transform = `translate3d(0,${(-scrollY / max) * 35}vh,0)`;
  };
  if (!reduced) addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(move); } }, { passive: true });
})();

// ---------- price table: every number visible, total computed, nothing hard-coded twice
const PARTS = [
  ['Seeed XIAO nRF52840', 'The brain and the Bluetooth radio', 'Seeed Studio', 9.99, '#6C8FB8'],
  ['Waveshare 1.47 in LCD', 'The screen', 'Waveshare', 9.99, '#3F6FD0'],
  ['Kailh Choc red switch', 'The key you press', 'Adafruit, $11.95 for 10', 1.20, '#C8453B'],
  ['LiPo battery, 400 mAh', 'Runs it without a cable', 'Amazon', 7.49, '#C9CBC6'],
  ['4 N52 disc magnets', 'Snap keys together', 'K&J Magnetics, $0.32 each', 1.28, '#8E959B'],
  ['PETG plastic, about 16 g', 'Printed case, lid and keycap', 'About $20 for a 1 kg spool', 0.32, '#5C5F56'],
  ['Foam tape, wire, Kapton tape, 1 screw', 'Holds everything in place', 'Adafruit, Zoro', 0.54, '#B58A2A'],
  ['Shipping the parts to me', 'Split across a batch of 10 keys (estimate)', 'Five stores, about $56 per batch', 5.60, '#77796F'],
];
const PRICE = 46.99;                                                  // the price per key; my cut is whatever is left after parts
const PROFIT = Math.round((PRICE - PARTS.reduce((s, p) => s + p[3], 0)) * 100) / 100;
const $ = (n) => n.toFixed(2);
const partsSum = PARTS.reduce((s, p) => s + p[3], 0), total = partsSum + PROFIT;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
window.NOD_PARTS = PARTS;

// price table (Individuals page). Elsewhere, clicking a part in the 3D model opens its row there.
if (document.getElementById('rows')) {
const rowsEl = document.getElementById('rows'), stackEl = document.getElementById('stack');
rowsEl.innerHTML =
  PARTS.map((p, i) => `<tr data-i="${i}"><td class="name"><i style="background:${p[4]}"></i>${esc(p[0])}<small>${esc(p[1])}</small></td><td>${esc(p[2])}</td><td class="num">$${$(p[3])}</td></tr>`).join('') +
  `<tr class="sub"><td>Parts</td><td></td><td class="num">$${$(partsSum)}</td></tr>` +
  `<tr data-i="${PARTS.length}"><td class="name"><i style="background:var(--amber)"></i>My profit<small>Flat per key. Pays for my build and test time, reprints and dead parts</small></td><td>A flat amount, not a percentage</td><td class="num">$${$(PROFIT)}</td></tr>` +
  `<tr class="total"><td>Price</td><td></td><td class="num">$${$(total)}</td></tr>`;
stackEl.innerHTML = PARTS.map((p, i) => `<div data-i="${i}" style="flex:${p[3]} 0 0;background:${p[4]}" title="${esc(p[0])}: $${$(p[3])}"></div>`).join('') +
  `<div data-i="${PARTS.length}" style="flex:${PROFIT} 0 0;background:var(--amber)" title="My profit: $${$(PROFIT)}"></div>`;
document.getElementById('total').textContent = $(total);
document.querySelectorAll('.profit-word').forEach((el) => { el.textContent = $(PROFIT); });
function hot(i) {
  stackEl.classList.toggle('dim', i != null);
  stackEl.querySelectorAll('div').forEach((d) => d.classList.toggle('hot', d.dataset.i === String(i)));
  rowsEl.querySelectorAll('tr[data-i]').forEach((r) => r.classList.toggle('hot', r.dataset.i === String(i)));
}
for (const el of [rowsEl, stackEl]) {
  el.addEventListener('pointerover', (e) => { const t = e.target.closest('[data-i]'); if (t) hot(t.dataset.i); });
  el.addEventListener('pointerleave', () => hot(null));
}
// the 3D model calls this when you click a part
window.showPriceRow = (i) => {
  const r = rowsEl.querySelector(`tr[data-i="${i}"]`); if (!r) return;
  r.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
  r.classList.remove('flash'); void r.offsetWidth; r.classList.add('flash');
};
  const want = new URLSearchParams(location.search).get('row');
  if (want !== null) setTimeout(() => window.showPriceRow(want), 400);
} else {
  window.showPriceRow = (i) => { location.href = `individuals.html?row=${i}#price`; };
}

// ---------- forms: send to Formspree with fetch, so people stay on the page and see a real answer
(() => {
  const cleanEmail = (v) => v.trim().replace(/^mailto:/i, '').replace(/^<|>$/g, '').trim();
  const hook = (formId, emailId, noteId, sentMsg, before) => {
    const form = document.getElementById(formId);
    if (!form) return;
    const note = document.getElementById(noteId), btn = form.querySelector('button[type="submit"]'), email = document.getElementById(emailId);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      email.value = cleanEmail(email.value);
      if (!/^\S+@\S+\.\S+$/.test(email.value)) { note.textContent = 'That doesn’t look like an email address.'; email.setAttribute('aria-invalid', 'true'); email.focus(); return; }
      email.removeAttribute('aria-invalid');
      if (before) before(form);
      btn.disabled = true; note.textContent = 'Sending…';
      try {
        const res = await fetch(form.action, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } });
        if (res.ok) { form.reset(); note.textContent = sentMsg; return; }
        const data = await res.json().catch(() => ({}));
        note.textContent = (data.errors && data.errors.map((x) => x.message).join(' ')) || 'That didn’t go through. Try again in a minute.';
      } catch (err) {
        note.textContent = 'Couldn’t reach the form service. Check your connection and try again.';
      } finally { btn.disabled = false; }
    });
  };
  hook('signup', 'email', 'note', 'You’re on the list. You’ll get an email when pre-orders open.');
  // Postel: team size can be "12", "about 20" or "10-15". Keep what they typed, it all goes through
  hook('pilot', 'pemail', 'pnote', 'Got it. I’ll email you about the pilot.', (form) => {
    const sz = form.querySelector('#psize'); sz.value = sz.value.trim();
  });
})();

// ---------- sections ease in once
(() => {
  const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: 0.12 });
  document.querySelectorAll('.rise').forEach((el) => io.observe(el));
})();

if (document.getElementById('lanesArt')) {
// ---------- lanes: they slide together once you scroll to them
(() => {
  const art = document.getElementById('lanesArt');
  new IntersectionObserver((es, io) => es.forEach((e) => { if (e.isIntersecting) { setTimeout(() => art.classList.add('snap'), 400); io.disconnect(); } }), { threshold: 0.6 }).observe(art);
})();

}

// ---------- the key's screen and press rules. Same numbers as the firmware (nod_key.cpp).
// One engine draws both the 3D key in the hero and the working key in "Try it".
window.makeNod = function (canvas, hooks = {}) {
  const W = 172, H = 320, S = canvas.width / W, c = canvas.getContext('2d');
  const HIT = 288, TH = 64, THR = 96, GAP = 6, TX = 6, TW = W - 12;
  const HOLD = 1000, DBL = 320, PRESS = 90, APPR = 780, DENY = 450, MAX_SHOWN = 3, FALL = 210;   // FALL in px per second
  const RED = '#F04438';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const k = { tiles: [], parked: [], down: false, downAt: 0, holdUsed: false, lastTapAt: 0, pendingTapAt: 0, hold: 0, hintUntil: 0, earlyUntil: 0, last: 0 };
  let nextId = 1;
  const live = () => k.tiles.filter((t) => t.state === 'live');
  const lowest = () => live()[0] || null;
  const ready = () => { const t = lowest(); return !!t && t.y >= HIT - THR - 12; };
  const emit = (name, ...a) => hooks[name] && hooks[name](...a);

  function submit(req) {
    const t = Object.assign({ id: nextId++, state: 'live', y: -TH, doneAt: 0 }, req);
    if (live().length < MAX_SHOWN) k.tiles.push(t); else k.parked.push(t);
    emit('change');
    return t;
  }
  function refill() { while (live().length < MAX_SHOWN && k.parked.length) k.tiles.push(k.parked.shift()); }
  function finish(t, state) {
    t.state = state; t.doneAt = performance.now(); t.ay = t.y;
    refill();
    emit('finish', t, state === 'appr');
    emit('change');
  }
  function press() { if (k.down) return; k.down = true; k.downAt = performance.now(); k.holdUsed = false; }
  function cancel() { k.down = false; k.hold = 0; }
  function release() {
    if (!k.down) return;
    k.down = false; k.hold = 0;
    if (k.holdUsed) return;
    const now = performance.now();
    if (!lowest()) return;
    if (!ready()) { k.earlyUntil = now + 900; emit('gesture', 'early'); return; }   // still falling: ignored
    if (k.pendingTapAt && now - k.lastTapAt < DBL) {                                  // second tap: deny
      k.pendingTapAt = 0;
      emit('gesture', 'double');
      finish(lowest(), 'deny');
      return;
    }
    k.lastTapAt = now; k.pendingTapAt = now + DBL;
  }
  function tick(now) {
    const t = lowest();
    if (k.down && !k.holdUsed && t && t.risky && ready()) {
      k.hold = Math.min(1, (now - k.downAt) / HOLD);
      if (k.hold >= 1) { k.holdUsed = true; k.hold = 0; k.pendingTapAt = 0; emit('gesture', 'hold'); finish(t, 'appr'); }
    }
    if (k.pendingTapAt && now >= k.pendingTapAt) {
      k.pendingTapAt = 0;
      const l = lowest();
      if (!l) return;
      if (l.risky) { k.hintUntil = now + 1100; emit('gesture', 'needhold'); }
      else { emit('gesture', 'tap'); finish(l, 'appr'); }
    }
  }
  function settle(dt) {
    let slotBottom = HIT;
    const now = performance.now();
    live().forEach((t, i) => {
      const h = i === 0 ? THR : TH, target = slotBottom - h;
      if (reduced) t.y = target;
      else if (t.y < target) {
        t.v = Math.min(FALL * 1.25, (t.v || FALL * 0.35) + FALL * 2.4 * dt);   // slow in: it picks up speed
        t.y = Math.min(target, t.y + t.v * dt); t.moving = true;
        if (t.y >= target) { t.landAt = now; t.moving = false; t.v = 0; if (i === 0) emit('land', t); }
      } else { t.y = target; t.moving = false; }
      slotBottom = target - GAP;
    });
  }

  // drawing
  const F1 = `${10 * S}px Silkscreen, "JetBrains Mono", monospace`, F2 = `${17 * S}px Silkscreen, "JetBrains Mono", monospace`;
  const ink = (hex) => { const v = parseInt(hex.slice(1), 16), r = v >> 16, g = (v >> 8) & 255, b = v & 255; return (r * 299 + g * 587 + b * 114) / 1000 > 110 ? '#141414' : '#FFFFFF'; };
  const rgba = (hex, a) => { const v = parseInt(hex.slice(1), 16); return `rgba(${v >> 16},${(v >> 8) & 255},${v & 255},${a})`; };
  const clamp = (v) => Math.max(0, Math.min(1, v));
  function rr(x, y, w, h, r) {
    x *= S; y *= S; w *= S; h *= S; r *= S;
    c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }
  function text(s, x, y, font, color, maxW) {
    c.font = font; c.fillStyle = color; c.textBaseline = 'top';
    let str = String(s || '');
    if (maxW) while (str.length > 1 && c.measureText(str).width > maxW * S) str = str.slice(0, -2) + '.';
    c.fillText(str, x * S, y * S);
  }
  function centered(s, y, font, color) { c.font = font; text(s, (W * S - c.measureText(s).width) / 2 / S, y, font, color); }
  function seeded(n) { let x = (n * 2654435761) >>> 0; return () => ((x = (Math.imul(x, 1664525) + 1013904223) >>> 0) / 4294967296); }

  function drawTile(t, isReady, now) {
    if (t.state === 'appr') return drawYes(t, now);
    let h = isReady ? THR : TH;
    let x = TX, w = TW, yOff = 0;
    if (!reduced && t.state === 'live') {
      if (t.moving) { const st = Math.min(0.08, (t.v || 0) / FALL * 0.06); h *= 1 + st; w *= 1 - st * 0.6; }                       // stretch while falling
      const since = performance.now() - (t.landAt || -1e9);
      if (since < 360) { const d = Math.exp(-since / 90) * Math.cos(since / 38); h *= 1 - 0.13 * d; w *= 1 + 0.05 * d; yOff = 0.13 * d * (isReady ? THR : TH); }   // squash, then settle
      x = TX + (TW - w) / 2;
    }
    if (t.state === 'deny') { x -= reduced ? 0 : Math.min(1, (now - t.doneAt) / DENY) * 190; centered('DENIED', 60, F2, RED); }
    const yy = t.y + yOff;
    c.fillStyle = t.color; rr(x, yy, w, h, 6); c.fill();
    if (t.risky) { c.strokeStyle = RED; c.lineWidth = S; rr(x - 3, yy - 3, w + 6, h + 6, 8); c.stroke(); }
    const kk = ink(t.color);
    text(t.risky ? 'RISKY' : t.src, x + 8, yy + 7, F1, kk, TW - 16);
    text(t.l1, x + 8, yy + 19, F2, kk, TW - 16);
    text(t.l2, x + 8, yy + 40, F1, kk, TW - 16);
    if (isReady) {
      text(t.l3, x + 8, yy + 54, F1, kk, TW - 16);
      if (t.risky) {
        c.fillStyle = '#C6C6C6'; c.fillRect((x + 8) * S, (yy + h - 12) * S, (TW - 16) * S, 5 * S);
        c.fillStyle = RED; c.fillRect((x + 8) * S, (yy + h - 12) * S, (TW - 16) * k.hold * S, 5 * S);
      }
    }
  }
  // the "yes" moment: the tile slams the line, the lane flashes, the tile shatters upward, a check draws itself
  function drawYes(t, now) {
    const e = now - t.doneAt, top = t.ay ?? HIT - THR, col = t.color;
    if (e < PRESS && !reduced) {
      const q = (e / PRESS) ** 2, hh = THR * (1 - 0.55 * q), yy = top + THR - hh;
      c.fillStyle = col; rr(TX, yy, TW, hh, 6); c.fill();
      c.fillStyle = `rgba(255,255,255,${0.6 * q})`; rr(TX, yy, TW, hh, 6); c.fill();
      return;
    }
    const f = reduced ? 400 : e - PRESS;
    if (f < 170) { c.fillStyle = rgba(col, 0.34 * (1 - f / 170)); c.fillRect(0, 0, W * S, H * S); }
    if (!reduced) {
      const rnd = seeded(t.id), cols = 8, rows = 3, cw = TW / cols, ch = (THR * 0.45) / rows, y0 = top + THR * 0.55;
      for (let r = 0; r < rows; r++) for (let q = 0; q < cols; q++) {
        const vx = (rnd() - 0.5) * 150, vy = -(230 + rnd() * 330), life = 420 + rnd() * 280, light = rnd() < 0.3, p = f / life;
        if (p >= 1) continue;
        const sec = f / 1000, sz = 1 - 0.65 * p, px = TX + q * cw + vx * sec, py = y0 + r * ch + vy * sec + 150 * sec * sec;
        c.globalAlpha = 1 - p * p; c.fillStyle = light ? '#FFFFFF' : col;
        c.fillRect(px * S, py * S, Math.max(1, cw * sz - 1) * S, Math.max(1, ch * sz - 1) * S);
      }
      c.globalAlpha = 1;
    }
    const draw = clamp((f - 30) / 210), pop = 1 + 0.3 * Math.sin(Math.PI * clamp((f - 230) / 190));
    const fade = 1 - clamp((f - (APPR - PRESS - 200)) / 200), cx = W / 2, cy = 128, R = 42 * pop;
    c.save();
    c.globalAlpha = fade; c.lineCap = 'round'; c.lineJoin = 'round'; c.strokeStyle = col; c.lineWidth = 4 * S;
    c.beginPath(); c.arc(cx * S, cy * S, R * S, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * draw); c.stroke();
    const pts = [[-24, 2], [-7, 19], [26, -20]].map(([dx, dy]) => [cx + dx * pop, cy + dy * pop]);
    const seg = pts.slice(1).map((p, i) => Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]));
    let left = (seg[0] + seg[1]) * clamp((f - 90) / 190);
    c.lineWidth = 8 * S; c.beginPath(); c.moveTo(pts[0][0] * S, pts[0][1] * S);
    for (let i = 0; i < 2 && left > 0; i++) {
      const q = Math.min(1, left / seg[i]);
      c.lineTo((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * q) * S, (pts[i][1] + (pts[i + 1][1] - pts[i][1]) * q) * S);
      left -= seg[i];
    }
    c.stroke();
    c.globalAlpha = fade * clamp((f - 170) / 140);
    centered('APPROVED', cy + R + 12, F2, col);
    c.restore();
  }
  function render(now) {
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.fillStyle = '#08090A'; c.fillRect(0, 0, W * S, H * S);
    const lv = live(), low = lv[0], isReady = ready();
    const yes = k.tiles.find((t) => t.state === 'appr');
    const since = yes ? now - yes.doneAt - PRESS : 1e9;
    c.save();
    if (since >= 0 && since < 130 && !reduced) c.translate(Math.round(Math.sin(since / 9) * 3 * (1 - since / 130)) * S, 0);
    k.tiles.forEach((t) => { if (t.state !== 'live') drawTile(t, true, now); });
    lv.forEach((t) => drawTile(t, t === low && isReady, now));
    if (since >= 0 && since < 320) { c.fillStyle = rgba(yes.color, 1 - since / 320); c.fillRect(6 * S, (HIT - 1) * S, (W - 12) * S, 3 * S); }
    c.restore();
    c.fillStyle = '#4A4C52';
    for (let x = 6; x < W - 6; x += 6) c.fillRect(x * S, HIT * S, 3 * S, S);
    if (low && isReady) {
      const msg = low.risky ? (now < k.hintUntil ? "HOLD, DON'T TAP" : 'HOLD 1.0 S TO RUN') : 'TAP OK  2 TAPS NO';
      text(msg, 8, HIT + 10, F1, low.risky ? RED : low.color);
    } else if (low && now < k.earlyUntil) text('LET IT LAND', 8, HIT + 10, F1, '#9A9DA3');
    else if (!k.tiles.length) centered('ALL CLEAR', 150, F1, '#8A8D93');
    c.fillStyle = '#08090A'; c.fillRect(0, 0, W * S, 20 * S);                       // header last, so tiles never cover it
    text('01 PC', 8, 6, F1, '#8A8D93'); text('100%', W - 40, 6, F1, '#8A8D93');
    if (k.parked.length) { c.fillStyle = '#FFFFFF'; rr(W / 2 - 36, 3, 72, 14, 3); c.fill(); centered(`+${k.parked.length} MORE`, 6, F1, '#141414'); }
  }
  function step(now) {
    const dt = Math.min(0.1, k.last ? (now - k.last) / 1000 : 0); k.last = now;
    settle(dt); tick(now);
    const n = k.tiles.length;
    k.tiles = k.tiles.filter((t) => t.state === 'live' || now - t.doneAt < (t.state === 'appr' ? APPR : DENY));
    if (k.tiles.length !== n) emit('change');
    render(now);
  }
  return { submit, press, release, cancel, step, k, live, lowest, ready, RED };
};

// ---------- "Try it": the working key, the request buttons, and "add your own"
if (document.getElementById('demo')) (() => {
  const SRC = {
    claude: { name: 'CLAUDE CODE', label: 'Claude Code', color: '#D97757', where: 'athens-sound',
      pool: [['Bash', 'npm run test'], ['Edit', 'src/routes.ts'], ['Write', 'docs/setup.md'], ['Bash', 'npx prettier --write .']], risky: [['Bash', 'rm -rf build/']] },
    codex: { name: 'CODEX', label: 'Codex', color: '#E8E6E1', where: 'gridaid', pool: [['Shell', 'pytest -q'], ['Patch', 'app/models.py'], ['Shell', 'ruff check .']], risky: [] },
    gemini: { name: 'GEMINI CLI', label: 'Gemini CLI', color: '#5B8DEF', where: 'lab-notes', pool: [['Write', 'README.md'], ['Shell', 'pip install pandas'], ['Edit', 'analysis/grade.py']], risky: [] },
    git: { name: 'GIT PUSH', label: 'git push', color: '#3FB950', where: 'athens-sound-co', pool: [['main to origin', '3 commits +142 -37'], ['feat/lanes', '1 commit +18 -4']], risky: [['main to origin', 'FORCE 1 commit +12 -40']] },
  };
  const canvas = document.getElementById('demo'), cap = document.getElementById('capbtn'), body = document.getElementById('nodkey');
  const bench = document.querySelector('.bench'), list = document.getElementById('sendList'), said = document.getElementById('said');
  const pick = (a) => a[Math.floor(Math.random() * a.length)];
  const lit = (id) => { const el = document.getElementById(id); if (!el) return; el.classList.add('lit'); clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove('lit'), 1600); };
  const nod = window.makeNod(canvas, {
    change: updateButtons,
    gesture: (g) => {
      if (g === 'tap') lit('g-tap'); if (g === 'double') lit('g-double'); if (g === 'hold' || g === 'needhold') lit('g-hold');
      if (g === 'double') again(body, 'shake');
      if (g === 'early' || g === 'needhold') again(body, 'nudge');
    },
    land: () => { bench.classList.add('focus'); },
    finish: (t, ok) => {
      t.done = ok ? 'YES' : 'NO';
      if (said) said.textContent = `${t.label}: ${ok ? 'allowed' : 'denied'}`;
      if (t.btn) { t.btn.dataset.state = ok ? 'yes' : 'no'; t.btn.querySelector('.go').textContent = ok ? 'YES' : 'NO';
        const btn = t.btn; clearTimeout(btn._r); btn._r = setTimeout(() => { btn._r = 0; updateButtons(); }, 1500); }
      if (ok) { cap.style.setProperty('--g', t.risky ? 'var(--red)' : t.color); again(cap, 'ok-burst'); }
      if (!nod.lowest()) bench.classList.remove('focus');
    },
  });
  function again(el, cls) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); clearTimeout(el['_' + cls]); el['_' + cls] = setTimeout(() => el.classList.remove(cls), 700); }
  // each button shows where its latest request is: on the key, queued, or answered
  function updateButtons() {
    const busy = new Map();
    nod.k.tiles.forEach((t) => { if (t.state === 'live' && t.btn) busy.set(t.btn, 'ON KEY'); });
    nod.k.parked.forEach((t) => { if (t.btn && !busy.has(t.btn)) busy.set(t.btn, 'QUEUED'); });
    list.querySelectorAll('.send').forEach((b) => {
      if (busy.has(b)) { b.dataset.state = 'busy'; b.querySelector('.go').textContent = busy.get(b); }
      else if (b.dataset.state === 'busy' || (b.dataset.state && !b._r)) { b.dataset.state = ''; b.querySelector('.go').textContent = 'SEND'; }
    });
  }
  function ask(srcKey, o = {}) {
    const s = SRC[srcKey], risky = s.always !== undefined ? s.always : (!!o.risky && s.risky.length > 0);
    const [l1, l2] = o.first && !risky ? s.pool[0] : pick(risky && s.risky.length ? s.risky : s.pool);
    const btn = o.btn || list.querySelector(`.send[data-src="${srcKey}"]:not([data-risky])`);
    if (btn) { clearTimeout(btn._r); btn._r = 0; }
    const t = nod.submit({ srcKey, label: s.label, src: s.name, color: s.color, l1, l2, l3: risky ? `${s.where}  RISKY` : s.where, risky, btn });
    updateButtons();
    return t;
  }
  window.nodDemo = nod;
  const sent = {};
  list.addEventListener('click', (e) => {
    const b = e.target.closest('.send'); if (!b) return;
    b.classList.remove('fired'); void b.offsetWidth; b.classList.add('fired'); setTimeout(() => b.classList.remove('fired'), 650);
    if (b.dataset.burst) { ['claude', 'codex', 'git', 'gemini', 'claude'].forEach((s, i) => setTimeout(() => ask(s), i * 260)); return; }
    const key = b.dataset.src + (b.dataset.risky || '');
    ask(b.dataset.src, { risky: !!b.dataset.risky, first: !sent[key], btn: b }); sent[key] = true;
  });

  // ---- add your own: a name, what it asks, a color, and whether it needs a hold
  const maker = document.getElementById('maker'), cmd = document.getElementById('makerCmd');
  const slug = (v) => (v || 'my-tool').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 24) || 'my-tool';
  const q = (v) => '"' + String(v).replace(/(["\\$`])/g, '\\$1') + '"';
  let nCustom = 0;
  function addCustom(c, send) {
    const key = 'c' + (++nCustom);
    SRC[key] = { name: c.name.toUpperCase().slice(0, 16), label: c.name, color: c.color, where: 'your script', pool: [[c.l1, c.l2]], risky: c.risky ? [[c.l1, c.l2]] : [], always: c.risky };
    const b = document.createElement('button'); b.type = 'button'; b.className = 'send custom'; b.dataset.src = key;
    b.innerHTML = `<i style="background:${c.risky ? '#F04438' : c.color}"></i><span><span class="who"></span><span class="cmd"></span></span><span class="go">SEND</span>`;
    b.querySelector('.who').textContent = c.name; b.querySelector('.cmd').textContent = c.l1 + (c.l2 ? ' ' + c.l2 : '') + (c.risky ? '  (hold)' : '');
    const burst = list.querySelector('[data-burst]'); list.insertBefore(b, burst);
    if (send) { b.classList.add('fired'); ask(key, { btn: b }); }
  }
  function readMaker() {
    const f = new FormData(maker);
    return { name: (f.get('name') || '').trim() || 'My tool', l1: (f.get('l1') || '').trim() || 'Go ahead?', l2: (f.get('l2') || '').trim(), color: f.get('color') || '#E5B53A', risky: !!f.get('risky') };
  }
  function showCmd() {
    if (!cmd) return;
    const c = readMaker(), id = slug(c.name);
    cmd.textContent =
`# 1. in ~/.nod/config.json
"colors": { "${id}": "${c.color.replace('#', '')}" },
"labels": { "${id}": "${c.name.toUpperCase().slice(0, 16)}" }

# 2. from any script
nod ask --source ${id} --l1 ${q(c.l1.slice(0, 24))}${c.l2 ? ' --l2 ' + q(c.l2) : ''}${c.risky ? ' --risky' : ''}`;
  }
  if (maker) {
    maker.addEventListener('input', showCmd);
    maker.addEventListener('submit', (e) => {
      e.preventDefault();
      const c = readMaker(); addCustom(c, true);
      try { const saved = JSON.parse(localStorage.getItem('nodCustom') || '[]'); saved.push(c); localStorage.setItem('nodCustom', JSON.stringify(saved.slice(-6))); } catch (err) { /* storage can be off; the button still works */ }
    });
    try { JSON.parse(localStorage.getItem('nodCustom') || '[]').forEach((c) => addCustom(c, false)); } catch (err) { /* ignore */ }
    showCmd();
  }

  // press, release: pointer on the keycap, or the space bar while this section is on screen
  const down = () => { nod.press(); cap.classList.add('down'); body.classList.add('pressed'); };
  const up = () => { nod.release(); cap.classList.remove('down', 'holding'); body.classList.remove('pressed'); };
  cap.addEventListener('pointerdown', (e) => { e.preventDefault(); cap.setPointerCapture?.(e.pointerId); cap.focus({ preventScroll: true }); down(); });
  cap.addEventListener('pointerup', up);
  cap.addEventListener('pointercancel', () => { nod.cancel(); cap.classList.remove('down', 'holding'); body.classList.remove('pressed'); });
  cap.addEventListener('contextmenu', (e) => e.preventDefault());
  let onScreen = false, started = false;
  const typing = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable);
  document.addEventListener('keydown', (e) => {
    const isKey = e.code === 'Space' || (e.code === 'Enter' && e.target === cap);
    if (!isKey || !onScreen || typing(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.closest && e.target.closest('button, a, summary, label') && e.target !== cap) return;
    e.preventDefault(); if (!e.repeat) down();
  });
  document.addEventListener('keyup', (e) => { if ((e.code === 'Space' || e.code === 'Enter') && nod.k.down) { e.preventDefault(); up(); } });
  let raf = 0;
  function loop(now) {
    nod.step(now);
    const low = nod.lowest(), rdy = nod.ready();
    cap.style.setProperty('--glow', low && rdy ? (low.risky ? 'rgba(240,68,56,.55)' : 'rgba(229,181,58,.32)') : 'transparent');
    cap.classList.toggle('holding', nod.k.hold > 0);
    cap.style.setProperty('--p', nod.k.hold.toFixed(3));
    raf = onScreen ? requestAnimationFrame(loop) : 0;
  }
  new IntersectionObserver((es) => es.forEach((e) => {
    onScreen = e.isIntersecting;
    if (onScreen && !raf) raf = requestAnimationFrame(loop);
    if (onScreen && !started && e.intersectionRatio > 0.4) { started = true; setTimeout(() => { if (!nod.k.tiles.length) { ask('claude', { first: true }); sent.claude = true; } }, 600); }
  }), { threshold: [0, 0.4] }).observe(bench);
  if (document.fonts && document.fonts.load) document.fonts.load('20px Silkscreen');
  nod.step(performance.now());
})();

// ---------- pre-order: the button itself grows to fill the screen, then you're at the sign-up at the bottom of the home page
(() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fill = document.createElement('div'); fill.id = 'fill'; fill.setAttribute('aria-hidden', 'true'); document.body.appendChild(fill);
  const home = document.body.dataset.page === 'home', list = document.getElementById('list');
  function land() {
    window.scrollTo({ top: list.getBoundingClientRect().top + scrollY, behavior: 'instant' });
    list.classList.add('landed');
    requestAnimationFrame(() => { fill.className = 'on fade'; setTimeout(() => { fill.className = ''; fill.removeAttribute('style'); }, 420); });
    const f = list.querySelector('input'); if (f) setTimeout(() => f.focus({ preventScroll: true }), 450);
  }
  function go(e) {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    if (fill.className) return;
    const btn = e.currentTarget;
    const next = () => { if (home) land(); else { sessionStorage.setItem('nodFill', '1'); location.href = 'index.html#list'; } };
    if (reduced) { next(); return; }
    const r = btn.getBoundingClientRect(), rad = parseFloat(getComputedStyle(btn).borderTopLeftRadius) || 6;
    const T = r.top, Rt = innerWidth - r.right, B = innerHeight - r.bottom, L = r.left;
    const nearTop = T <= B, nearRight = Rt <= L;
    const ins = (t, rr, b, l, k) => `inset(${t}px ${rr}px ${b}px ${l}px round ${k}px)`;
    // step 1: reach the two closest edges. step 2: the other two
    const mid = ins(nearTop ? 0 : T, nearRight ? 0 : Rt, nearTop ? B : 0, nearRight ? L : 0, rad);
    fill.style.clipPath = ins(T, Rt, B, L, rad);
    fill.className = 'on';
    btn.style.visibility = 'hidden';
    const anim = fill.animate([
      { clipPath: ins(T, Rt, B, L, rad), easing: 'cubic-bezier(.55,0,.25,1)' },
      { clipPath: mid, offset: 0.42, easing: 'cubic-bezier(.55,0,.25,1)' },
      { clipPath: ins(0, 0, 0, 0, 0) },
    ], { duration: 680, fill: 'forwards' });
    anim.onfinish = () => { fill.style.clipPath = 'none'; anim.cancel(); setTimeout(() => { btn.style.visibility = ''; }, 500); next(); };
  }
  document.querySelectorAll('a[href$="#list"]').forEach((a) => a.addEventListener('click', go));
  if (home && sessionStorage.getItem('nodFill')) {
    sessionStorage.removeItem('nodFill'); fill.className = 'on'; fill.style.clipPath = 'none';
    addEventListener('load', () => setTimeout(land, 60));
  } else if (home && location.hash === '#list') list.classList.add('landed');
  // the logo takes you back to the top of the page you're on
  const logo = document.querySelector('.logo');
  logo.addEventListener('click', (e) => {
    if (e.metaKey || e.ctrlKey) return;
    if (!home) return;                                              // other pages: a normal link to the home page
    e.preventDefault();                                             // home: glide back to the top
    if (reduced) { window.scrollTo(0, 0); return; }
    const from = Math.min(scrollY, innerHeight * 0.9), t0 = performance.now(), T = 520;   // long way up: skip most of it, glide the last screen
    window.scrollTo(0, from);
    (function glide(now) {
      const k = Math.min(1, (now - t0) / T), e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      window.scrollTo(0, from * (1 - e));
      if (k < 1) requestAnimationFrame(glide);
    })(t0);
  });
})();

// ---------- intro: "Sit back and ___". The drum turns on a timer: nod, relax, approve, trust, and around again
if (document.getElementById('intro')) {
  const WORDS = ['nod', 'relax', 'approve', 'trust', 'nod', 'relax', 'approve', 'trust'], N = WORDS.length, STEP = 360 / N, TURNS = 4;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const intro = document.getElementById('intro'), drum = intro.querySelector('.drum'), live = document.getElementById('wheelWord');
  const faces = WORDS.map((w) => { const f = document.createElement('span'); f.className = 'face'; f.textContent = w; drum.appendChild(f); return f; });
  const R = 0.5 / Math.tan(Math.PI / N);
  faces.forEach((f, i) => { f.style.transform = `rotateX(${-i * STEP}deg) translateZ(${R}em)`; });
  let a = 0, shown = -1;
  const sm = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  function paint() {
    drum.style.transform = `translateZ(${-R}em) rotateX(${a}deg)`;
    faces.forEach((f, i) => {
      const d = Math.abs(((a - i * STEP) % 360 + 540) % 360 - 180);           // degrees away from the front
      const front = 1 - sm(d / STEP);                                            // 1 at the front, 0 one step away
      const vis = d >= 88 ? 0 : Math.cos(d * Math.PI / 180);                    // fades out as it turns over the top or bottom
      f.style.opacity = vis.toFixed(3);
      f.style.color = `rgba(229,181,58,${front.toFixed(3)})`;
      f.style.webkitTextStroke = `1.5px rgba(237,235,228,${(0.5 * (1 - front)).toFixed(3)})`;
      f.style.borderTopColor = `rgba(237,235,228,${(0.32 * vis).toFixed(3)})`;
    });
    const w = Math.round(a / STEP) % N;
    if (w !== shown) { shown = w; live.textContent = WORDS[(w + N) % N]; }
  }
  // on a timer: each word holds, then the drum turns smoothly to the next. Never stops dead, never jumps
  const PERIOD = 2600;                                       // ms per word
  const ease = (x) => x - Math.sin(2 * Math.PI * x) / (2 * Math.PI);
  let onScreen = true, t0 = performance.now() + 900, pausedAt = 0;
  function frame(now) {
    if (onScreen) {
      const t = Math.max(0, now - t0) / PERIOD, n = Math.floor(t);
      a = STEP * (n + (reduced ? 0 : ease(t - n)));
      paint();
    }
    requestAnimationFrame(frame);
  }
  new IntersectionObserver((es) => es.forEach((e) => {
    const vis = e.isIntersecting && e.intersectionRatio > 0;
    if (!vis && onScreen) pausedAt = performance.now();
    if (vis && !onScreen && pausedAt) t0 += performance.now() - pausedAt;   // pick up where it left off
    onScreen = vis;
  })).observe(intro);
  paint(); requestAnimationFrame(frame);
  const c = intro.querySelector('canvas'), x = c.getContext('2d');
  c.width = 1800; c.height = 1100;
  window.drawContours(x, c.width, c.height, { step: 5, levels: 40, scale: 1 / 520, seed: 5, line: 'rgba(237,235,228,.16)', major: 'rgba(229,181,58,.42)', lw: 1.1, mw: 1.6 });
}


// ---------- a short gradient trail on white text, wherever the mouse goes
(() => {
  if (!matchMedia('(hover: hover) and (pointer: fine)').matches || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const SEL = '.logo, .foot-mark, .intro-line .t, h2, .page-head h1, .forstrip b, .way h2, .rows .n, .honest h3, .gestures h3';
  const LIFE = 650, COLORS = ['229,181,58', '246,208,106', '143,176,224', '217,119,87'];
  const live = new Map();                                   // element -> { pts, base }
  let raf = 0, hue = 0;
  addEventListener('pointermove', (e) => {
    const el = e.target.closest && e.target.closest(SEL);
    if (!el || el.closest('.sheet')) return;               // the blue blueprint sheet keeps its own colors
    let st = live.get(el);
    if (!st) { st = { pts: [], base: getComputedStyle(el).color }; live.set(el, st); }
    const r = el.getBoundingClientRect(), fs = parseFloat(getComputedStyle(el).fontSize);
    hue = (hue + 1) % (COLORS.length * 6);
    st.pts.push({ x: e.clientX - r.left, y: e.clientY - r.top, t: performance.now(), c: COLORS[Math.floor(hue / 6)], s: Math.max(18, fs * 0.55) });
    if (st.pts.length > 28) st.pts.shift();
    if (!raf) raf = requestAnimationFrame(tick);
  }, { passive: true });
  function tick(now) {
    raf = 0;
    for (const [el, st] of live) {
      st.pts = st.pts.filter((p) => now - p.t < LIFE);
      if (!st.pts.length) { el.classList.remove('trail-on'); el.style.backgroundImage = ''; live.delete(el); continue; }
      const blobs = st.pts.map((p) => { const k = 1 - (now - p.t) / LIFE, a = (k * k).toFixed(3);
        return `radial-gradient(circle ${p.s.toFixed(0)}px at ${p.x.toFixed(0)}px ${p.y.toFixed(0)}px, rgba(${p.c},${a}), rgba(${p.c},0))`; });
      el.style.backgroundImage = blobs.reverse().join(',') + `, linear-gradient(${st.base}, ${st.base})`;
      el.classList.add('trail-on');
    }
    if (live.size) raf = requestAnimationFrame(tick);
  }
})();

// ---------- Dibu: pops up when his spot scrolls into view, and his eyes follow the pointer smoothly
(() => {
  const spots = document.querySelectorAll('.fred-ledge, .fred-side');
  if (spots.length) {
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('up'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -10% 0px' });
    spots.forEach((s) => io.observe(s));
  }
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const dogs = [...document.querySelectorAll('.fred-svg')].map((el) => ({ el, p: el.querySelector('.pupils'), x: 0, y: 0, tx: 0, ty: 0 }));
  if (!dogs.length) return;
  let px = -1, py = -1, raf = 0;
  const tick = () => {
    raf = 0;
    let moving = false;
    for (const d of dogs) {
      const r = d.el.getBoundingClientRect();
      if (r.bottom < 0 || r.top > innerHeight || r.width === 0) continue;
      if (px >= 0) {
        const dx = px - (r.left + r.width / 2), dy = py - (r.top + r.height * 0.5);
        const dist = Math.hypot(dx, dy) || 1, m = Math.min(1, dist / 380) * 3.4;
        d.tx = (dx / dist) * m; d.ty = (dy / dist) * m;
      }
      d.x += (d.tx - d.x) * 0.14; d.y += (d.ty - d.y) * 0.14;
      if (Math.abs(d.tx - d.x) > 0.02 || Math.abs(d.ty - d.y) > 0.02) moving = true;
      d.p.setAttribute('transform', `translate(${d.x.toFixed(2)} ${d.y.toFixed(2)})`);
    }
    if (moving) raf = requestAnimationFrame(tick);
  };
  addEventListener('pointermove', (e) => { px = e.clientX; py = e.clientY; if (!raf) raf = requestAnimationFrame(tick); }, { passive: true });
  addEventListener('scroll', () => { if (!raf && px >= 0) raf = requestAnimationFrame(tick); }, { passive: true });
})();

// ---------- "Nod for" strip: drifts left on its own, drag it with the mouse or a finger, and it carries on with a little momentum
(() => {
  const strip = document.querySelector('.forstrip'), track = strip && strip.querySelector('.track');
  if (!track) return;
  track.style.animation = 'none';
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const BASE = calm ? 0 : -60;                 // px per second
  let half = track.scrollWidth / 2, x = 0, vel = BASE, target = BASE, drag = null, moved = 0, last = performance.now();
  addEventListener('resize', () => { half = track.scrollWidth / 2; });
  const wrap = () => { if (half > 0) { x = x % half; if (x > 0) x -= half; } };
  const frame = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (!drag) { vel += (target - vel) * Math.min(1, dt * 2.2); x += vel * dt; }
    wrap();
    track.style.transform = `translate3d(${x.toFixed(2)}px,0,0)`;
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  strip.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') target = 0; });
  strip.addEventListener('pointerleave', () => { if (!drag) target = BASE; });
  strip.addEventListener('focusin', () => { target = 0; });
  strip.addEventListener('focusout', () => { target = BASE; });
  strip.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    drag = { id: e.pointerId, px: e.clientX, t: performance.now() }; moved = 0; vel = 0;
    strip.classList.add('dragging');
  });
  strip.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const now = performance.now(), dx = e.clientX - drag.px, dt = Math.max(1, now - drag.t) / 1000;
    if (!strip.hasPointerCapture(e.pointerId) && Math.abs(moved + dx) > 4) strip.setPointerCapture(e.pointerId);
    x += dx; moved += Math.abs(dx);
    vel = vel * 0.6 + (dx / dt) * 0.4;
    drag.px = e.clientX; drag.t = now;
  });
  const end = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (performance.now() - drag.t > 90) vel = 0;           // held still before letting go: no fling
    drag = null; strip.classList.remove('dragging');
    target = e.pointerType === 'mouse' && strip.matches(':hover') ? 0 : BASE;
  };
  strip.addEventListener('pointerup', end);
  strip.addEventListener('pointercancel', end);
  // a drag isn't a click: don't follow the link you happened to grab
  strip.addEventListener('click', (e) => { if (moved > 6) { e.preventDefault(); e.stopPropagation(); } }, true);
})();

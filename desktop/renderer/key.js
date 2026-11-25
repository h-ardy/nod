// Practice key: an on-screen Nod for testing Nod Dot with no hardware.
// Send a made-up request on the left, answer it on the key in the middle, and see what the agent heard on the right.
// The daemon decides everything, with the same rules as the firmware; this window only draws its simulated screen.
(() => {
  const $ = (id) => document.getElementById(id);
  const body = document.body;
  const api = window.nodKey;
  const HOLD_MS = 500, DOUBLE_MS = 320;          // same as the firmware
  const CMD = 'bash ~/Documents/GitHub/nod/host/demo.sh key';

  const SAMPLES = [
    { source: 'claude-code', who: 'Claude Code', color: '#D97757', l1: 'Bash', l2: 'npm run test', l3: 'nod/site',
      detail: '$ npm run test\n\nRuns the test script in package.json.\nFolder: ~/Documents/GitHub/nod/site', why: 'Check the footer change did not break the build' },
    { source: 'codex', who: 'Codex', color: '#E8E6E1', l1: 'Patch', l2: 'app/models.py', l3: '+14 -3',
      detail: 'File: app/models.py\n+ SESSION_IDLE_MIN = 30\n+ def expired(s):\n+     return s.idle_minutes() > SESSION_IDLE_MIN\n- import os', why: 'Log users out after 30 minutes idle' },
    { source: 'gemini', who: 'Gemini CLI', color: '#5B8DEF', l1: 'Write', l2: 'README.md', l3: 'lab-notes',
      detail: 'File: README.md\n+ # Lab notes\n+ How to run the grading script on a new batch of slides.', why: 'Document the grading steps' },
    { source: 'git', who: 'git push', color: '#3FB950', l1: 'git push', l2: 'main to origin, 3 commits', l3: '+142 -37',
      detail: '$ git push origin main\n\n3 commits:\n  fix footer gap\n  add purpose text\n  clip the wheel', why: '' },
    { source: 'claude-code', who: 'Claude Code', color: '#D97757', l1: 'Bash', l2: 'rm -rf build/', l3: 'RISK: deletes files', risky: true,
      detail: '$ rm -rf build/\n\nDeletes the build folder and everything in it.\nFolder: ~/Documents/GitHub/nod/desktop', why: 'Clear old build output before packaging' },
  ];

  let ws = null, retry = 0, sim = false, tag = 0;
  const log = new Map();                         // tag -> li

  // ---- left: send buttons
  const list = $('sendList');
  SAMPLES.forEach((s, i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'send'; b.dataset.i = i;
    b.innerHTML = '<i></i><span><span class="who"></span><span class="cmd"></span></span><span class="go">SEND</span>';
    b.querySelector('i').style.background = s.risky ? 'var(--red)' : s.color;
    b.querySelector('.who').textContent = s.who;
    b.querySelector('.cmd').textContent = `${s.l1} ${s.l2}`;
    if (s.risky) { const em = document.createElement('em'); em.textContent = ' risky'; b.querySelector('.cmd').appendChild(em); }
    list.appendChild(b);
  });
  const burst = document.createElement('button');
  burst.type = 'button'; burst.className = 'send'; burst.dataset.burst = '1';
  burst.innerHTML = '<i></i><span><span class="who">Four at once</span><span class="cmd">a busy afternoon</span></span><span class="go">SEND</span>';
  burst.querySelector('i').style.background = 'var(--ink-3)';
  list.appendChild(burst);

  function send(s) {
    const t = ++tag;
    api.send({ ...s, tag: t });
    $('empty').hidden = true;
    const li = document.createElement('li');
    li.innerHTML = '<i></i><div class="what"><b></b><small></small></div><span class="st">WAITING</span>';
    li.querySelector('i').style.background = s.risky ? 'var(--red)' : s.color;
    li.querySelector('b').textContent = `${s.l1} ${s.l2}`;
    li.querySelector('small').textContent = s.who;
    $('log').prepend(li);
    log.set(t, li);
    while ($('log').children.length > 30) $('log').lastChild.remove();
  }
  list.addEventListener('click', (e) => {
    const b = e.target.closest('.send');
    if (!b || b.disabled) return;
    b.classList.remove('fired'); void b.offsetWidth; b.classList.add('fired'); setTimeout(() => b.classList.remove('fired'), 300);
    if (b.dataset.burst) { [0, 3, 1, 2].forEach((i, n) => setTimeout(() => send(SAMPLES[i]), n * 260)); return; }
    send(SAMPLES[Number(b.dataset.i)]);
  });
  api.onAnswer((a) => {
    const li = log.get(a.tag);
    if (!li) return;
    const st = li.querySelector('.st');
    const words = { allow: ['ALLOWED', 'ok'], deny: ['DENIED', 'no'], timeout: ['TIMED OUT', ''], unavailable: ['NO KEY', 'no'] };
    const [w, cls] = words[a.decision] || [String(a.decision).toUpperCase(), ''];
    st.textContent = w; st.className = 'st ' + cls;
  });

  // ---- middle: the key's screen, drawn from what the daemon says the simulated key holds
  const scr = $('scr'), glass = scr.parentElement;
  function fit() {
    const r = glass.getBoundingClientRect();
    scr.style.setProperty('--s', Math.min((r.width - 6) / 172, (r.height - 6) / 320).toFixed(4));
  }
  addEventListener('resize', fit); fit();

  let tiles = [];
  function draw(st) {
    const old = new Set(tiles.map((t) => t.id));
    tiles = st.tiles || [];
    const stack = $('stack');
    stack.textContent = '';
    for (const t of tiles) {
      const el = document.createElement('div');
      el.className = 'tile' + (t.t === 'note' ? ' note' : '') + (t.risk ? ' risk' : '') + (t.opened ? ' opened' : '');
      if (old.has(t.id)) el.style.animation = 'none';
      el.style.setProperty('--c', '#' + (t.c || 'E5B53A'));
      el.innerHTML = '<div class="row"><span class="src"></span><span class="code"></span></div><div class="l1"></div><div class="l2"></div>';
      el.querySelector('.src').textContent = t.src || '';
      el.querySelector('.code').textContent = t.code || '';
      el.querySelector('.l1').textContent = t.l1 || '';
      el.querySelector('.l2').textContent = t.l2 || '';
      if (t.opened || t.nolook) {
        const tagEl = document.createElement('div'); tagEl.className = 'tag';
        tagEl.textContent = t.opened ? 'OPEN ON YOUR SCREEN' : 'NO SCREEN';
        el.appendChild(tagEl);
      }
      stack.appendChild(el);
    }
    $('more').textContent = st.more ? `+${st.more} MORE` : '';
    const low = tiles[0];
    const hint = $('hint');
    hint.className = 'hint';
    if (!low) hint.textContent = 'NOTHING WAITING';
    else if (low.t === 'note') hint.textContent = 'TAP TO CLEAR';
    else if (low.nolook) hint.textContent = 'NO SCREEN. HOLD TO RUN';
    else if (low.opened) hint.textContent = 'TAP OK  2 NO';
    else hint.textContent = 'TAP OK  2 NO  HOLD MORE';
    $('cap').style.setProperty('--glow', low ? (low.risk ? 'rgba(232,85,61,.5)' : 'rgba(229,181,58,.3)') : 'transparent');
    if (st.msg) react(st.msg);
  }

  function flash(text, cls) {
    const f = $('flash');
    f.hidden = true; void f.offsetWidth;
    f.className = 'flash ' + cls; $('flashText').textContent = text; f.hidden = false;
    clearTimeout(flash.t); flash.t = setTimeout(() => { f.hidden = true; }, 900);
  }
  function again(el, cls) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); setTimeout(() => el.classList.remove(cls), 600); }
  function react(msg) {
    if (msg === 'allow') { flash('APPROVED', 'allow'); again($('cap'), 'ok'); }
    else if (msg === 'deny') { flash('DENIED', 'deny'); again($('nodkey'), 'shake'); }
    else if (msg === 'note cleared') flash('CLEARED', 'info');
    else if (msg === 'look') flash('OPENING ON YOUR SCREEN', 'info');
  }

  // ---- the cap: tap, double tap, hold. Timed like the firmware.
  const cap = $('cap');
  let downAt = 0, held = false, holdTimer = 0, pendingTap = 0, raf = 0;
  async function press(kind) {
    const res = await api.press(kind);
    if (res.status === 400) setMode('real');
    else if (res.status === 0) setMode('offline');
  }
  function ringLoop() {
    if (!downAt) return;
    cap.style.setProperty('--p', Math.min(1, (performance.now() - downAt) / HOLD_MS).toFixed(3));
    raf = requestAnimationFrame(ringLoop);
  }
  function down() {
    if (downAt || cap.disabled) return;
    downAt = performance.now(); held = false;
    cap.classList.add('down', 'holding'); $('nodkey').classList.add('pressed');
    holdTimer = setTimeout(() => { held = true; cap.classList.remove('holding'); press('hold'); }, HOLD_MS);
    raf = requestAnimationFrame(ringLoop);
  }
  function up() {
    if (!downAt) return;
    downAt = 0; clearTimeout(holdTimer); cancelAnimationFrame(raf);
    cap.classList.remove('down', 'holding'); $('nodkey').classList.remove('pressed');
    cap.style.setProperty('--p', 0);
    if (held) return;                                   // letting go of a hold is not a tap
    if (pendingTap) { clearTimeout(pendingTap); pendingTap = 0; press('double'); return; }
    pendingTap = setTimeout(() => { pendingTap = 0; press('tap'); }, DOUBLE_MS);
  }
  cap.addEventListener('pointerdown', (e) => { e.preventDefault(); cap.setPointerCapture(e.pointerId); cap.focus(); down(); });
  cap.addEventListener('pointerup', up);
  cap.addEventListener('pointercancel', up);
  cap.addEventListener('contextmenu', (e) => e.preventDefault());
  document.addEventListener('keydown', (e) => {
    if (e.code !== 'Space' || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.closest && e.target.closest('button') && e.target !== cap) e.target.blur();
    e.preventDefault(); if (!e.repeat) down();
  });
  document.addEventListener('keyup', (e) => { if (e.code === 'Space') { e.preventDefault(); up(); } });

  // ---- connection to the daemon
  function setMode(mode) {
    body.classList.remove('live', 'real', 'offline');
    body.classList.add(mode);
    sim = mode === 'live';
    $('state').textContent = { live: 'Practice mode', real: 'Running for real keys', offline: 'Nod is not running' }[mode];
    $('banner').hidden = mode === 'live';
    $('bannerText').textContent = mode === 'real'
      ? 'Nod is running for your real keys, so the practice key is off. Stop that Nod (Ctrl-C in its window) and start practice mode:'
      : "Nod isn't running. Start it in practice mode in Terminal:";
    list.querySelectorAll('.send').forEach((b) => { b.disabled = !sim; });
    cap.disabled = !sim;
    if (!sim) draw({ tiles: [], more: 0 });
  }
  $('cmd').textContent = CMD;
  $('copy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(CMD); $('copy').textContent = 'Copied'; setTimeout(() => { $('copy').textContent = 'Copy'; }, 1400); } catch (e) { /* select it instead */ }
  });

  async function connect() {
    const cfg = await api.config();
    if (!cfg.token) { setMode('offline'); return later(); }
    try {
      ws = new WebSocket(`ws://127.0.0.1:${cfg.port}/v1/events?role=key&token=${encodeURIComponent(cfg.token)}`);
    } catch (e) { setMode('offline'); return later(); }
    ws.onopen = () => { retry = 0; };
    ws.onmessage = (e) => {
      let m; try { m = JSON.parse(e.data); } catch (err) { return; }
      if (m.ev === 'keyhello') setMode(m.sim ? 'live' : 'real');
      else if (m.ev === 'sim' && m.lane === 0) draw(m);
    };
    ws.onclose = () => { setMode('offline'); later(); };
  }
  function later() { setTimeout(connect, Math.min(5000, 800 * 2 ** Math.min(retry++, 3))); }
  setMode('offline');
  connect();
})();

// Nod Dot panel. Listens to the Nod daemon and shows a request in full when its key is held.
// It can only open and close itself: approving and rejecting happen on the key.
(() => {
  const $ = (id) => document.getElementById(id);
  const body = document.body;
  const panel = $('panel');
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const OPEN_MS = calm ? 0 : 560;
  const PULSE_MS = calm ? 0 : 520;

  // In the app, the port and token come from the main process. In a plain browser (for testing),
  // pass them in the address: index.html?port=47823&token=...&corner=bottom-right
  const app = window.nodApp || null;
  const q = new URLSearchParams(location.search);

  let cfg = null;
  let ws = null;
  let retry = 0;
  const pending = new Map();     // id -> request
  let shown = null;              // request open in the panel
  let closing = null;

  function setCorner(corner) {
    body.classList.remove('top-right', 'top-left', 'bottom-right', 'bottom-left');
    body.classList.add(corner || 'top-right');
  }

  function refreshDot() {
    const list = [...pending.values()];
    body.classList.toggle('waiting', list.length > 0);
    body.classList.toggle('risky', list.some((r) => r.risky));
    body.classList.toggle('many', list.length > 1);
    $('count').textContent = list.length > 1 ? String(list.length) : '';
    const others = shown ? list.filter((r) => r.id !== shown.id).length : 0;
    $('more').textContent = others ? `${others} more waiting` : '';
  }

  // ---- the panel
  function fillDetail(text) {
    const pre = $('detail');
    pre.textContent = '';
    for (const line of String(text || '').split('\n')) {
      const span = document.createElement('span');
      span.textContent = line + '\n';
      if (line.startsWith('+ ')) span.className = 'add';
      else if (line.startsWith('- ')) span.className = 'del';
      else if (line.startsWith('$ ')) span.className = 'cmd';
      else if (/^(Tool|Folder|Flagged|File|URL):/.test(line)) span.className = 'meta';
      pre.appendChild(span);
    }
    pre.scrollTop = 0;
  }

  function fill(r) {
    $('swatch').style.background = r.color || '#E5B53A';
    $('label').textContent = r.label || r.source || 'REQUEST';
    $('lane').textContent = r.lane != null ? `· key ${r.lane + 1}` : '';
    $('code').textContent = r.code || '---';
    const risk = /RISK:\s*(.+)$/.exec(r.l3 || '');
    $('risk').hidden = !r.risky;
    $('risk').textContent = r.risky ? `Risky${risk ? `: ${risk[1]}` : ''}. Read it before you tap.` : '';
    $('l1').textContent = r.l1 || '';
    $('l2').textContent = r.l2 || '';
    $('whyBox').hidden = !r.why;
    $('why').textContent = r.why || '';
    fillDetail(r.detail || [r.l1, r.l2, r.l3].filter(Boolean).join('\n'));
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }

  async function open(r) {
    if (closing) { clearTimeout(closing); closing = null; }
    const already = shown && shown.id === r.id;
    shown = r;
    fill(r);
    refreshDot();
    if (already) return;
    $('result').hidden = true;
    if (!body.classList.contains('open')) {
      body.classList.add('pulsing');                       // the dot pulses twice, then opens
      await new Promise((ok) => setTimeout(ok, PULSE_MS));
      body.classList.remove('pulsing');
      panel.hidden = false;
      app && app.setExpanded(true);
      panel.getBoundingClientRect();                        // start the open animation from the dot
      body.classList.add('open');
      await new Promise((ok) => setTimeout(ok, OPEN_MS));
    }
    if (shown && shown.id === r.id) send({ cmd: 'opened', id: r.id });   // now the key takes a plain tap
  }

  function close(reason) {
    if (!shown) return;
    const id = shown.id;
    if (reason === 'user') send({ cmd: 'closed', id });
    shown = null;
    body.classList.remove('open');
    app && app.setExpanded(false);
    closing = setTimeout(() => { panel.hidden = true; closing = null; }, OPEN_MS);
    refreshDot();
  }

  function finish(id, decision) {
    pending.delete(id);
    refreshDot();
    if (!shown || shown.id !== id) return;
    const res = $('result');
    const words = { allow: 'Approved', deny: 'Rejected', seen: 'Cleared' };
    res.className = 'result ' + (decision === 'allow' ? 'allow' : decision === 'deny' ? 'deny' : 'gone');
    $('resultText').textContent = words[decision] || 'No longer waiting';
    res.hidden = false;
    setTimeout(() => close('done'), calm ? 900 : 750);
  }

  // ---- the daemon
  function onEvent(m) {
    if (m.ev === 'hello') {
      pending.clear();
      for (const r of m.pending || []) pending.set(r.id, r);
      if (shown && !pending.has(shown.id)) finish(shown.id, 'gone');
    } else if (m.ev === 'add') {
      if (m.req.kind === 'ask') pending.set(m.req.id, m.req);
    } else if (m.ev === 'done') {
      finish(m.id, m.decision);
    } else if (m.ev === 'look') {
      pending.set(m.req.id, m.req);
      open(m.req);
    }
    refreshDot();
  }

  async function connect() {
    if (app) cfg = await app.config();                     // re-read: the daemon may have made its token since
    else cfg = { port: Number(q.get('port') || 47823), token: q.get('token') || '', corner: q.get('corner') || 'top-right' };
    setCorner(cfg.corner);
    if (!cfg.token) { body.classList.add('offline'); return later(); }
    try {
      ws = new WebSocket(`ws://127.0.0.1:${cfg.port}/v1/events?token=${encodeURIComponent(cfg.token)}`);
    } catch (e) {
      return later();
    }
    ws.onopen = () => { retry = 0; body.classList.remove('offline'); };
    ws.onmessage = (e) => { try { onEvent(JSON.parse(e.data)); } catch (err) { /* ignore a bad line */ } };
    ws.onclose = () => {
      body.classList.add('offline');
      pending.clear();
      if (shown) close('gone');
      refreshDot();
      later();
    };
  }
  function later() { setTimeout(connect, Math.min(10000, 1000 * 2 ** Math.min(retry++, 3))); }

  $('close').addEventListener('click', () => close('user'));
  if (app) app.onCorner(setCorner);
  connect();
})();

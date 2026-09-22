/**
 * One watch. Instantiated once per watch on the page.
 *
 * Every element is looked up inside the instance's own root, so two of these
 * can run side by side without fighting over ids — which is what lets the page
 * show a live watch and a safe demo watch at the same time.
 *
 * `live: false` runs the whole interface for real except that power actions
 * and shortcut actions are never sent to the PC. That makes the guard on
 * shutdown something you can actually rehearse.
 */

(function (global) {
  'use strict';

  const PAGE_NAMES = ['קול', 'חשמל', 'מצב', 'כפתורים'];

  // -------------------------------------------------------------- icon set

  const ICONS = {
    'lock':      '<path d="M7 10V7a5 5 0 0 1 10 0v3"/><rect x="4.5" y="10" width="15" height="10.5" rx="3"/>',
    'moon':      '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    'restart':   '<path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1"/><path d="M20.5 4.5V10h-5.5"/>',
    'power':     '<path d="M12 3.5v8"/><path d="M6.8 6.6a8 8 0 1 0 10.4 0"/>',
    'camera.viewfinder': '<path d="M4 8.5V6a2 2 0 0 1 2-2h2.5"/><path d="M20 8.5V6a2 2 0 0 0-2-2h-2.5"/><path d="M4 15.5V18a2 2 0 0 0 2 2h2.5"/><path d="M20 15.5V18a2 2 0 0 1-2 2h-2.5"/><circle cx="12" cy="12" r="3"/>',
    'rectangle.3.group': '<rect x="3" y="4" width="18" height="6" rx="1.8"/><rect x="3" y="13" width="8" height="7" rx="1.8"/><rect x="13" y="13" width="8" height="7" rx="1.8"/>',
    'globe':     '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.4 2.5 3.6 5.4 3.6 8.5s-1.2 6-3.6 8.5c-2.4-2.5-3.6-5.4-3.6-8.5s1.2-6 3.6-8.5z"/>',
    'folder':    '<path d="M3.5 7.5A2 2 0 0 1 5.5 5.5h3.6l2 2.4h7.4a2 2 0 0 1 2 2v7.6a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    'chart.bar': '<path d="M5 20V11"/><path d="M12 20V5"/><path d="M19 20v-6"/>',
    'gearshape': '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.8v2.4M12 18.8v2.4M21.2 12h-2.4M5.2 12H2.8M18.5 5.5l-1.7 1.7M7.2 16.8l-1.7 1.7M18.5 18.5l-1.7-1.7M7.2 7.2 5.5 5.5"/>',
    'bolt':      '<path d="M13.5 2.5 5 13.5h6L10.5 21.5 19 10.5h-6z"/>',
  };

  function icon(name, size) {
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' +
      (ICONS[name] || ICONS.bolt) + '</svg>';
  }

  const CHECK_SVG =
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M5 12.5 10 17.5 19 7"/></svg>';

  const POWER_ICONS = { lock: 'lock', sleep: 'moon', restart: 'restart', shutdown: 'power' };

  const POWER_ACCENTS = {
    lock: '64,200,224',
    sleep: '94,92,230',
    restart: '255,159,10',
    shutdown: '255,69,58',
  };

  const ACTION_ACCENTS = {
    'screenshot': '64,200,224',
    'minimize-all': '94,92,230',
    'chrome': '255,159,10',
    'explorer': '255,214,10',
    'taskmgr': '191,90,242',
    'settings': '152,152,157',
  };
  const ACCENT_POOL = [
    '10,132,255', '48,209,88', '255,55,95', '100,210,255', '191,90,242', '255,159,10',
  ];

  function accentFor(id) {
    if (ACTION_ACCENTS[id]) return ACTION_ACCENTS[id];
    let hash = 0;
    for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
    return ACCENT_POOL[hash % ACCENT_POOL.length];
  }

  // --------------------------------------------------------------- haptics

  /**
   * On the watch these map to WKInterfaceDevice haptics. In a browser only
   * Android exposes a vibrator, so this is best-effort by design: the visual
   * guard never depends on it.
   */
  function buzz(pattern) {
    if (navigator.vibrate) {
      try { navigator.vibrate(pattern); } catch (e) { /* blocked */ }
    }
  }

  const HAPTIC = {
    tick:    10,
    arm:     [12],
    warn:    [18],
    confirm: [30, 40, 60],
    cancel:  [8, 30, 8],
    fail:    [40, 60, 40],
  };

  // -------------------------------------------------------------- the watch

  class WatchUI {
    /**
     * @param {HTMLElement} root  the .watch element holding one cloned template
     * @param {object} opts       { live, label, onLog }
     */
    constructor(root, opts) {
      const o = opts || {};
      this.root = root;
      this.live = o.live !== false;
      this.onLog = o.onLog || function () {};

      this.q = (sel) => root.querySelector(sel);
      this.qa = (sel) => Array.prototype.slice.call(root.querySelectorAll(sel));

      this.screen = this.q('.screen');
      this.pages = this.q('.pages');
      this.dots = this.q('.dots');
      this.crown = this.q('.crown');
      this.clock = this.q('.js-clock');
      this.statusDot = this.q('.js-dot');
      this.volBadge = this.q('.js-vol-badge');
      this.volTrack = this.q('.js-vol-track');
      this.volFill = this.q('.js-vol-fill');
      this.volPct = this.q('.js-vol-pct');
      this.orbStage = this.q('.orb-stage');
      this.orbCaption = this.q('.js-orb-caption');
      this.powerWrap = this.q('.js-power');
      this.tiles = this.q('.js-tiles');
      this.lastRun = this.q('.js-last-run');
      this.flash = this.q('.screen-flash');
      this.pageName = this.q('.js-page-name');

      this.orb = new global.Orb(this.q('.orb-canvas'));
      this.orb.start();

      this.volume = 50;
      this.dragging = false;
      this.volumePost = null;
      this.stateTimer = null;

      this.bindClock();
      this.bindVolume();
      this.bindOrb();
      this.bindPages();

      this.paintVolume(this.volume);
      this.syncDots();
    }

    log(msg, kind) {
      this.onLog((this.live ? '' : '[הדגמה] ') + msg, kind);
    }

    // ------------------------------------------------------------ chrome

    bindClock() {
      const tick = () => {
        const d = new Date();
        this.clock.textContent =
          String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
      };
      tick();
      this.clockTimer = setInterval(tick, 15000);
    }

    setState(name, caption) {
      this.screen.className = 'screen state-' + name;
      this.orb.setState(name);
      if (caption) {
        this.orbCaption.textContent = caption;
        this.orbCaption.classList.add('show');
      } else {
        this.orbCaption.classList.remove('show');
      }
      clearTimeout(this.stateTimer);
      if (name === 'success' || name === 'error') {
        this.stateTimer = setTimeout(() => this.setState('idle'), 1900);
      }
    }

    // ------------------------------------------------------------ volume

    paintVolume(v) {
      this.volume = Math.max(0, Math.min(100, Math.round(v)));
      this.volFill.style.width = this.volume + '%';
      this.volPct.textContent = this.volume + '%';
      this.volBadge.textContent = this.volume + '%';
    }

    pushVolume(v) {
      if (!this.live) return;
      clearTimeout(this.volumePost);
      this.volumePost = setTimeout(() => {
        fetch('/api/volume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ volume: v }),
        })
          .then((r) => r.json())
          .then((d) => this.log('volume → ' + d.volume + '%', 'ok'))
          .catch((e) => this.log('volume failed: ' + e.message, 'err'));
      }, 45);
    }

    bindVolume() {
      const fromPointer = (e) => {
        const rect = this.volTrack.getBoundingClientRect();
        return Math.round(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)) * 100);
      };

      this.volTrack.addEventListener('pointerdown', (e) => {
        this.dragging = true;
        const v = fromPointer(e);
        this.paintVolume(v);
        this.pushVolume(v);
        buzz(HAPTIC.tick);
        // Capture keeps tracking outside the track; it is an enhancement, so a
        // failure here must not abort the update above.
        try { this.volTrack.setPointerCapture(e.pointerId); } catch (err) { /* synthetic */ }
      });

      this.volTrack.addEventListener('pointermove', (e) => {
        if (!this.dragging) return;
        const v = fromPointer(e);
        this.paintVolume(v);
        this.pushVolume(v);
      });

      ['pointerup', 'pointercancel'].forEach((ev) =>
        this.volTrack.addEventListener(ev, () => { this.dragging = false; }));

      this.screen.addEventListener('wheel', (e) => {
        if (this.currentPage() !== 0) return;
        e.preventDefault();
        this.paintVolume(this.volume + (e.deltaY < 0 ? 2 : -2));
        this.pushVolume(this.volume);
        this.crown.classList.remove('spin');
        void this.crown.offsetWidth;
        this.crown.classList.add('spin');
      }, { passive: false });
    }

    // ------------------------------------------------------------- voice

    bindOrb() {
      this.orbStage.addEventListener('click', () => {
        const Rec = global.SpeechRecognition || global.webkitSpeechRecognition;
        if (!Rec) {
          const typed = prompt('דבר אל השעון:', 'תנמיך ב-30 אחוז');
          if (typed) this.runCommand(typed);
          return;
        }
        const rec = new Rec();
        rec.lang = 'he-IL';
        rec.interimResults = false;
        this.setState('listening', 'מקשיב…');
        buzz(HAPTIC.tick);
        rec.onresult = (ev) => this.runCommand(ev.results[0][0].transcript);
        rec.onerror = () => this.setState('error', 'לא שמעתי');
        rec.onend = () => {
          if (this.screen.classList.contains('state-listening')) this.setState('idle');
        };
        rec.start();
      });
    }

    runCommand(text) {
      this.setState('thinking', 'חושב…');
      this.log('command: "' + text + '"');

      if (!this.live) {
        setTimeout(() => this.setState('success', 'הדגמה'), 700);
        return;
      }

      fetch('/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text }),
      })
        .then((r) => r.json())
        .then((d) => {
          if (d.status === 'success') {
            this.setState('success', d.feedback);
            buzz(HAPTIC.confirm);
            this.log(d.feedback, 'ok');
            if (d.details && typeof d.details.new_volume === 'number') {
              this.paintVolume(d.details.new_volume);
            }
          } else {
            this.setState('error', 'לא הבנתי');
            buzz(HAPTIC.fail);
            this.log(d.feedback, 'err');
          }
        })
        .catch((e) => {
          this.setState('error', 'אין קשר');
          this.log('command failed: ' + e.message, 'err');
        });
    }

    // ------------------------------------------------------------- power

    renderPower(actions) {
      this.powerWrap.innerHTML = '';

      actions.forEach((a, index) => {
        const tile = document.createElement('button');
        tile.className = 'ptile' + (a.destructive ? ' guarded' : '');
        tile.dataset.action = a.action;
        tile.style.setProperty('--accent', POWER_ACCENTS[a.action] || '64,200,224');
        tile.style.setProperty('--i', index);

        const hold = Number(a.hold_seconds) || 0;
        tile.dataset.hold = hold;

        tile.innerHTML =
          '<span class="ptile-fill"></span>' +
          (hold > 0 ? this.ringMarkup() : '') +
          '<span class="ptile-glyph">' + icon(POWER_ICONS[a.action] || 'bolt', 19) + '</span>' +
          '<span class="ptile-label">' + a.label + '</span>' +
          (hold > 0 ? '<span class="ptile-count"></span>' : '');

        if (hold > 0) {
          this.attachHold(tile, hold, () => this.firePower(a, tile));
        } else {
          tile.addEventListener('click', () => this.firePower(a, tile));
        }
        this.powerWrap.appendChild(tile);
      });
    }

    ringMarkup() {
      // The geometry is measured from the tile at runtime, because a fixed
      // circle in a rounded rectangle is letterboxed by preserveAspectRatio:
      // it leaves gaps at the sides and clips at the bottom.
      return '<svg class="hold-ring" preserveAspectRatio="none">' +
        '<path class="hold-ring-track"/>' +
        '<path class="hold-ring-val"/>' +
        '</svg>';
    }

    /**
     * Trace the tile's rounded rectangle exactly, starting at top centre and
     * running clockwise, and return the perimeter so the dash maths matches.
     */
    fitHoldRing(tile) {
      const svg = tile.querySelector('.hold-ring');
      if (!svg) return 0;

      const w = tile.offsetWidth;
      const h = tile.offsetHeight;
      if (!w || !h) return 0;

      const stroke = 3;
      const pad = stroke / 2 + 1;
      const rw = w - pad * 2;
      const rh = h - pad * 2;

      const corner = parseFloat(getComputedStyle(tile).borderTopLeftRadius) || 0;
      const r = Math.max(0, Math.min(corner - pad, rw / 2, rh / 2));

      const x = pad;
      const y = pad;
      const cx = x + rw / 2;

      const d = [
        'M', cx, y,
        'H', x + rw - r,
        'A', r, r, 0, 0, 1, x + rw, y + r,
        'V', y + rh - r,
        'A', r, r, 0, 0, 1, x + rw - r, y + rh,
        'H', x + r,
        'A', r, r, 0, 0, 1, x, y + rh - r,
        'V', y + r,
        'A', r, r, 0, 0, 1, x + r, y,
        'Z',
      ].join(' ');

      svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
      svg.querySelector('.hold-ring-track').setAttribute('d', d);
      svg.querySelector('.hold-ring-val').setAttribute('d', d);

      return 2 * (rw - 2 * r) + 2 * (rh - 2 * r) + 2 * Math.PI * r;
    }

    /**
     * Press-and-hold guard.
     *
     * A ring closes around the tile, the accent floods up from the base, a
     * countdown reads out the remaining seconds, and the haptic pulse quickens
     * as it approaches. Releasing early unwinds all of it — the cancel is as
     * legible as the commit.
     */
    attachHold(tile, seconds, onComplete) {
      const ring = tile.querySelector('.hold-ring-val');
      const fill = tile.querySelector('.ptile-fill');
      const count = tile.querySelector('.ptile-count');

      let perimeter = 0;
      let raf = null;
      let startedAt = 0;
      let lastBuzz = 0;
      let active = false;

      const remeasure = () => {
        perimeter = this.fitHoldRing(tile);
        ring.style.strokeDasharray = perimeter.toFixed(2);
        if (!active) ring.style.strokeDashoffset = perimeter.toFixed(2);
      };

      remeasure();
      // The tile is laid out by a grid inside a flex column, so its size is
      // only final after layout settles — and changes again if the page does.
      requestAnimationFrame(remeasure);
      if (typeof ResizeObserver === 'function') {
        new ResizeObserver(remeasure).observe(tile);
      }

      const paint = (t) => {
        ring.style.strokeDashoffset = (perimeter * (1 - t)).toFixed(2);
        fill.style.transform = 'scaleY(' + t.toFixed(3) + ')';
      };

      const step = (now) => {
        if (!active) return;
        const t = Math.min(1, (now - startedAt) / (seconds * 1000));
        paint(t);

        const remaining = Math.ceil(seconds * (1 - t));
        count.textContent = remaining > 0 ? remaining : '';

        // The pulse tightens from ~3/s to ~12/s as the commit approaches.
        const interval = 320 - t * 240;
        if (now - lastBuzz > interval) {
          buzz(HAPTIC.warn);
          lastBuzz = now;
        }

        if (t >= 1) {
          active = false;
          tile.classList.remove('holding');
          tile.classList.add('committed');
          count.textContent = '';
          buzz(HAPTIC.confirm);
          // The ring stays closed through the confirmation flash — that snap
          // shut is the payoff of the gesture. It rewinds afterwards, while
          // hidden, so the next press never starts on a full ring.
          setTimeout(() => {
            tile.classList.remove('committed');
            ring.style.strokeDashoffset = perimeter.toFixed(2);
            fill.style.transform = 'scaleY(0)';
          }, 700);
          onComplete();
          return;
        }
        raf = requestAnimationFrame(step);
      };

      const start = (e) => {
        if (active) return;
        e.preventDefault();
        active = true;
        startedAt = performance.now();
        lastBuzz = 0;
        tile.classList.add('holding');
        buzz(HAPTIC.arm);
        raf = requestAnimationFrame(step);
      };

      const cancel = () => {
        if (!active) return;
        active = false;
        cancelAnimationFrame(raf);
        tile.classList.remove('holding');
        tile.classList.add('unwinding');
        count.textContent = '';
        ring.style.strokeDashoffset = perimeter.toFixed(2);
        fill.style.transform = 'scaleY(0)';
        buzz(HAPTIC.cancel);
        setTimeout(() => tile.classList.remove('unwinding'), 320);
      };

      tile.addEventListener('pointerdown', start);
      ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) =>
        tile.addEventListener(ev, cancel));
      // A guarded tile must never fire from a plain click.
      tile.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); });
    }

    firePower(a, tile) {
      if (!this.live) {
        this.log(a.label + ' — לא נשלח', 'ok');
        this.announce('✓ ' + a.label + ' (הדגמה)', true);
        return;
      }

      this.log('power: ' + a.action + ' …');
      fetch('/api/power', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: a.action }),
      })
        .then((r) => {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(() => this.log(a.label + ' נשלח', 'ok'))
        .catch((e) => this.log('power failed: ' + e.message, 'err'));
    }

    // ------------------------------------------------------------- stats

    paintRing(el, radius, pct) {
      const c = 2 * Math.PI * radius;
      el.setAttribute('stroke-dasharray', c.toFixed(2));
      el.setAttribute('stroke-dashoffset', (c * (1 - pct / 100)).toFixed(2));
    }

    renderStats(s) {
      this.paintRing(this.q('.js-ring-cpu'), 50, s.cpu);
      this.paintRing(this.q('.js-ring-mem'), 37, s.memory);
      this.paintRing(this.q('.js-ring-disk'), 24, s.disk);
      this.q('.js-num-cpu').textContent = s.cpu + '%';
      this.q('.js-num-mem').textContent = s.memory + '%';
      this.q('.js-num-disk').textContent = s.disk + '%';
      this.q('.js-note-mem').textContent = s.memory_used_gb + '/' + s.memory_total_gb + 'GB';
      this.q('.js-note-disk').textContent = s.disk_free_gb + 'GB free';
    }

    // ----------------------------------------------------------- actions

    announce(text, hot) {
      this.lastRun.textContent = text;
      this.lastRun.classList.toggle('hot', !!hot);
    }

    effects() {
      return {
        'screenshot': () => {
          this.flash.classList.remove('fire');
          void this.flash.offsetWidth;
          this.flash.classList.add('fire');
        },
        'minimize-all': () => {
          this.tiles.classList.remove('collapsing');
          void this.tiles.offsetWidth;
          this.tiles.classList.add('collapsing');
          setTimeout(() => this.tiles.classList.remove('collapsing'), 900);
        },
      };
    }

    renderActions(list) {
      this.tiles.innerHTML = '';
      this.actionTiles = new Map();
      if (!list.length) {
        this.tiles.innerHTML =
          '<div class="empty" style="grid-column: 1 / -1">אין כפתורים.<br>ערוך את actions.json.</div>';
        return;
      }

      list.forEach((a, index) => {
        const tile = document.createElement('button');
        tile.className = 'atile';
        tile.dataset.action = a.id;
        tile.style.setProperty('--accent', accentFor(a.id));
        tile.style.setProperty('--i', index);
        tile.innerHTML =
          '<span class="atile-ripple"></span>' +
          (a.process ? '<span class="atile-live"></span>' : '') +
          '<span class="atile-glyph">' + icon(a.icon, 20) + '</span>' +
          '<span class="atile-check">' + CHECK_SVG + '</span>' +
          '<span class="atile-cap">' + a.label + '</span>';

        tile.addEventListener('pointerdown', (e) => {
          const box = tile.getBoundingClientRect();
          tile.style.setProperty('--rx', (e.clientX - box.left) + 'px');
          tile.style.setProperty('--ry', (e.clientY - box.top) + 'px');
          tile.classList.remove('rippling');
          void tile.offsetWidth;
          tile.classList.add('rippling');
          buzz(HAPTIC.tick);
        });

        tile.addEventListener('click', () => this.runAction(a, tile));
        this.actionTiles.set(a.id, tile);
        this.tiles.appendChild(tile);
      });
    }

    /** Light up the tiles whose app is already open. */
    setActionStatuses(statuses) {
      if (!this.actionTiles) return;
      this.actionTiles.forEach((tile, id) => {
        const st = statuses[id];
        tile.classList.toggle('live', !!(st && st.running));
      });
    }

    runAction(a, tile) {
      // Raising a window that was already open is a different event from
      // starting the app, so it gets its own, quieter confirmation.
      const raised = () => {
        tile.classList.remove('raised');
        void tile.offsetWidth;
        tile.classList.add('raised');
        buzz(HAPTIC.tick);
        setTimeout(() => tile.classList.remove('raised'), 800);
        this.announce('↑ ' + a.label + ' הובא לחזית', true);
        this.log(a.label + ' הובא לחזית', 'ok');
      };

      const launched = () => {
        const effect = this.effects()[a.id];
        if (effect) effect();
        tile.classList.add('done');
        buzz(HAPTIC.confirm);
        setTimeout(() => tile.classList.remove('done'), 1100);
        this.announce('✓ ' + a.label, true);
        this.log(a.label + ' הופעל', 'ok');
      };

      this.announce('מריץ ' + a.label + '…');

      if (!this.live) {
        // Mirror what the real machine would do, so the demo reads the same.
        const wouldFocus = tile.classList.contains('live');
        setTimeout(wouldFocus ? raised : launched, 260);
        return;
      }

      fetch('/api/actions/' + encodeURIComponent(a.id), { method: 'POST' })
        .then((r) => {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then((d) => {
          if (d.details && d.details.status === 'focused') raised();
          else launched();
        })
        .catch((e) => {
          tile.classList.remove('failed');
          void tile.offsetWidth;
          tile.classList.add('failed');
          buzz(HAPTIC.fail);
          setTimeout(() => tile.classList.remove('failed'), 500);
          this.announce('✕ ' + a.label + ' נכשל');
          this.log(a.label + ' failed: ' + e.message, 'err');
        });
    }

    // ------------------------------------------------------------- pages

    currentPage() {
      return Math.round(this.pages.scrollLeft / this.pages.clientWidth);
    }

    goToPage(i) {
      const clamped = Math.max(0, Math.min(3, i));
      this.pages.scrollTo({ left: clamped * this.pages.clientWidth, behavior: 'smooth' });
    }

    syncDots() {
      const i = this.currentPage();
      Array.prototype.forEach.call(this.dots.children, (d, n) => d.classList.toggle('on', n === i));
      if (this.pageName) this.pageName.textContent = PAGE_NAMES[i] || '';
    }

    bindPages() {
      let queued = false;
      this.pages.addEventListener('scroll', () => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => { queued = false; this.syncDots(); });
      });

      const prev = this.q('.js-prev');
      const next = this.q('.js-next');
      if (prev) prev.addEventListener('click', () => this.goToPage(this.currentPage() - 1));
      if (next) next.addEventListener('click', () => this.goToPage(this.currentPage() + 1));

      // Drag to swipe: the scrollbar is hidden to keep the watch looking like a
      // watch, so a pointer drag is the only stand-in for a real swipe.
      let startX = 0, startLeft = 0, active = false, moved = false;

      this.pages.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        if (e.target.closest && e.target.closest('.js-vol-track, button')) return;
        active = true;
        moved = false;
        startX = e.clientX;
        startLeft = this.pages.scrollLeft;
        this.pages.classList.add('dragging');
        try { this.pages.setPointerCapture(e.pointerId); } catch (err) { /* synthetic */ }
      });

      this.pages.addEventListener('pointermove', (e) => {
        if (!active) return;
        const dx = e.clientX - startX;
        if (Math.abs(dx) > 4) moved = true;
        this.pages.scrollLeft = startLeft - dx;
      });

      const endDrag = () => {
        if (!active) return;
        active = false;
        this.pages.classList.remove('dragging');
        this.goToPage(Math.round(this.pages.scrollLeft / this.pages.clientWidth));
      };
      ['pointerup', 'pointercancel'].forEach((ev) => this.pages.addEventListener(ev, endDrag));

      this.pages.addEventListener('click', (e) => {
        if (!moved) return;
        moved = false;
        e.stopPropagation();
        e.preventDefault();
      }, true);
    }

    // ------------------------------------------------------------- status

    setConnected(on) {
      this.statusDot.classList.toggle('live', !!on);
    }

    destroy() {
      clearInterval(this.clockTimer);
      this.orb.destroy();
    }
  }

  global.WatchUI = WatchUI;
  global.WATCH_ICON = icon;
})(window);

/**
 * A sphere of light particles.
 *
 * Points are spread evenly over a sphere with a Fibonacci lattice, displaced
 * by a travelling wave so the surface breathes instead of sitting rigid, then
 * spun and projected with perspective. Depth drives size, brightness and
 * colour, so the sphere reads as a volume rather than a flat disc — no single
 * particle is doing the work, the distribution is.
 *
 * Everything composites additively, which is what makes overlapping points
 * bloom into light instead of stacking into mud.
 *
 * The public surface is small on purpose: setState, setLevel, start, stop.
 */

(function (global) {
  'use strict';

  const TAU = Math.PI * 2;
  const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

  // ---------------------------------------------------------------- palettes

  const PALETTES = {
    idle: {
      deep: '#0B1541',      // particles at the back of the sphere
      mid: '#3B5BDB',
      bright: '#8FB4FF',    // particles at the front
      core: '#2748C8',      // the glow behind the shell
      speed: 0.30,
      wobble: 0.055,
      density: 1,
    },
    listening: {
      deep: '#04314F',
      mid: '#0A84FF',
      bright: '#A8F2FF',
      core: '#0B6FB8',
      speed: 0.62,
      wobble: 0.13,
      density: 1.12,
    },
    thinking: {
      deep: '#250A45',
      mid: '#8B3BEA',
      bright: '#E7BCFF',
      core: '#6A24C0',
      speed: 1.25,
      wobble: 0.10,
      density: 1.05,
    },
    success: {
      deep: '#04301F',
      mid: '#12A96F',
      bright: '#A6FFCB',
      core: '#0B7D52',
      speed: 0.45,
      wobble: 0.075,
      density: 1.08,
    },
    error: {
      deep: '#460B05',
      mid: '#E0392A',
      bright: '#FFB9AC',
      core: '#A32115',
      speed: 0.55,
      wobble: 0.16,
      density: 1,
    },
  };

  const RAMP_STEPS = 10;

  // ------------------------------------------------------------ colour utils

  function parseHex(hex) {
    const h = hex.replace('#', '');
    return [
      parseInt(h.slice(0, 2), 16),
      parseInt(h.slice(2, 4), 16),
      parseInt(h.slice(4, 6), 16),
    ];
  }

  function mix(a, b, t) {
    return [
      a[0] + (b[0] - a[0]) * t,
      a[1] + (b[1] - a[1]) * t,
      a[2] + (b[2] - a[2]) * t,
    ];
  }

  function rgba(c, alpha) {
    return 'rgba(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ',' + alpha + ')';
  }

  function toPalette(name) {
    const p = PALETTES[name] || PALETTES.idle;
    return {
      deep: parseHex(p.deep),
      mid: parseHex(p.mid),
      bright: parseHex(p.bright),
      core: parseHex(p.core),
      speed: p.speed,
      wobble: p.wobble,
      density: p.density,
    };
  }

  function blendPalettes(from, to, t) {
    return {
      deep: mix(from.deep, to.deep, t),
      mid: mix(from.mid, to.mid, t),
      bright: mix(from.bright, to.bright, t),
      core: mix(from.core, to.core, t),
      speed: from.speed + (to.speed - from.speed) * t,
      wobble: from.wobble + (to.wobble - from.wobble) * t,
      density: from.density + (to.density - from.density) * t,
    };
  }

  /** Sample the deep → mid → bright ramp at 0..1. */
  function rampAt(palette, t) {
    return t < 0.5
      ? mix(palette.deep, palette.mid, t * 2)
      : mix(palette.mid, palette.bright, (t - 0.5) * 2);
  }

  // ----------------------------------------------------------- dot sprites

  /**
   * One soft dot, pre-rendered once per colour step.
   *
   * Building a radial gradient per particle per frame would cost thousands of
   * gradient allocations a second; drawing a cached sprite costs a blit.
   */
  function buildDot(px, colour) {
    const c = document.createElement('canvas');
    const size = Math.max(4, Math.ceil(px));
    c.width = size;
    c.height = size;
    const g = c.getContext('2d');
    const r = size / 2;

    const grad = g.createRadialGradient(r, r, 0, r, r, r);
    grad.addColorStop(0, rgba(colour, 1));
    grad.addColorStop(0.35, rgba(colour, 0.55));
    grad.addColorStop(1, rgba(colour, 0));
    g.fillStyle = grad;
    g.beginPath();
    g.arc(r, r, r, 0, TAU);
    g.fill();
    return c;
  }

  // ------------------------------------------------------------------- orb

  class Orb {
    constructor(canvas, options) {
      const opts = options || {};
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.count = opts.count || 1200;

      this.state = 'idle';
      this.fromPalette = toPalette('idle');
      this.toPalette = this.fromPalette;
      this.blend = 1;
      this.blendStart = 0;
      this.blendMs = 750;

      this.level = 0;
      this.levelSmoothed = 0;

      this.yaw = 0;
      this.pitch = -0.28;
      this.time = 0;

      this.rampCache = new Map();
      this.rampKey = null;
      this.ramp = null;

      this.running = false;
      this.lastFrame = 0;

      this.buildLattice();
      this.resize();
      this._onResize = () => this.resize();
      global.addEventListener('resize', this._onResize);
    }

    /**
     * Fibonacci lattice: the golden angle keeps successive points from ever
     * lining up, which is why the sphere looks evenly covered with no seams or
     * clumping at the poles.
     */
    buildLattice() {
      const n = this.count;
      this.points = new Float32Array(n * 3);
      this.seed = new Float32Array(n);

      for (let i = 0; i < n; i++) {
        const y = 1 - (i / (n - 1)) * 2;
        const r = Math.sqrt(Math.max(0, 1 - y * y));
        const theta = i * GOLDEN_ANGLE;
        this.points[i * 3] = Math.cos(theta) * r;
        this.points[i * 3 + 1] = y;
        this.points[i * 3 + 2] = Math.sin(theta) * r;
        this.seed[i] = Math.random();
      }
    }

    resize() {
      const dpr = Math.min(global.devicePixelRatio || 1, 2);
      // offsetWidth is the layout size. getBoundingClientRect reports the
      // *transformed* size, and the breathing scale on an ancestor makes that
      // wobble, so the buffer resolution would depend on when it measured.
      const cssSize = Math.max(
        1,
        Math.min(this.canvas.offsetWidth, this.canvas.offsetHeight) || 118,
      );

      this.size = Math.round(cssSize * dpr * Orb.SUPERSAMPLE);
      this.canvas.width = this.size;
      this.canvas.height = this.size;
      this.dpr = dpr;
      this.radius = this.size * 0.40;
      this.dotPx = Math.max(6, this.size * 0.055);

      this.rampCache.clear();
      this.rampKey = null;
    }

    setState(name) {
      if (!PALETTES[name] || name === this.state) return;
      this.fromPalette = this.currentPalette();
      this.toPalette = toPalette(name);
      this.blend = 0;
      this.blendStart = performance.now();
      this.state = name;
    }

    currentPalette() {
      if (this.blend >= 1) return this.toPalette;
      return blendPalettes(this.fromPalette, this.toPalette, this.blend);
    }

    /** Feed a 0..1 audio level; without one a gentle synthetic pulse is used. */
    setLevel(v) {
      this.level = Math.max(0, Math.min(1, v));
    }

    /** Ten tinted dots spanning the palette, rebuilt only when the hue moves. */
    rampFor(palette) {
      const key =
        (palette.deep[0] | 0) + ',' + (palette.mid[1] | 0) + ',' + (palette.bright[2] | 0);
      if (key === this.rampKey && this.ramp) return this.ramp;

      let ramp = this.rampCache.get(key);
      if (!ramp) {
        ramp = [];
        for (let i = 0; i < RAMP_STEPS; i++) {
          ramp.push(buildDot(this.dotPx, rampAt(palette, i / (RAMP_STEPS - 1))));
        }
        this.rampCache.set(key, ramp);
        if (this.rampCache.size > 40) {
          this.rampCache.delete(this.rampCache.keys().next().value);
        }
      }
      this.rampKey = key;
      this.ramp = ramp;
      return ramp;
    }

    start() {
      if (this.running) return;
      this.running = true;
      this.lastFrame = performance.now();
      const loop = (now) => {
        if (!this.running) return;
        this.frame(now);
        this.raf = requestAnimationFrame(loop);
      };
      this.raf = requestAnimationFrame(loop);
    }

    stop() {
      this.running = false;
      if (this.raf) cancelAnimationFrame(this.raf);
    }

    destroy() {
      this.stop();
      global.removeEventListener('resize', this._onResize);
    }

    // ------------------------------------------------------------- rendering

    frame(now) {
      const dt = Math.min(0.05, (now - this.lastFrame) / 1000);
      this.lastFrame = now;

      if (this.blend < 1) this.blend = Math.min(1, (now - this.blendStart) / this.blendMs);
      const p = this.currentPalette();

      const synthetic = this.state === 'listening'
        ? 0.4 + 0.6 * Math.abs(Math.sin(now / 250))
        : 0.1 + 0.08 * Math.sin(now / 1500);
      const target = this.level > 0 ? this.level : synthetic;
      this.levelSmoothed += (target - this.levelSmoothed) * Math.min(1, dt * 8);

      this.time += dt;
      this.yaw += dt * p.speed * (1 + this.levelSmoothed * 0.6);
      this.pitch = -0.28 + Math.sin(this.time * 0.21) * 0.16;

      const ctx = this.ctx;
      const S = this.size;
      const R = S / 2;

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, S, S);

      ctx.save();
      ctx.beginPath();
      ctx.arc(R, R, R, 0, TAU);
      ctx.clip();

      this.drawCore(p, S, R);
      this.drawShell(p, S, R);
      this.drawRim(p, S, R);

      ctx.restore();
    }

    /** A soft glow inside the shell so the sphere feels lit from within. */
    drawCore(p, S, R) {
      const ctx = this.ctx;
      const pulse = 0.82 + this.levelSmoothed * 0.3;
      const grad = ctx.createRadialGradient(
        R, R * 0.92, 0,
        R, R * 0.92, this.radius * 1.15 * pulse,
      );
      grad.addColorStop(0, rgba(p.core, 0.85));
      grad.addColorStop(0.45, rgba(p.core, 0.32));
      grad.addColorStop(1, rgba(p.deep, 0));

      ctx.globalCompositeOperation = 'lighter';
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, S, S);
      ctx.globalCompositeOperation = 'source-over';
    }

    drawShell(p, S, R) {
      const ctx = this.ctx;
      const ramp = this.rampFor(p);
      const pts = this.points;
      const seed = this.seed;

      const cosY = Math.cos(this.yaw);
      const sinY = Math.sin(this.yaw);
      const cosX = Math.cos(this.pitch);
      const sinX = Math.sin(this.pitch);

      const camera = 2.9;                     // in sphere radii
      const amp = p.wobble + this.levelSmoothed * 0.09;
      const t = this.time;
      const baseDot = this.dotPx;

      // Additive so overlapping particles bloom rather than occlude. That also
      // means draw order is irrelevant, so there is no depth sort per frame.
      ctx.globalCompositeOperation = 'lighter';

      for (let i = 0; i < this.count; i++) {
        const x0 = pts[i * 3];
        const y0 = pts[i * 3 + 1];
        const z0 = pts[i * 3 + 2];

        // A travelling wave over the surface — cheap, and reads as organic
        // because the three axes beat against each other at different rates.
        const wave =
          Math.sin(x0 * 2.1 + t * 0.9) *
          Math.sin(y0 * 1.7 - t * 0.7) *
          Math.sin(z0 * 2.3 + t * 1.1);
        const rr = 1 + amp * wave;

        const x = x0 * rr;
        const y = y0 * rr;
        const z = z0 * rr;

        // yaw about Y, then pitch about X
        const xz = x * cosY + z * sinY;
        const zz = z * cosY - x * sinY;
        const yy = y * cosX - zz * sinX;
        const zf = y * sinX + zz * cosX;

        const depth = (zf + 1) * 0.5;              // 0 back, 1 front
        const proj = camera / (camera - zf);

        const px = R + xz * this.radius * proj;
        const py = R + yy * this.radius * proj;

        // Front particles are larger, brighter and warmer up the ramp.
        const twinkle = 0.85 + 0.15 * Math.sin(t * 2.2 + seed[i] * TAU);
        const size = baseDot * (0.34 + depth * 0.95) * proj * twinkle;
        const alpha = (0.1 + Math.pow(depth, 1.5) * 0.9) * (0.7 + this.levelSmoothed * 0.4);

        let shade = (depth * 0.78 + (1 - (yy + 1) * 0.5) * 0.22) * (RAMP_STEPS - 1);
        shade = shade < 0 ? 0 : shade > RAMP_STEPS - 1 ? RAMP_STEPS - 1 : shade;
        const dot = ramp[shade | 0];

        ctx.globalAlpha = alpha > 1 ? 1 : alpha;
        ctx.drawImage(dot, px - size / 2, py - size / 2, size, size);
      }

      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';
    }

    /** A thin lit edge, brightest along the bottom, to seat the sphere. */
    drawRim(p, S, R) {
      const ctx = this.ctx;
      const grad = ctx.createLinearGradient(0, S, 0, 0);
      grad.addColorStop(0, rgba(p.bright, 0.5));
      grad.addColorStop(0.55, rgba(p.bright, 0.1));
      grad.addColorStop(1, rgba(p.bright, 0));

      ctx.globalCompositeOperation = 'lighter';
      ctx.save();
      ctx.filter = 'blur(' + S * 0.045 + 'px)';
      ctx.strokeStyle = grad;
      ctx.lineWidth = S * 0.05;
      ctx.beginPath();
      ctx.arc(R, R, R * 0.93, 0, TAU);
      ctx.stroke();
      ctx.restore();
      ctx.globalCompositeOperation = 'source-over';
    }
  }

  /** Matches the peak of the CSS breathing scale so the orb never softens. */
  Orb.SUPERSAMPLE = 1.06;

  global.Orb = Orb;
  global.ORB_PALETTES = PALETTES;
})(window);

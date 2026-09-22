/**
 * Minimal Chrome DevTools Protocol client — no dependencies.
 *
 * Node 22 ships a global WebSocket, so driving a real browser needs nothing
 * from npm. Used by the dashboard UI tests to evaluate JavaScript against the
 * live page and read the result back.
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CHROME_CANDIDATES = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
];

export function findChrome() {
  const found = CHROME_CANDIDATES.find((p) => existsSync(p));
  if (!found) throw new Error('no Chrome or Edge binary found');
  return found;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForDebugger(port, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (res.ok) return (await res.json()).webSocketDebuggerUrl;
    } catch {
      /* not listening yet */
    }
    await sleep(120);
  }
  throw new Error('browser debugger did not come up in time');
}

export class Browser {
  static async launch({ port = 9222 + Math.floor(Math.random() * 900) } = {}) {
    const profile = mkdtempSync(join(tmpdir(), 'cdp-profile-'));
    const proc = spawn(findChrome(), [
      '--headless=new',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      `--user-data-dir=${profile}`,
      `--remote-debugging-port=${port}`,
      'about:blank',
    ], { stdio: 'ignore' });

    const wsUrl = await waitForDebugger(port);
    return new Browser(proc, wsUrl, port);
  }

  constructor(proc, wsUrl, port) {
    this.proc = proc;
    this.wsUrl = wsUrl;
    this.port = port;
  }

  async newPage(url) {
    const res = await fetch(
      `http://127.0.0.1:${this.port}/json/new?${encodeURIComponent(url)}`,
      { method: 'PUT' },
    );
    const target = await res.json();
    const page = new Page(target.webSocketDebuggerUrl);
    await page.connect();
    return page;
  }

  close() {
    this.proc.kill();
  }
}

export class Page {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.nextId = 1;
    this.pending = new Map();
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.addEventListener('open', () => resolve());
      this.ws.addEventListener('error', (e) => reject(e));
      this.ws.addEventListener('message', (event) => {
        const msg = JSON.parse(event.data);
        const waiter = this.pending.get(msg.id);
        if (!waiter) return;
        this.pending.delete(msg.id);
        if (msg.error) waiter.reject(new Error(msg.error.message));
        else waiter.resolve(msg.result);
      });
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  /** Evaluate an expression in the page and return its JSON value. */
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression: `(() => { ${expression} })()`,
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.exceptionDetails) {
      throw new Error(
        'page threw: ' +
          (result.exceptionDetails.exception?.description ||
            result.exceptionDetails.text),
      );
    }
    return result.result.value;
  }

  /** Poll an expression until it returns truthy, or fail. */
  async waitFor(expression, { timeoutMs = 8000, label = expression } = {}) {
    const deadline = Date.now() + timeoutMs;
    let last;
    while (Date.now() < deadline) {
      last = await this.evaluate(`return (${expression});`);
      if (last) return last;
      await sleep(100);
    }
    throw new Error(`timed out waiting for: ${label} (last value: ${JSON.stringify(last)})`);
  }

  async close() {
    try { this.ws.close(); } catch { /* already gone */ }
  }
}

export { sleep };

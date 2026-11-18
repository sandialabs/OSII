'use strict';
const { EventEmitter } = require('node:events');
const { createInterface } = require('node:readline');

class RuntimeClient extends EventEmitter {
  constructor(child) {
    super();
    this.child = child;
    this.sequence = 0;
    this.pending = new Map();
    this.closed = false;
    this.ready = new Promise((resolve, reject) => {
      this.readyResolve = resolve;
      this.readyReject = reject;
    });
    this.ready.catch(() => {}); // The window may finish loading before its caller awaits readiness.
    this.readyTimer = setTimeout(() => this.fail(new Error('The bundled runtime did not start. Reinstall OSII or export diagnostics.')), 30_000);
    this.lines = createInterface({ input: child.stdout });
    this.lines.on('line', line => {
      if (line.length > 1024 * 1024) return this.fail(new Error('Invalid runtime response'));
      let message;
      try { message = JSON.parse(line); } catch { return; }
      if (message.event === 'supervisor_ready' && message.protocol === 1) {
        clearTimeout(this.readyTimer);
        this.readyResolve();
      } else if (message.event === 'runtime_failed') {
        this.emit('runtime-failed', String(message.error));
      } else if (Number.isSafeInteger(message.id) && this.pending.has(message.id)) {
        const request = this.pending.get(message.id);
        this.pending.delete(message.id);
        clearTimeout(request.timer);
        if (message.error) request.reject(new Error(String(message.error)));
        else request.resolve(message.result);
      }
    });
    child.on('error', error => this.fail(error));
    const stopped = code => {
      if (this.closed) return;
      this.closed = true;
      this.fail(new Error(`The OSII runtime stopped (exit ${code ?? 'unknown'}). Reopen OSII to recover queued work.`));
      this.emit('stopped', code);
    };
    child.on('exit', stopped);
    child.on('close', stopped); // A failed spawn emits close without an exit event.
    child.stdin.on('error', error => this.fail(error));
  }

  fail(error) {
    if (['ENOENT', 'EACCES', 'ENOEXEC'].includes(error.code)) {
      error = new Error('The OSII runtime is missing or blocked. Reinstall OSII and check application permissions.');
    }
    clearTimeout(this.readyTimer);
    this.readyReject(error);
    for (const request of this.pending.values()) {
      clearTimeout(request.timer);
      request.reject(error);
    }
    this.pending.clear();
  }

  async request(command, fields = {}) {
    await this.ready;
    if (this.closed) throw new Error('The OSII runtime has stopped. Reopen OSII.');
    return new Promise((resolve, reject) => {
      const id = ++this.sequence;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error('OSII did not finish this operation. Close and reopen the application; library data is preserved.'));
      }, 180_000);
      this.pending.set(id, { resolve, reject, timer });
      this.child.stdin.write(JSON.stringify({ ...fields, id, command }) + '\n');
    });
  }

  async shutdown() {
    if (this.closed) return;
    const exited = new Promise(resolve => this.once('stopped', resolve));
    this.child.stdin.end(JSON.stringify({ command: 'shutdown' }) + '\n');
    let timer;
    const timeout = new Promise(resolve => { timer = setTimeout(resolve, 20_000); });
    await Promise.race([exited, timeout]);
    clearTimeout(timer);
    if (!this.closed) {
      this.child.kill(); // Windows closes the supervisor's Job Object handle.
      await exited;
    }
    this.lines.close();
  }
}

function validRuntimeSession(value) {
  if (!value || typeof value.token !== 'string' || value.token.length < 32 || typeof value.url !== 'string') return false;
  try {
    const url = new URL(value.url);
    return url.protocol === 'http:' && url.hostname === '127.0.0.1' && Number(url.port) > 0 &&
      !url.username && !url.password && !url.search && !url.hash && url.pathname === '/';
  } catch { return false; }
}

module.exports = { RuntimeClient, validRuntimeSession };

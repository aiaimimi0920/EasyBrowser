#!/usr/bin/env node

const fs = require('node:fs');
const fsp = fs.promises;
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const readline = require('node:readline');
const { spawn } = require('node:child_process');

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const current = argv[i];
    if (!current.startsWith('--')) {
      continue;
    }
    const key = current.slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith('--')) {
      out[key] = next;
      i += 1;
      continue;
    }
    out[key] = 'true';
  }
  return out;
}

function nowIso() {
  return new Date().toISOString();
}

function nextId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function makeError({ category, code, message, retriable = false, cooldownCandidate = false, raw = undefined }) {
  const error = new Error(message);
  error.easybrowser = {
    category,
    code,
    message,
    retriable,
    cooldown_candidate: cooldownCandidate,
    raw,
  };
  return error;
}

const args = parseArgs(process.argv.slice(2));
const providerId = String(args.provider || '').trim();
const runtimeId = String(args['runtime-id'] || '').trim();
const explicitBrowserPath = String(process.env.EASYBROWSER_CHROME_PATH || '').trim();
const headlessEnv = String(process.env.EASYBROWSER_CHROME_HEADLESS || 'true').trim().toLowerCase();
const useHeadless = !['0', 'false', 'no'].includes(headlessEnv);

if (!providerId || !runtimeId) {
  console.error('chrome runtime requires --provider and --runtime-id');
  process.exit(1);
}

const browserCandidates = [
  explicitBrowserPath,
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
].filter(Boolean);

let browserPath = '';
let browserLabel = '';
for (const candidate of browserCandidates) {
  if (candidate && fs.existsSync(candidate)) {
    browserPath = candidate;
    browserLabel = path.basename(candidate).toLowerCase().includes('edge') ? 'edge' : 'chrome';
    break;
  }
}

if (!browserPath) {
  console.error('chrome runtime could not find a local Chrome/Edge executable');
  process.exit(1);
}

let browserProc = null;
let profileDir = '';
let devtoolsPort = 0;
let browserHealthy = false;
let recentFailures = 0;

function sendEnvelope(kind, action, payload, trace = {}) {
  const envelope = {
    id: nextId(action || kind),
    kind,
    action,
    timestamp: nowIso(),
    trace: {
      runtime_id: runtimeId,
      provider_id: providerId,
      ...trace,
    },
    payload,
  };
  process.stdout.write(`${JSON.stringify(envelope)}\n`);
}

function sendReady() {
  sendEnvelope('event', 'runtime_ready', {
    runtime_id: runtimeId,
    provider_id: providerId,
    pid: browserProc?.pid || process.pid,
    state: 'ready',
    started_at: nowIso(),
  });
}

function sendHeartbeat(healthy, notes = undefined) {
  browserHealthy = healthy;
  sendEnvelope('heartbeat', 'runtime_health', {
    runtime_id: runtimeId,
    provider_id: providerId,
    healthy,
    timestamp: nowIso(),
    signals: {
      recent_failures: recentFailures,
      cooldown_active: false,
    },
    notes,
  });
}

function sendCompletion(taskId, success, result, error) {
  sendEnvelope(
    'event',
    'task_completed',
    {
      runtime_id: runtimeId,
      task_id: taskId,
      success,
      result,
      error,
      finished_at: nowIso(),
    },
    { task_id: taskId },
  );
}

async function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = address && typeof address === 'object' ? address.port : 0;
      server.close((closeErr) => {
        if (closeErr) {
          reject(closeErr);
          return;
        }
        resolve(port);
      });
    });
  });
}

async function waitFor(condition, attempts = 40, delayMs = 250) {
  let lastError = null;
  for (let i = 0; i < attempts; i += 1) {
    try {
      return await condition();
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  throw lastError || new Error('condition not met');
}

async function requestDevtoolsJson(pathname, options = {}) {
  if (!devtoolsPort) {
    throw makeError({
      category: 'startup',
      code: 'devtools_port_missing',
      message: 'chrome devtools port is not initialized',
      retriable: true,
      cooldownCandidate: true,
    });
  }

  const method = options.method || 'GET';
  const url = `http://127.0.0.1:${devtoolsPort}${pathname}`;
  let response;
  try {
    response = await fetch(url, { method });
  } catch (error) {
    throw makeError({
      category: 'transport',
      code: 'devtools_transport_error',
      message: error instanceof Error ? error.message : 'chrome devtools transport error',
      retriable: true,
      cooldownCandidate: true,
      raw: { url, cause: String(error) },
    });
  }

  const text = await response.text();
  if (!response.ok) {
    throw makeError({
      category: 'provider',
      code: `devtools_http_${response.status}`,
      message: text || response.statusText || `chrome devtools request failed (${response.status})`,
      retriable: response.status >= 500,
      cooldownCandidate: response.status >= 500,
      raw: { url, status: response.status, body: text },
    });
  }

  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function normalizeError(error) {
  if (error && error.easybrowser) {
    return {
      category: error.easybrowser.category || 'unknown',
      code: error.easybrowser.code || 'unknown_error',
      message: error.easybrowser.message || 'unknown error',
      retriable: Boolean(error.easybrowser.retriable),
      cooldown_candidate: Boolean(error.easybrowser.cooldown_candidate),
      raw: error.easybrowser.raw || undefined,
    };
  }
  return {
    category: 'unknown',
    code: 'unknown_error',
    message: error instanceof Error ? error.message : String(error),
    retriable: false,
    cooldown_candidate: false,
  };
}

function buildAttachContract(targetId, pageUrl) {
  return {
    scope: 'page',
    transport: 'cdp',
    endpoint: `http://127.0.0.1:${devtoolsPort}`,
    browser_name: 'chromium',
    target_id: targetId || undefined,
    page_url: pageUrl || undefined,
  };
}

async function startBrowser() {
  profileDir = await fsp.mkdtemp(path.join(os.tmpdir(), 'easybrowser-chrome-'));
  devtoolsPort = await getFreePort();

  const args = [
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--remote-debugging-address=127.0.0.1',
    `--remote-debugging-port=${devtoolsPort}`,
    `--user-data-dir=${profileDir}`,
    'about:blank',
  ];
  if (useHeadless) {
    args.unshift('--headless=new');
  }

  browserProc = spawn(browserPath, args, {
    stdio: ['ignore', 'ignore', 'pipe'],
    windowsHide: true,
  });

  browserProc.stderr.on('data', (chunk) => {
    const message = chunk.toString().trim();
    if (message) {
      console.error(`chrome runtime browser stderr: ${message}`);
    }
  });

  browserProc.on('exit', (code, signal) => {
    browserHealthy = false;
    console.error(`chrome browser exited code=${code} signal=${signal}`);
  });

  await waitFor(async () => {
    const version = await requestDevtoolsJson('/json/version');
    if (!version || typeof version !== 'object') {
      throw new Error('chrome version response unavailable');
    }
    return version;
  }, 50, 250);
}

async function cleanup() {
  const proc = browserProc;
  browserProc = null;

  if (proc && proc.exitCode === null) {
    try {
      proc.kill();
    } catch {}
    try {
      await new Promise((resolve) => {
        const timer = setTimeout(resolve, 3000);
        proc.once('exit', () => {
          clearTimeout(timer);
          resolve();
        });
      });
    } catch {}
  }

  if (profileDir) {
    try {
      await fsp.rm(profileDir, { recursive: true, force: true });
    } catch {}
  }
}

function resolveTargetID(payload) {
  return String(payload?.resource_id || payload?.resourceId || payload?.target_id || payload?.targetId || payload?.id || '').trim();
}

async function executeAction(request) {
  const operation = request?.operation || {};
  const payload = operation.payload || {};
  const action = String(payload.action || operation.kind || '').trim().toLowerCase();
  const resourceKind = String(payload.resource_kind || payload.resourceKind || '').trim().toLowerCase();

  if (['open_resource', 'list_resources', 'get_resource', 'close_resource'].includes(action) && resourceKind && resourceKind !== 'page') {
    throw makeError({
      category: 'provider',
      code: 'unsupported_resource_kind',
      message: `chrome does not support resource_kind=${resourceKind} for action=${action}`,
      retriable: false,
      cooldownCandidate: false,
    });
  }

  switch (action) {
    case 'health':
    case 'get_version': {
      const response = await requestDevtoolsJson('/json/version');
      return {
        action,
        response,
        browser_path: browserPath,
        browser_kind: browserLabel,
        debug_port: devtoolsPort,
      };
    }
    case 'list_pages': {
      const targets = await requestDevtoolsJson('/json/list');
      const response = Array.isArray(targets) ? targets.filter((target) => target?.type === 'page') : targets;
      return {
        action,
        response,
        browser_path: browserPath,
        browser_kind: browserLabel,
        debug_port: devtoolsPort,
      };
    }
    case 'list_resources': {
      const targets = await requestDevtoolsJson('/json/list');
      const response = Array.isArray(targets) ? targets.filter((target) => target?.type === 'page') : targets;
      return {
        action,
        resource_kind: 'page',
        response,
        browser_path: browserPath,
        browser_kind: browserLabel,
        debug_port: devtoolsPort,
      };
    }
    case 'list_targets': {
      const response = await requestDevtoolsJson('/json/list');
      return {
        action,
        response,
        browser_path: browserPath,
        browser_kind: browserLabel,
        debug_port: devtoolsPort,
      };
    }
    case 'open_resource':
    case 'open_page':
    case 'open_url':
    case 'create_tab':
    case 'new_page': {
      const url = String(payload.url || payload.target_url || 'about:blank').trim() || 'about:blank';
      const response = await requestDevtoolsJson(`/json/new?${encodeURIComponent(url)}`, { method: 'PUT' });
      const targetId = response?.id || '';
      const pageUrl = response?.url || url;
      return {
        action,
        resource_kind: 'page',
        response,
        attach: buildAttachContract(targetId, pageUrl),
        browser_path: browserPath,
        browser_kind: browserLabel,
        debug_port: devtoolsPort,
      };
    }
    case 'get_resource': {
      const targetID = resolveTargetID(payload);
      if (!targetID) {
        throw makeError({
          category: 'provider',
          code: 'missing_target_id',
          message: 'get_resource requires resource_id or target_id',
          retriable: false,
          cooldownCandidate: false,
        });
      }
      const targets = await requestDevtoolsJson('/json/list');
      const response = Array.isArray(targets) ? targets.find((target) => target?.id === targetID) : null;
      if (!response) {
        throw makeError({
          category: 'provider',
          code: 'target_not_found',
          message: `target ${targetID} not found`,
          retriable: false,
          cooldownCandidate: false,
        });
      }
      return {
        action,
        resource_kind: 'page',
        target_id: targetID,
        response,
        attach: buildAttachContract(targetID, response?.url),
        browser_path: browserPath,
        browser_kind: browserLabel,
        debug_port: devtoolsPort,
      };
    }
    case 'activate_target': {
      const targetID = resolveTargetID(payload);
      if (!targetID) {
        throw makeError({
          category: 'provider',
          code: 'missing_target_id',
          message: 'activate_target requires target_id',
          retriable: false,
          cooldownCandidate: false,
        });
      }
      const response = await requestDevtoolsJson(`/json/activate/${encodeURIComponent(targetID)}`);
      return {
        action,
        target_id: targetID,
        response,
      };
    }
    case 'close_resource':
    case 'close_target': {
      const targetID = resolveTargetID(payload);
      if (!targetID) {
        throw makeError({
          category: 'provider',
          code: 'missing_target_id',
          message: `${action} requires resource_id or target_id`,
          retriable: false,
          cooldownCandidate: false,
        });
      }
      const response = await requestDevtoolsJson(`/json/close/${encodeURIComponent(targetID)}`);
      await waitFor(async () => {
        const targets = await requestDevtoolsJson('/json/list');
        if (Array.isArray(targets) && targets.some((target) => target.id === targetID)) {
          throw new Error('target still present');
        }
        return true;
      }, 25, 200);
      return {
        action,
        resource_kind: 'page',
        target_id: targetID,
        response,
      };
    }
    default:
      throw makeError({
        category: 'provider',
        code: 'unsupported_action',
        message: `unsupported chrome action: ${action || '<empty>'}`,
        retriable: false,
        cooldownCandidate: false,
        raw: {
          supported_actions: ['get_version', 'health', 'list_pages', 'list_targets', 'list_resources', 'get_resource', 'open_page', 'open_resource', 'open_url', 'create_tab', 'new_page', 'activate_target', 'close_target', 'close_resource'],
        },
      });
  }
}

async function handleExecuteTask(envelope) {
  const taskId = String(envelope?.trace?.task_id || envelope?.payload?.task_id || '').trim();
  const request = envelope?.payload?.request || {};

  try {
    const execution = await executeAction(request);
    recentFailures = 0;
    sendHeartbeat(true, {
      browser_kind: browserLabel,
      browser_path: browserPath,
      debug_port: devtoolsPort,
    });
    sendCompletion(taskId, true, {
      provider_id: providerId,
      runtime_id: runtimeId,
      browser_kind: browserLabel,
      browser_path: browserPath,
      debug_port: devtoolsPort,
      ...execution,
    }, null);
  } catch (error) {
    recentFailures += 1;
    const normalized = normalizeError(error);
    sendHeartbeat(false, {
      browser_kind: browserLabel,
      browser_path: browserPath,
      debug_port: devtoolsPort,
      last_error: normalized.message,
    });
    sendCompletion(taskId, false, null, normalized);
  }
}

async function handleCollectHealth() {
  try {
    const version = await requestDevtoolsJson('/json/version');
    recentFailures = 0;
    sendHeartbeat(true, {
      browser_kind: browserLabel,
      browser_path: browserPath,
      debug_port: devtoolsPort,
      browser_version: version?.Browser,
    });
  } catch (error) {
    recentFailures += 1;
    sendHeartbeat(false, {
      browser_kind: browserLabel,
      browser_path: browserPath,
      debug_port: devtoolsPort,
      last_error: error instanceof Error ? error.message : String(error),
    });
  }
}

async function handleEnvelope(envelope) {
  switch (envelope?.action) {
    case 'execute_task':
      await handleExecuteTask(envelope);
      break;
    case 'collect_health':
      await handleCollectHealth();
      break;
    case 'shutdown_runtime':
      await cleanup();
      process.exit(0);
      break;
    default:
      break;
  }
}

(async () => {
  try {
    await startBrowser();
    browserHealthy = true;
    sendReady();
    await handleCollectHealth();

    const heartbeatTimer = setInterval(() => {
      handleCollectHealth().catch((error) => {
        console.error(`chrome runtime heartbeat failed: ${error instanceof Error ? error.message : String(error)}`);
      });
    }, 15000);
    heartbeatTimer.unref();

    const rl = readline.createInterface({
      input: process.stdin,
      crlfDelay: Infinity,
    });

    rl.on('line', (line) => {
      if (!line.trim()) {
        return;
      }
      Promise.resolve()
        .then(async () => {
          const envelope = JSON.parse(line.replace(/^\uFEFF/, ''));
          await handleEnvelope(envelope);
        })
        .catch((error) => {
          recentFailures += 1;
          console.error(`chrome runtime failed to handle message: ${error instanceof Error ? error.stack || error.message : String(error)}`);
        });
    });

    rl.on('close', async () => {
      await cleanup();
      process.exit(0);
    });

    process.on('SIGTERM', async () => {
      await cleanup();
      process.exit(0);
    });
    process.on('SIGINT', async () => {
      await cleanup();
      process.exit(0);
    });
  } catch (error) {
    console.error(error instanceof Error ? error.stack || error.message : String(error));
    await cleanup();
    process.exit(1);
  }
})();

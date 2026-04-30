#!/usr/bin/env node

const readline = require('node:readline');

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

const args = parseArgs(process.argv.slice(2));
const providerId = String(args.provider || '').trim();
const runtimeId = String(args['runtime-id'] || '').trim();
const apiKey = String(process.env.BROWSERBASE_API_KEY || '').trim();
const defaultProjectId = String(process.env.BROWSERBASE_PROJECT_ID || '').trim();
const baseUrl = String(process.env.EASYBROWSER_BROWSERBASE_BASE_URL || 'https://api.browserbase.com')
  .trim()
  .replace(/\/+$/, '');

let recentFailures = 0;
let lastHealthy = true;

if (!providerId || !runtimeId) {
  console.error('browserbase runtime requires --provider and --runtime-id');
  process.exit(1);
}

if (!apiKey) {
  console.error('browserbase runtime requires BROWSERBASE_API_KEY');
  process.exit(1);
}

function nowIso() {
  return new Date().toISOString();
}

function nextId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

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
    pid: process.pid,
    state: 'ready',
    started_at: nowIso(),
  });
}

function sendHeartbeat(healthy, notes) {
  lastHealthy = healthy;
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

function makeLocalError({ category, code, message, retriable = false, cooldownCandidate = false, raw = null }) {
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

async function readResponseBody(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function buildUrl(pathname, query) {
  let normalized = String(pathname || '').trim();
  if (!normalized) {
    throw makeLocalError({
      category: 'provider',
      code: 'missing_path',
      message: 'browserbase path is required',
      retriable: false,
      cooldownCandidate: false,
    });
  }
  if (!normalized.startsWith('/')) {
    normalized = `/${normalized}`;
  }
  if (!normalized.startsWith('/v1/')) {
    if (normalized.startsWith('/sessions') || normalized.startsWith('/projects')) {
      normalized = `/v1${normalized}`;
    }
  }

  const url = new URL(`${baseUrl}${normalized}`);
  if (query && typeof query === 'object') {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === '') {
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

async function browserbaseRequest(method, pathname, body, query) {
  const headers = {
    'x-bb-api-key': apiKey,
    Accept: 'application/json',
  };
  const options = { method, headers };
  if (body !== undefined && body !== null && method !== 'GET' && method !== 'HEAD') {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(buildUrl(pathname, query), options);
  } catch (error) {
    throw makeLocalError({
      category: 'transport',
      code: 'browserbase_transport_error',
      message: error instanceof Error ? error.message : 'browserbase transport error',
      retriable: true,
      cooldownCandidate: true,
      raw: {
        cause: error instanceof Error ? error.stack : String(error),
      },
    });
  }

  const responseBody = await readResponseBody(response);
  if (!response.ok) {
    const message =
      (responseBody && typeof responseBody === 'object' && responseBody.message) ||
      response.statusText ||
      `browserbase request failed (${response.status})`;

    const retriable = response.status === 408 || response.status === 429 || response.status >= 500;
    throw makeLocalError({
      category: 'provider',
      code: `browserbase_http_${response.status}`,
      message,
      retriable,
      cooldownCandidate: retriable,
      raw: {
        status: response.status,
        body: responseBody,
      },
    });
  }

  return responseBody;
}

function resolveSessionID(payload) {
  return String(
    payload?.resource_id ||
      payload?.resourceId ||
      payload?.session_id ||
      payload?.sessionId ||
      payload?.id ||
      payload?.body?.id ||
      payload?.body?.sessionId ||
      '',
  ).trim();
}

function buildCreateSessionBody(payload) {
  let body = payload?.body ?? payload?.session ?? {};
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    body = {};
  }

  if (!body.projectId) {
    if (payload?.project_id) {
      body.projectId = payload.project_id;
    } else if (payload?.projectId) {
      body.projectId = payload.projectId;
    } else if (defaultProjectId) {
      body.projectId = defaultProjectId;
    }
  }
  if (payload?.keep_alive !== undefined && body.keepAlive === undefined) {
    body.keepAlive = Boolean(payload.keep_alive);
  }
  if (payload?.keepAlive !== undefined && body.keepAlive === undefined) {
    body.keepAlive = Boolean(payload.keepAlive);
  }
  if (payload?.region !== undefined && body.region === undefined) {
    body.region = payload.region;
  }
  if (payload?.timeout !== undefined && body.timeout === undefined) {
    body.timeout = payload.timeout;
  }
  if (payload?.user_metadata !== undefined && body.userMetadata === undefined) {
    body.userMetadata = payload.user_metadata;
  }
  if (payload?.userMetadata !== undefined && body.userMetadata === undefined) {
    body.userMetadata = payload.userMetadata;
  }
  if (payload?.extension_id !== undefined && body.extensionId === undefined) {
    body.extensionId = payload.extension_id;
  }
  if (payload?.extensionId !== undefined && body.extensionId === undefined) {
    body.extensionId = payload.extensionId;
  }
  if (payload?.browser_settings !== undefined && body.browserSettings === undefined) {
    body.browserSettings = payload.browser_settings;
  }
  if (payload?.browserSettings !== undefined && body.browserSettings === undefined) {
    body.browserSettings = payload.browserSettings;
  }
  if (payload?.proxies !== undefined && body.proxies === undefined) {
    body.proxies = payload.proxies;
  }
  if (payload?.context_id !== undefined && body.contextId === undefined) {
    body.contextId = payload.context_id;
  }
  if (payload?.contextId !== undefined && body.contextId === undefined) {
    body.contextId = payload.contextId;
  }

  return body;
}

function resolveProjectID(payload) {
  return String(
    payload?.project_id ||
      payload?.projectId ||
      payload?.body?.projectId ||
      defaultProjectId ||
      '',
  ).trim();
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

async function executeBrowserbaseAction(request) {
  const operation = request?.operation || {};
  const payload = operation.payload || {};
  const action = String(payload.action || operation.kind || '').trim().toLowerCase();
  const resourceKind = String(payload.resource_kind || payload.resourceKind || '').trim().toLowerCase();

  if (['open_resource', 'list_resources', 'get_resource', 'close_resource'].includes(action) && resourceKind && resourceKind !== 'session') {
    throw makeLocalError({
      category: 'provider',
      code: 'unsupported_resource_kind',
      message: `browserbase does not support resource_kind=${resourceKind} for action=${action}`,
      retriable: false,
      cooldownCandidate: false,
    });
  }

  switch (action) {
    case 'open_resource':
    case 'create_session': {
      const body = buildCreateSessionBody(payload);
      const response = await browserbaseRequest('POST', '/v1/sessions', body);
      return { action, resource_kind: 'session', response };
    }
    case 'list_resources':
    case 'list_sessions': {
      const response = await browserbaseRequest('GET', '/v1/sessions', undefined, payload.query || payload.filters);
      return { action, resource_kind: 'session', response };
    }
    case 'get_resource':
    case 'get_session': {
      const sessionId = resolveSessionID(payload);
      if (!sessionId) {
        throw makeLocalError({
          category: 'provider',
          code: 'missing_session_id',
          message: 'get_session requires session_id',
          retriable: false,
          cooldownCandidate: false,
        });
      }
      const response = await browserbaseRequest('GET', `/v1/sessions/${encodeURIComponent(sessionId)}`);
      return { action, resource_kind: 'session', response, session_id: sessionId };
    }
    case 'close_resource':
    case 'update_session':
    case 'close_session':
    case 'release_session':
    case 'request_release': {
      const sessionId = resolveSessionID(payload);
      if (!sessionId) {
        throw makeLocalError({
          category: 'provider',
          code: 'missing_session_id',
          message: `${action} requires session_id`,
          retriable: false,
          cooldownCandidate: false,
        });
      }
      let body = payload.body ?? {};
      if (!body || typeof body !== 'object' || Array.isArray(body)) {
        body = {};
      }
      if (!body.projectId) {
        const projectId = resolveProjectID(payload);
        if (projectId) {
          body.projectId = projectId;
        }
      }
      if (!body.projectId) {
        throw makeLocalError({
          category: 'provider',
          code: 'missing_project_id',
          message: `${action} requires projectId or BROWSERBASE_PROJECT_ID`,
          retriable: false,
          cooldownCandidate: false,
        });
      }
      if ((action === 'request_release' || action === 'close_session' || action === 'release_session') && body.status === undefined) {
        body.status = 'REQUEST_RELEASE';
      }
      if (action === 'close_resource' && body.status === undefined) {
        body.status = 'REQUEST_RELEASE';
      }
      const response = await browserbaseRequest('POST', `/v1/sessions/${encodeURIComponent(sessionId)}`, body);
      return { action, resource_kind: 'session', response, session_id: sessionId };
    }
    case 'api_request': {
      const method = String(payload.method || 'GET').toUpperCase();
      const path = payload.path || payload.endpoint;
      const response = await browserbaseRequest(method, path, payload.body, payload.query);
      return { action, response };
    }
    case 'health': {
      const response = await browserbaseRequest('GET', '/v1/sessions');
      return { action, response };
    }
    default:
      throw makeLocalError({
        category: 'provider',
        code: 'unsupported_action',
        message: `unsupported browserbase action: ${action || '<empty>'}`,
        retriable: false,
        cooldownCandidate: false,
        raw: {
          supported_actions: ['open_resource', 'list_resources', 'get_resource', 'close_resource', 'create_session', 'list_sessions', 'get_session', 'update_session', 'request_release', 'api_request', 'health'],
        },
      });
  }
}

async function handleExecuteTask(envelope) {
  const taskId = String(envelope?.trace?.task_id || envelope?.payload?.task_id || '').trim();
  const request = envelope?.payload?.request || {};

  try {
    const execution = await executeBrowserbaseAction(request);
    recentFailures = 0;
    sendHeartbeat(true);
    sendCompletion(taskId, true, {
      provider_id: providerId,
      runtime_id: runtimeId,
      action: execution.action,
      response: execution.response,
      session_id: execution.session_id,
    }, null);
  } catch (error) {
    recentFailures += 1;
    const normalized = normalizeError(error);
    const healthy = !(normalized.category === 'transport' || normalized.code === 'browserbase_http_429' || normalized.code.startsWith('browserbase_http_5'));
    sendHeartbeat(healthy);
    sendCompletion(taskId, false, null, normalized);
  }
}

async function handleCollectHealth() {
  try {
    await browserbaseRequest('GET', '/v1/sessions');
    recentFailures = 0;
    sendHeartbeat(true);
  } catch (error) {
    recentFailures += 1;
    sendHeartbeat(false);
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
      process.exit(0);
      break;
    default:
      break;
  }
}

sendReady();
sendHeartbeat(true);

const heartbeatTimer = setInterval(() => {
  sendHeartbeat(lastHealthy);
}, 15000);
heartbeatTimer.unref();

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

rl.on('line', async (line) => {
  if (!line.trim()) {
    return;
  }
  try {
    const envelope = JSON.parse(line.replace(/^\uFEFF/, ''));
    await handleEnvelope(envelope);
  } catch (error) {
    recentFailures += 1;
    console.error(`browserbase runtime failed to handle message: ${error instanceof Error ? error.stack || error.message : String(error)}`);
  }
});

rl.on('close', () => {
  process.exit(0);
});

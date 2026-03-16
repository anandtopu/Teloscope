/**
 * AgentLens Node.js SDK
 * Auto-instrumentation for AI agents in Node.js/TypeScript.
 *
 * Usage:
 *   const { init, traceAgent, traceLLM, traceTool, flush } = require('agentlens-sdk');
 *   init({ apiKey: 'your-key', endpoint: 'http://localhost:8000' });
 */
'use strict';

const { randomUUID } = require('crypto');
const https = require('https');
const http = require('http');

// ─── State ────────────────────────────────────────────────────────────────────

const state = {
  apiKey:         '',
  endpoint:       'http://localhost:8000',
  orgId:          'default',
  projectId:      'default',
  environment:    'production',
  framework:      'custom',
  sdkVersion:     '1.0.0',
  enabled:        false,
  debug:          false,
  flushThreshold: 50,
  spanBuffer:     [],
};

// Context tracking using AsyncLocalStorage (Node 12.17+)
let AsyncLocalStorage;
try {
  ({ AsyncLocalStorage } = require('async_hooks'));
} catch (_) {
  AsyncLocalStorage = null;
}

const contextStorage = AsyncLocalStorage ? new AsyncLocalStorage() : null;

function getContext() {
  return contextStorage?.getStore() ?? {};
}

// ─── Init ─────────────────────────────────────────────────────────────────────

/**
 * Initialize the AgentLens SDK.
 * @param {Object} options
 * @param {string} options.apiKey
 * @param {string} [options.endpoint]
 * @param {string} [options.orgId]
 * @param {string} [options.projectId]
 * @param {string} [options.environment]
 * @param {string} [options.framework]
 * @param {boolean} [options.debug]
 */
function init(options = {}) {
  Object.assign(state, {
    apiKey:         options.apiKey         || '',
    endpoint:       (options.endpoint      || 'http://localhost:8000').replace(/\/$/, ''),
    orgId:          options.orgId          || 'default',
    projectId:      options.projectId      || 'default',
    environment:    options.environment    || 'production',
    framework:      options.framework      || 'custom',
    debug:          options.debug          || false,
    flushThreshold: options.flushThreshold || 50,
    enabled:        true,
    spanBuffer:     [],
  });

  // Auto-flush on process exit
  process.on('exit',    () => flushSync());
  process.on('SIGINT',  () => { flushSync(); process.exit(0); });
  process.on('SIGTERM', () => { flushSync(); process.exit(0); });

  if (state.debug) console.log(`[AgentLens] SDK initialized → ${state.endpoint}`);
}

// ─── Span Helpers ─────────────────────────────────────────────────────────────

function newSpan(name, kind, overrides = {}) {
  const ctx = getContext();
  return {
    spanId:        randomUUID(),
    traceId:       ctx.traceId    || overrides.traceId    || randomUUID(),
    parentSpanId:  ctx.spanId     || overrides.parentSpanId || null,
    name,
    kind,
    status:        'UNSET',
    startTime:     new Date().toISOString(),
    endTime:       null,
    durationMs:    null,
    agentId:       ctx.agentName  || overrides.agentId    || null,
    sessionId:     ctx.sessionId  || overrides.sessionId  || null,
    orgId:         state.orgId,
    projectId:     state.projectId,
    framework:     state.framework,
    environment:   state.environment,
    sdkVersion:    state.sdkVersion,
    input:         null,
    output:        null,
    error:         null,
    errorType:     null,
    llmAttributes: null,
    toolAttributes:null,
    attributes:    {},
    events:        [],
    ...overrides,
  };
}

function finishSpan(span, output = null, error = null) {
  span.endTime   = new Date().toISOString();
  span.durationMs = new Date(span.endTime) - new Date(span.startTime);
  if (output !== null && output !== undefined) span.output = output;
  if (error) {
    span.status    = 'ERROR';
    span.error     = error.message || String(error);
    span.errorType = error.constructor?.name || 'Error';
  } else {
    span.status = 'OK';
  }
  bufferSpan(span);
  return span;
}

function bufferSpan(span) {
  if (!state.enabled) return;
  // Convert camelCase to snake_case for API compatibility
  state.spanBuffer.push(toSnakeCase(span));
  if (state.debug) console.log(`[AgentLens] Span: ${span.kind}/${span.name} (${span.status})`);
  if (state.spanBuffer.length >= state.flushThreshold) {
    flush().catch(() => {});
  }
}

function toSnakeCase(obj) {
  if (Array.isArray(obj)) return obj.map(toSnakeCase);
  if (obj && typeof obj === 'object' && !(obj instanceof Date)) {
    const result = {};
    for (const [k, v] of Object.entries(obj)) {
      const snake = k.replace(/([A-Z])/g, '_$1').toLowerCase();
      result[snake] = toSnakeCase(v);
    }
    return result;
  }
  return obj;
}

// ─── Flush ─────────────────────────────────────────────────────────────────────

/**
 * Flush buffered spans to the AgentLens ingestion endpoint.
 * @returns {Promise<boolean>}
 */
async function flush() {
  if (!state.enabled || state.spanBuffer.length === 0) return true;

  const spans = [...state.spanBuffer];
  state.spanBuffer = [];

  const payload = JSON.stringify({ spans });
  const url = new URL(`${state.endpoint}/api/v1/ingest/spans`);
  const isHttps = url.protocol === 'https:';
  const lib = isHttps ? https : http;

  return new Promise((resolve) => {
    const req = lib.request(
      {
        hostname: url.hostname,
        port:     url.port || (isHttps ? 443 : 80),
        path:     url.pathname,
        method:   'POST',
        headers:  {
          'Content-Type':   'application/json',
          'Content-Length': Buffer.byteLength(payload),
          'X-API-Key':      state.apiKey,
        },
      },
      (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          if (state.debug) console.log(`[AgentLens] Flushed ${spans.length} spans → ${res.statusCode}`);
          resolve(true);
        } else {
          state.spanBuffer = [...spans, ...state.spanBuffer];
          resolve(false);
        }
        res.resume();
      },
    );
    req.on('error', (err) => {
      if (state.debug) console.error('[AgentLens] Flush error:', err.message);
      state.spanBuffer = [...spans, ...state.spanBuffer];
      resolve(false);
    });
    req.write(payload);
    req.end();
  });
}

function flushSync() {
  // Best-effort synchronous flush for process exit handlers
  if (!state.enabled || state.spanBuffer.length === 0) return;
  const spans = [...state.spanBuffer];
  state.spanBuffer = [];

  try {
    const { execSync } = require('child_process');
    const payload = JSON.stringify({ spans });
    // Use curl as synchronous HTTP — last resort for exit handlers
    execSync(
      `curl -s -X POST "${state.endpoint}/api/v1/ingest/spans" ` +
      `-H "Content-Type: application/json" ` +
      `-H "X-API-Key: ${state.apiKey}" ` +
      `-d '${payload.replace(/'/g, "'\\''")}'`,
      { timeout: 5000 },
    );
  } catch (_) { /* best effort */ }
}

// ─── Higher-Order Functions ───────────────────────────────────────────────────

/**
 * Wrap an async function as a traced agent invocation.
 *
 * @param {string} name      Agent name
 * @param {Function} fn      Async function to wrap
 * @param {Object}  [opts]
 * @param {string}  [opts.sessionId]
 * @returns {Function}
 *
 * Example:
 *   const myAgent = traceAgent('search-agent', async (query) => { ... });
 */
function traceAgent(name, fn, opts = {}) {
  return async function (...args) {
    const traceId = randomUUID();
    const span    = newSpan(name, 'agent', { traceId, agentId: name });
    span.input    = { args };

    const ctx = { traceId, spanId: span.spanId, agentName: name, sessionId: opts.sessionId || null };

    let result, error;
    try {
      if (contextStorage) {
        result = await contextStorage.run(ctx, () => fn(...args));
      } else {
        result = await fn(...args);
      }
      return result;
    } catch (err) {
      error = err;
      throw err;
    } finally {
      finishSpan(span, result, error);
    }
  };
}

/**
 * Wrap an async function as a traced LLM call.
 *
 * @param {string}   provider  LLM provider name
 * @param {string}   model     Model identifier
 * @param {Function} fn        Async function
 * @returns {Function}
 */
function traceLLM(provider, model, fn) {
  return async function (...args) {
    const span = newSpan(model || fn.name, 'llm');
    span.llmAttributes = { provider, model, tokenUsage: null, cost: null };
    span.input = { args };

    let result, error;
    try {
      result = await fn(...args);
      return result;
    } catch (err) {
      error = err;
      throw err;
    } finally {
      // Extract token usage if result has OpenAI-compatible usage field
      if (result?.usage) {
        span.llmAttributes.tokenUsage = {
          promptTokens:     result.usage.prompt_tokens     || 0,
          completionTokens: result.usage.completion_tokens || 0,
          totalTokens:      result.usage.total_tokens      || 0,
        };
      }
      finishSpan(span, result, error);
    }
  };
}

/**
 * Wrap an async function as a traced tool call.
 *
 * @param {string}   name        Tool name
 * @param {Function} fn          Async function
 * @param {string}   [description]
 * @returns {Function}
 */
function traceTool(name, fn, description = '') {
  return async function (...args) {
    const span = newSpan(name, 'tool');
    span.toolAttributes = { toolName: name, toolDescription: description, isMcpTool: false };
    span.input = { args };

    let result, error;
    try {
      result = await fn(...args);
      return result;
    } catch (err) {
      error = err;
      throw err;
    } finally {
      finishSpan(span, result, error);
    }
  };
}

/**
 * Execute a function within a named span.
 *
 * @param {string}   name
 * @param {string}   kind
 * @param {Function} fn   Async or sync function receiving the span object
 * @returns {Promise<any>}
 *
 * Example:
 *   const result = await withSpan('retrieval', 'retrieval', async (s) => {
 *     s.attributes.collection = 'docs';
 *     return vectorDb.search(query);
 *   });
 */
async function withSpan(name, kind, fn) {
  const s = newSpan(name, kind);
  let result, error;
  try {
    result = await fn(s);
    return result;
  } catch (err) {
    error = err;
    throw err;
  } finally {
    finishSpan(s, result, error);
  }
}

// ─── Exports ──────────────────────────────────────────────────────────────────

module.exports = {
  init,
  flush,
  flushSync,
  traceAgent,
  traceLLM,
  traceTool,
  withSpan,
  // Expose state for testing
  _state: state,
};

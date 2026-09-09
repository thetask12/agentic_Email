/**
 * Utils.gs
 * ------------------------------------------------------------------------
 * Generic helper functions shared across the Apps Script project:
 *   - UUID generation (prefixed like the backend's app/utils/ids.py)
 *   - ISO-8601 timestamp helpers
 *   - Safe JSON parse/stringify
 *   - Email validation
 *   - HTML sanitization for reply bodies before writing to the Sheet
 *   - Retry-with-backoff wrapper for transient errors
 *
 * Keep this file dependency-free (no references to other .gs files) so it
 * can be safely used by any worker.
 */

/**
 * Generates a UUID v4 string, matching the backend's ID format:
 * "<prefix>_<uuid4>", e.g. "fu_3b1f2b0a-....", "evt_...".
 * Prefixes used across the system (see docs/sheet-schema.md):
 *   job_, cmp_, lead_, eml_, fu_, rpl_, evt_, run_, camp_, sup_, act_, note_,
 *   tpl_, q_, conv_
 *
 * @param {string} prefix Entity prefix, e.g. "evt".
 * @return {string} A prefixed UUID v4 string.
 */
function generateId(prefix) {
  var uuid = Utilities.getUuid(); // Apps Script built-in UUID v4 generator.
  return (prefix ? prefix + '_' : '') + uuid;
}

/**
 * Returns the current time as an ISO-8601 UTC string, matching the
 * convention used everywhere else in the system ("All timestamps are
 * ISO-8601 UTC strings" - docs/sheet-schema.md).
 * @return {string}
 */
function nowIso() {
  return new Date().toISOString();
}

/**
 * Converts any Date (or date-like value) to an ISO-8601 UTC string.
 * Returns '' for null/undefined/invalid input.
 * @param {Date|string|number} value
 * @return {string}
 */
function toIso(value) {
  if (value === null || value === undefined || value === '') return '';
  var d = (value instanceof Date) ? value : new Date(value);
  if (isNaN(d.getTime())) return '';
  return d.toISOString();
}

/**
 * Safely parses a JSON string. Returns the fallback value (default: null)
 * if parsing fails or input is empty, instead of throwing.
 * @param {string} str
 * @param {*} fallback
 * @return {*}
 */
function safeJsonParse(str, fallback) {
  if (fallback === undefined) fallback = null;
  if (!str || typeof str !== 'string') return fallback;
  try {
    return JSON.parse(str);
  } catch (e) {
    return fallback;
  }
}

/**
 * Safely stringifies a value to JSON. Returns '' on failure instead of
 * throwing (e.g. circular references).
 * @param {*} value
 * @return {string}
 */
function safeJsonStringify(value) {
  if (value === null || value === undefined) return '';
  try {
    return JSON.stringify(value);
  } catch (e) {
    return '';
  }
}

/**
 * Basic RFC-5322-ish email validation. Good enough to catch obviously
 * malformed addresses before we attempt to send; not a full RFC parser.
 * @param {string} email
 * @return {boolean}
 */
function isValidEmail(email) {
  if (!email || typeof email !== 'string') return false;
  var trimmed = email.trim();
  // Simple, pragmatic pattern: local@domain.tld
  var re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return re.test(trimmed);
}

/**
 * Sanitizes HTML before it is written into the Sheet or shown in the
 * frontend. This is a defense-in-depth measure for inbound reply bodies
 * (System.txt #58: "Never render unsafe raw HTML directly. Sanitize HTML
 * before frontend display.").
 *
 * Strategy (regex-based, since Apps Script has no DOM/HTML parser
 * built in): strip <script>...</script> and <style>...</style> blocks
 * entirely (including content), strip on* event-handler attributes
 * (onclick=, onerror=, etc.), and neutralize javascript: URLs in href/src.
 *
 * This is NOT a substitute for sanitizing again on the frontend (e.g.
 * with DOMPurify) before rendering — treat this as a first line of
 * defense that keeps obviously dangerous payloads out of the Sheet.
 *
 * @param {string} html
 * @return {string} sanitized HTML
 */
function sanitizeHtml(html) {
  if (!html || typeof html !== 'string') return '';
  var out = html;

  // Remove <script>...</script> blocks (case-insensitive, multiline).
  out = out.replace(/<script[\s\S]*?<\/script>/gi, '');
  // Remove <style>...</style> blocks.
  out = out.replace(/<style[\s\S]*?<\/style>/gi, '');
  // Remove <iframe>, <object>, <embed> blocks entirely.
  out = out.replace(/<iframe[\s\S]*?<\/iframe>/gi, '');
  out = out.replace(/<object[\s\S]*?<\/object>/gi, '');
  out = out.replace(/<embed[\s\S]*?>/gi, '');
  // Strip on*="..." and on*='...' event handler attributes.
  out = out.replace(/\son\w+\s*=\s*"[^"]*"/gi, '');
  out = out.replace(/\son\w+\s*=\s*'[^']*'/gi, '');
  out = out.replace(/\son\w+\s*=\s*[^\s>]+/gi, '');
  // Neutralize javascript: URLs.
  out = out.replace(/(href|src)\s*=\s*"(\s*javascript:[^"]*)"/gi, '$1="#"');
  out = out.replace(/(href|src)\s*=\s*'(\s*javascript:[^']*)'/gi, "$1='#'");

  return out;
}

/**
 * Escapes a plain string for safe inclusion inside HTML markup (&, <, >,
 * ", '). Apps Script has no built-in Utilities.htmlEncode() - that method
 * does not exist on the Utilities service despite the name suggesting
 * otherwise (this previously caused every test-mode send to throw
 * "Utilities.htmlEncode is not a function" and fail outright). Use this
 * instead anywhere untrusted/dynamic text needs to be embedded in an HTML
 * email body.
 * @param {string} str
 * @return {string}
 */
function escapeHtml_(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Strips all HTML tags to produce a plain-text approximation. Used when
 * only a plain-text body is needed (e.g. for logs) from an HTML source.
 * @param {string} html
 * @return {string}
 */
function stripHtml(html) {
  if (!html) return '';
  return sanitizeHtml(html).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

/**
 * Retries a function with exponential backoff. Use for transient errors
 * such as Sheets API rate limits (HTTP 429) or transient network errors.
 * Does NOT retry indefinitely - respects maxAttempts.
 *
 * @param {Function} fn Zero-arg function to invoke. May throw.
 * @param {Object} [options]
 * @param {number} [options.maxAttempts=3]
 * @param {number} [options.baseDelayMs=500] Base delay, doubled each retry.
 * @param {function(Error):boolean} [options.shouldRetry] Predicate to decide
 *        whether a given error is transient/retryable. Defaults to always
 *        retry (safe for idempotent read/append operations).
 * @return {*} The return value of fn() on success.
 * @throws {Error} The last error if all attempts fail.
 */
function retryWithBackoff(fn, options) {
  options = options || {};
  var maxAttempts = options.maxAttempts || 3;
  var baseDelayMs = options.baseDelayMs || 500;
  var shouldRetry = options.shouldRetry || function () { return true; };

  var lastError = null;
  for (var attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return fn();
    } catch (err) {
      lastError = err;
      var isLastAttempt = attempt === maxAttempts;
      if (isLastAttempt || !shouldRetry(err)) {
        throw err;
      }
      var delay = baseDelayMs * Math.pow(2, attempt - 1);
      Utilities.sleep(delay);
    }
  }
  throw lastError;
}

/**
 * Extracts a bare email address from a Gmail-style "Display Name
 * <email@domain.com>" header value. Returns the trimmed input unchanged
 * if no angle-bracket address is found.
 * @param {string} headerValue
 * @return {string}
 */
function extractEmailAddress(headerValue) {
  if (!headerValue) return '';
  var match = headerValue.match(/<([^>]+)>/);
  if (match) return match[1].trim().toLowerCase();
  return headerValue.trim().toLowerCase();
}

/**
 * Extracts the display name portion from a "Display Name <email>" header
 * value. Returns '' if not present.
 * @param {string} headerValue
 * @return {string}
 */
function extractDisplayName(headerValue) {
  if (!headerValue) return '';
  var match = headerValue.match(/^"?([^"<]*)"?\s*<[^>]+>/);
  if (match) return match[1].trim();
  return '';
}

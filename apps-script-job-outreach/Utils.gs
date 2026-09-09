/**
 * Utils.gs
 * ------------------------------------------------------------------------
 * Generic helper functions shared across this Apps Script project. Ported
 * from apps-script/Utils.gs, keeping only what this simpler module actually
 * needs (no HTML sanitization — this module sends plain-text-only emails
 * with no inbound reply scanning).
 */

/**
 * Generates a UUID v4 string, matching the backend's id format:
 * "<prefix>_<uuid4>".
 * @param {string} prefix Entity prefix, e.g. "evt".
 * @return {string}
 */
function generateId(prefix) {
  var uuid = Utilities.getUuid();
  return (prefix ? prefix + '_' : '') + uuid;
}

/**
 * Returns the current time as an ISO-8601 UTC string.
 * @return {string}
 */
function nowIso() {
  return new Date().toISOString();
}

/**
 * Safely stringifies a value to JSON. Returns '' on failure instead of
 * throwing.
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
 * malformed addresses before attempting to send.
 * @param {string} email
 * @return {boolean}
 */
function isValidEmail(email) {
  if (!email || typeof email !== 'string') return false;
  var trimmed = email.trim();
  var re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return re.test(trimmed);
}

/**
 * Retries a function with exponential backoff. Use for transient errors
 * such as Sheets API rate limits (HTTP 429).
 * @param {Function} fn Zero-arg function to invoke. May throw.
 * @param {Object} [options]
 * @param {number} [options.maxAttempts=3]
 * @param {number} [options.baseDelayMs=500]
 * @return {*} The return value of fn() on success.
 * @throws {Error} The last error if all attempts fail.
 */
function retryWithBackoff(fn, options) {
  options = options || {};
  var maxAttempts = options.maxAttempts || 3;
  var baseDelayMs = options.baseDelayMs || 500;

  var lastError = null;
  for (var attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return fn();
    } catch (err) {
      lastError = err;
      if (attempt === maxAttempts) {
        throw err;
      }
      var delay = baseDelayMs * Math.pow(2, attempt - 1);
      Utilities.sleep(delay);
    }
  }
  throw lastError;
}

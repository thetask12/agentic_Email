/**
 * EventLogger.gs
 * ------------------------------------------------------------------------
 * Small helper for appending rows to EMAIL_EVENTS and ACTIVITY_LOG with
 * generated IDs and ISO timestamps, used by QueueWorker.
 *
 * IMPORTANT: only ever log event_type values Apps Script can ACTUALLY
 * observe: QUEUED, SENT, FAILED, BOUNCED. Never fabricate DELIVERED/OPENED/
 * CLICKED — Gmail/GmailApp does not expose delivery or open tracking.
 */

/**
 * Appends a new row to EMAIL_EVENTS.
 * @param {Object} event
 * @param {string} [event.queue_id]
 * @param {string} [event.company_id]
 * @param {string} event.event_type
 * @param {string} [event.message_id]
 * @param {string} [event.thread_id]
 * @param {boolean} [event.test_mode]
 * @param {Object|string} [event.metadata]
 * @return {Object} the appended row.
 */
function logEmailEvent(event) {
  var metadata = event.metadata;
  if (metadata && typeof metadata === 'object') {
    metadata = safeJsonStringify(metadata);
  }
  var row = {
    event_id: generateId('evt'),
    queue_id: event.queue_id || '',
    company_id: event.company_id || '',
    event_type: event.event_type,
    message_id: event.message_id || '',
    thread_id: event.thread_id || '',
    test_mode: event.test_mode === true,
    metadata: metadata || '',
    created_at: nowIso()
  };
  return SheetRepository.appendRow(SHEET_NAMES.EMAIL_EVENTS, row);
}

/**
 * Appends a new row to ACTIVITY_LOG.
 * @param {string} eventName
 * @param {string} [details]
 * @return {Object} the appended row.
 */
function logActivity(eventName, details) {
  var row = {
    log_id: generateId('log'),
    event: eventName,
    details: details || '',
    created_at: nowIso()
  };
  return SheetRepository.appendRow(SHEET_NAMES.ACTIVITY_LOG, row);
}

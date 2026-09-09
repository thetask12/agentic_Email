/**
 * EventLogger.gs
 * ------------------------------------------------------------------------
 * Small helper for appending rows to EMAIL_EVENTS and ACTIVITY_LOG with
 * generated IDs and ISO timestamps, used by QueueWorker, FollowUpWorker,
 * and ReplyScanner.
 *
 * IMPORTANT (System.txt #20, #54, #114): only ever log event_type values
 * that Apps Script can ACTUALLY observe:
 *   CREATED, APPROVED, QUEUED, PROCESSING, SENT, FAILED, REPLIED,
 *   FOLLOW_UP_SCHEDULED, FOLLOW_UP_SENT, CANCELLED
 * NEVER log DELIVERED, BOUNCED, OPENED, or CLICKED from Apps Script unless
 * a real, reliable signal produced them (Gmail/GmailApp does not expose
 * delivery or open tracking - see the long comment in EmailSender.gs).
 * The frontend must instead show "SENT — DELIVERY STATUS UNKNOWN" for any
 * email whose delivery could not be confirmed, and "OPEN TRACKING NOT
 * AVAILABLE" for opens.
 */

/**
 * Appends a new row to EMAIL_EVENTS.
 *
 * @param {Object} event
 * @param {string} [event.email_id]
 * @param {string} [event.lead_id]
 * @param {string} [event.company_id]
 * @param {string} event.event_type One of the EMAIL_EVENTS event_type enum values.
 * @param {string} [event.message_id]
 * @param {string} [event.provider] e.g. "gmail"
 * @param {Object|string} [event.metadata] Will be JSON-stringified if an object.
 * @return {Object} the appended row.
 */
function logEmailEvent(event) {
  var metadata = event.metadata;
  if (metadata && typeof metadata === 'object') {
    metadata = safeJsonStringify(metadata);
  }
  var row = {
    event_id: generateId('evt'),
    email_id: event.email_id || '',
    lead_id: event.lead_id || '',
    company_id: event.company_id || '',
    event_type: event.event_type,
    timestamp: nowIso(),
    message_id: event.message_id || '',
    provider: event.provider || 'gmail',
    metadata: metadata || '',
    created_at: nowIso()
  };
  return SheetRepository.appendRow(SHEET_NAMES.EMAIL_EVENTS, row);
}

/**
 * Appends a new row to ACTIVITY_LOG. Used for the cross-entity, human
 * readable timeline shown on the Lead Detail page (System.txt #30, #65, #66).
 *
 * @param {Object} activity
 * @param {string} [activity.lead_id]
 * @param {string} [activity.company_id]
 * @param {string} activity.activity_type e.g. "EMAIL_SENT", "REPLY_RECEIVED"
 * @param {string} activity.description Human-readable description.
 * @param {Object|string} [activity.metadata]
 * @param {string} [activity.created_by] Defaults to "apps_script".
 * @return {Object} the appended row.
 */
function logActivity(activity) {
  var metadata = activity.metadata;
  if (metadata && typeof metadata === 'object') {
    metadata = safeJsonStringify(metadata);
  }
  var row = {
    activity_id: generateId('act'),
    lead_id: activity.lead_id || '',
    company_id: activity.company_id || '',
    activity_type: activity.activity_type,
    description: activity.description || '',
    metadata: metadata || '',
    created_at: nowIso(),
    created_by: activity.created_by || 'apps_script'
  };
  return SheetRepository.appendRow(SHEET_NAMES.ACTIVITY_LOG, row);
}

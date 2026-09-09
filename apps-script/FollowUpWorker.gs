/**
 * FollowUpWorker.gs
 * ------------------------------------------------------------------------
 * processFollowUps() - the FOLLOW_UPS worker (System.txt #31-41, #56, #99,
 * #124-126).
 *
 * Entry point intended for a time-driven trigger (installed by
 * installTriggers() in Code.gs), running every 15 minutes.
 *
 * DESIGN CHOICE - push to EMAIL_QUEUE instead of sending directly:
 * This worker does NOT call EmailSender directly. Instead, when a
 * follow-up is due and passes all checks, it creates a new EMAIL_QUEUE
 * row (kind=FOLLOW_UP, referencing original_email_id) with status
 * PENDING, and marks the FOLLOW_UPS row QUEUED. processEmailQueue() then
 * sends it on its own schedule (every 5 minutes) exactly like any other
 * queued email. This is deliberate:
 *   - Single source of truth for "how we send email" (suppression checks,
 *     retry/backoff, idempotent status guards, message/thread id capture,
 *     TEST_MODE handling) lives in one place (QueueWorker + EmailSender)
 *     instead of being duplicated here.
 *   - EMAIL_QUEUE already gives us PENDING/PROCESSING/SENT/RETRY/FAILED
 *     bookkeeping for free, so follow-up sends get the same reliability
 *     and visibility as initial sends without extra code.
 *   - Avoids a follow-up "succeeding" from FOLLOW_UPS' perspective while
 *     silently failing to actually send (or vice versa) since there is
 *     only one send path.
 * The trade-off is one extra polling cycle of latency (up to ~5 minutes)
 * between a follow-up becoming QUEUED and actually being SENT, which is
 * fine given follow-ups are scheduled in day-granularity by the user.
 *
 * Steps per execution (System.txt #99):
 *   1. Acquire lock.
 *   2. Find FOLLOW_UPS with status SCHEDULED (or DUE) and scheduled_at <= now.
 *   3. Check lead replied -> SKIPPED/REPLIED.
 *   4. Check suppression -> SKIPPED/SUPPRESSED.
 *   5. Check not already sent/cancelled (status guard via live re-read).
 *   6. Check MAX_FOLLOW_UPS not exceeded for the lead.
 *   7. Push to EMAIL_QUEUE, mark FOLLOW_UPS QUEUED, write event, update lead.
 *   8. Release lock.
 */

function processFollowUps() {
  var lock = LockService.getScriptLock();
  var gotLock = lock.tryLock(30000);
  if (!gotLock) {
    Logger.log('processFollowUps: could not acquire lock, another execution is likely running. Skipping this run.');
    return;
  }

  try {
    BotivateConfig.assertValid();
    var maxFollowUps = BotivateConfig.MAX_FOLLOW_UPS();
    var nowMs = Date.now();

    var allFollowUps = SheetRepository.getRows(SHEET_NAMES.FOLLOW_UPS);
    var due = allFollowUps.filter(function (fu) {
      if (fu.status !== 'SCHEDULED' && fu.status !== 'DUE') return false;
      var scheduledAt = fu.scheduled_at ? new Date(fu.scheduled_at).getTime() : 0;
      return isNaN(scheduledAt) ? true : scheduledAt <= nowMs;
    });

    Logger.log('processFollowUps: ' + due.length + ' follow-up(s) due this run.');
    if (due.length === 0) return;

    var leads = SheetRepository.getRows(SHEET_NAMES.LEADS);
    var leadsById = {};
    leads.forEach(function (l) { leadsById[l.lead_id] = l; });

    var suppressionRows = SheetRepository.getRows(SHEET_NAMES.SUPPRESSION_LIST);
    var suppressedEmails = {};
    var suppressedCompanies = {};
    suppressionRows.forEach(function (s) {
      if (s.email) suppressedEmails[String(s.email).trim().toLowerCase()] = true;
      if (s.company_id) suppressedCompanies[String(s.company_id).trim()] = true;
    });

    // Count how many follow-ups have already been SENT/QUEUED per lead,
    // to enforce MAX_FOLLOW_UPS.
    var sentOrQueuedCountByLead = {};
    allFollowUps.forEach(function (fu) {
      if (fu.status === 'SENT' || fu.status === 'QUEUED') {
        sentOrQueuedCountByLead[fu.lead_id] = (sentOrQueuedCountByLead[fu.lead_id] || 0) + 1;
      }
    });

    for (var i = 0; i < due.length; i++) {
      processOneFollowUp_(due[i], {
        leadsById: leadsById,
        suppressedEmails: suppressedEmails,
        suppressedCompanies: suppressedCompanies,
        maxFollowUps: maxFollowUps,
        sentOrQueuedCountByLead: sentOrQueuedCountByLead
      });
    }
  } catch (err) {
    Logger.log('processFollowUps: unhandled error: ' + err.message + '\n' + err.stack);
  } finally {
    lock.releaseLock();
  }
}

/**
 * Processes a single due FOLLOW_UPS row.
 * @private
 */
function processOneFollowUp_(followUpRow, ctx) {
  var followUpId = followUpRow.follow_up_id;

  // Idempotent re-check under lock.
  var live = SheetRepository.findRowById(SHEET_NAMES.FOLLOW_UPS, followUpId);
  if (!live) return;
  if (live.status !== 'SCHEDULED' && live.status !== 'DUE') {
    Logger.log('processOneFollowUp_: ' + followUpId + ' status changed to ' + live.status + ', skipping.');
    return;
  }

  var lead = live.lead_id ? ctx.leadsById[live.lead_id] : null;

  // 1. Check if lead has replied.
  if (lead && lead.status === 'REPLIED') {
    cancelFollowUp_(live, 'SKIPPED', 'REPLIED', 'Lead already replied - unnecessary follow-up not sent.');
    return;
  }
  // Also guard on any other terminal "do not contact further" statuses.
  var terminalStatuses = ['NOT_INTERESTED', 'SUPPRESSED', 'BOUNCED', 'WON', 'LOST', 'CLOSED'];
  if (lead && terminalStatuses.indexOf(lead.status) !== -1) {
    cancelFollowUp_(live, 'SKIPPED', lead.status, 'Lead status is ' + lead.status + ' - follow-up not sent.');
    return;
  }

  // 2. Check suppression (by recipient email via lead's contact, or by company).
  var recipientEmail = resolveFollowUpRecipientEmail_(live, lead);
  var isSuppressedByEmail = recipientEmail && ctx.suppressedEmails[recipientEmail.toLowerCase()] === true;
  var isSuppressedByCompany = lead && lead.company_id && ctx.suppressedCompanies[String(lead.company_id)] === true;
  if (isSuppressedByEmail || isSuppressedByCompany) {
    cancelFollowUp_(live, 'SKIPPED', 'SUPPRESSED', 'Recipient or company is on the suppression list.');
    return;
  }

  // 3. Check not already sent/cancelled - covered by the live status
  // re-check above (SCHEDULED/DUE only).

  // 4. Check MAX_FOLLOW_UPS not exceeded.
  var alreadyCount = ctx.sentOrQueuedCountByLead[live.lead_id] || 0;
  if (alreadyCount >= ctx.maxFollowUps) {
    cancelFollowUp_(live, 'SKIPPED', 'MAX_FOLLOW_UPS_REACHED', 'Lead already has ' + alreadyCount + ' follow-up(s), max is ' + ctx.maxFollowUps + '.');
    return;
  }

  if (!recipientEmail) {
    cancelFollowUp_(live, 'FAILED', 'NO_RECIPIENT_EMAIL', 'Could not resolve a recipient email for this follow-up.');
    return;
  }

  // All checks passed - push to EMAIL_QUEUE for QueueWorker to send.
  var queueId = generateId('q');
  var scheduledNow = nowIso();
  SheetRepository.appendRow(SHEET_NAMES.EMAIL_QUEUE, {
    queue_id: queueId,
    email_id: live.original_email_id || '',
    lead_id: live.lead_id || '',
    recipient_email: recipientEmail,
    sender_email: BotivateConfig.BOTIVATE_SENDER_EMAIL(),
    subject: live.subject || '',
    body: live.body || '',
    html_body: live.html_body || '',
    kind: 'FOLLOW_UP',
    priority: 'MEDIUM',
    scheduled_at: scheduledNow, // send as soon as QueueWorker next runs
    status: 'PENDING',
    attempts: 0,
    max_attempts: BotivateConfig.QUEUE_MAX_ATTEMPTS(),
    last_attempt_at: '',
    sent_at: '',
    message_id: '',
    thread_id: '',
    error_message: '',
    test_mode: BotivateConfig.EMAIL_TEST_MODE(),
    created_at: scheduledNow,
    updated_at: scheduledNow
  });

  SheetRepository.updateRowById(SHEET_NAMES.FOLLOW_UPS, followUpId, {
    status: 'QUEUED',
    updated_at: scheduledNow
  });

  logEmailEvent({
    email_id: live.original_email_id, lead_id: live.lead_id, company_id: live.company_id,
    event_type: 'FOLLOW_UP_SENT', // "sent" here means "handed off to the queue"; the
    // queue's own SENT event is written by QueueWorker once actually delivered to Gmail.
    metadata: { follow_up_id: followUpId, queue_id: queueId, sequence_number: live.sequence_number }
  });

  if (lead) {
    SheetRepository.updateRowById(SHEET_NAMES.LEADS, lead.lead_id, {
      status: 'FOLLOW_UP_SENT',
      last_activity_at: scheduledNow,
      updated_at: scheduledNow
    });
  }

  logActivity({
    lead_id: live.lead_id, company_id: live.company_id,
    activity_type: 'FOLLOW_UP_SENT',
    description: 'Follow-up #' + (live.sequence_number || '?') + ' queued for sending: "' + live.subject + '"',
    metadata: { follow_up_id: followUpId, queue_id: queueId }
  });

  ctx.sentOrQueuedCountByLead[live.lead_id] = alreadyCount + 1;
}

/**
 * Marks a follow-up as cancelled/skipped/failed with a reason, and writes
 * the corresponding EMAIL_EVENTS + ACTIVITY_LOG rows. Used for all the
 * "do not send" branches above.
 * @private
 */
function cancelFollowUp_(followUpRow, status, reason, description) {
  var ts = nowIso();
  var patch = { status: status, updated_at: ts };
  if (status === 'CANCELLED' || status === 'SKIPPED') {
    patch.cancelled_at = ts;
    patch.cancel_reason = reason;
  }
  SheetRepository.updateRowById(SHEET_NAMES.FOLLOW_UPS, followUpRow.follow_up_id, patch);

  logEmailEvent({
    email_id: followUpRow.original_email_id, lead_id: followUpRow.lead_id, company_id: followUpRow.company_id,
    event_type: 'CANCELLED',
    metadata: { follow_up_id: followUpRow.follow_up_id, reason: reason, new_status: status }
  });

  logActivity({
    lead_id: followUpRow.lead_id, company_id: followUpRow.company_id,
    activity_type: 'FOLLOW_UP_' + status,
    description: description,
    metadata: { follow_up_id: followUpRow.follow_up_id, reason: reason }
  });
}

/**
 * Resolves the recipient email for a follow-up: prefers the lead's
 * associated contact email (via CONTACTS) but falls back to the
 * recipient_email of the original EMAIL_QUEUE/EMAIL_DRAFTS row so a
 * follow-up always targets the same address the initial email went to.
 * @private
 */
function resolveFollowUpRecipientEmail_(followUpRow, lead) {
  // 1. Try the original email's queue/draft recipient (most reliable -
  //    guarantees the follow-up goes to exactly who got the initial email).
  if (followUpRow.original_email_id) {
    var originalQueueRows = SheetRepository.findRows(SHEET_NAMES.EMAIL_QUEUE, function (q) {
      return q.email_id === followUpRow.original_email_id && q.status === 'SENT';
    });
    if (originalQueueRows.length > 0) {
      return String(originalQueueRows[0].recipient_email || '').trim();
    }
    var draft = SheetRepository.findRowById(SHEET_NAMES.EMAIL_DRAFTS, followUpRow.original_email_id);
    if (draft && draft.recipient_email) {
      return String(draft.recipient_email).trim();
    }
  }
  // 2. Fall back to the lead's contact record.
  if (lead && lead.contact_id) {
    var contact = SheetRepository.findRowById(SHEET_NAMES.CONTACTS, lead.contact_id);
    if (contact && contact.email) {
      return String(contact.email).trim();
    }
  }
  return '';
}

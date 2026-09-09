/**
 * QueueWorker.gs
 * ------------------------------------------------------------------------
 * processEmailQueue() - the EMAIL_QUEUE worker (System.txt #18, #56, #98).
 *
 * Entry point intended for a time-driven trigger (installed by
 * installTriggers() in Code.gs), running every 1 minute with
 * QUEUE_BATCH_SIZE defaulting to 1, so approved emails go out one at a
 * time rather than in a burst.
 *
 * Steps per execution (System.txt #98):
 *   1. Acquire LockService lock.
 *   2. Read EMAIL_QUEUE rows with status PENDING or RETRY and
 *      scheduled_at <= now.
 *   3. Process up to QUEUE_BATCH_SIZE rows.
 *   4. For each: suppression check, lead-reply check, idempotent
 *      re-check of status under lock, send, record result.
 *   5. Release lock in a finally block.
 *
 * IDEMPOTENCY (System.txt #135): the same queue_id must never be sent
 * twice. We guarantee this by (a) holding a single global LockService
 * lock for the whole batch (so no two executions of this worker overlap),
 * and (b) re-reading each row's live status immediately before sending
 * and skipping it if it is no longer PENDING/RETRY (e.g. it was already
 * sent by a previous, still-finishing execution, or cancelled by the
 * user via the backend in the meantime).
 */

/**
 * Main entry point - run this on a time-driven trigger, or manually via
 * the "Botivate Automation > Run Queue Worker Now" menu item.
 */
function processEmailQueue() {
  var lock = LockService.getScriptLock();
  var gotLock = lock.tryLock(30000); // wait up to 30s for other executions to finish
  if (!gotLock) {
    Logger.log('processEmailQueue: could not acquire lock, another execution is likely running. Skipping this run.');
    return;
  }

  try {
    BotivateConfig.assertValid();

    var batchSize = BotivateConfig.QUEUE_BATCH_SIZE();
    var maxAttempts = BotivateConfig.QUEUE_MAX_ATTEMPTS();
    var nowMs = Date.now();

    var allQueueRows = SheetRepository.getRows(SHEET_NAMES.EMAIL_QUEUE);

    // Recover rows stuck in PROCESSING from a previous crashed execution
    // (see the try/catch added around the send in processOneQueueRow_ for
    // the fix going forward - this handles rows that got stuck BEFORE that
    // fix existed, or from any other unforeseen crash). A row is only
    // considered stuck if its last_attempt_at is older than
    // STUCK_PROCESSING_MINUTES: a genuinely in-flight row from THIS
    // process never reaches here anyway (LockService serializes runs), so
    // the only way to see PROCESSING here is a previous run that never
    // finished updating it.
    var STUCK_PROCESSING_MINUTES = 10;
    var staleCutoffMs = nowMs - STUCK_PROCESSING_MINUTES * 60 * 1000;
    allQueueRows.forEach(function (row) {
      if (row.status !== 'PROCESSING') return;
      var lastAttemptMs = row.last_attempt_at ? new Date(row.last_attempt_at).getTime() : 0;
      if (lastAttemptMs && lastAttemptMs > staleCutoffMs) return; // might still be genuinely in-flight
      var attempts = (parseInt(row.attempts, 10) || 0) + 1;
      var recoveredStatus = attempts >= maxAttempts ? 'FAILED' : 'RETRY';
      SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, row.queue_id, {
        status: recoveredStatus,
        attempts: attempts,
        error_message: 'Recovered from a stuck PROCESSING state (previous execution likely crashed, e.g. a Sheets API quota error mid-send).',
        updated_at: nowIso()
      });
      row.status = recoveredStatus; // keep the in-memory snapshot consistent for the filter below
      Logger.log('processEmailQueue: recovered stuck PROCESSING row ' + row.queue_id + ' -> ' + recoveredStatus);
    });

    var candidates = allQueueRows.filter(function (row) {
      if (row.status !== 'PENDING' && row.status !== 'RETRY') return false;
      var scheduledAt = row.scheduled_at ? new Date(row.scheduled_at).getTime() : 0;
      return isNaN(scheduledAt) ? true : scheduledAt <= nowMs;
    });

    // Stable ordering: earliest scheduled_at first, then priority (higher first) if present.
    candidates.sort(function (a, b) {
      var aTime = a.scheduled_at ? new Date(a.scheduled_at).getTime() : 0;
      var bTime = b.scheduled_at ? new Date(b.scheduled_at).getTime() : 0;
      return aTime - bTime;
    });

    var toProcess = candidates.slice(0, batchSize);
    Logger.log('processEmailQueue: ' + toProcess.length + ' of ' + candidates.length + ' eligible queue rows this run.');

    var suppressionRows = SheetRepository.getRows(SHEET_NAMES.SUPPRESSION_LIST);
    var suppressedEmails = {};
    var suppressedCompanies = {};
    suppressionRows.forEach(function (s) {
      if (s.email) suppressedEmails[String(s.email).trim().toLowerCase()] = true;
      if (s.company_id) suppressedCompanies[String(s.company_id).trim()] = true;
    });

    var leadsCache = null; // lazy-loaded, keyed by lead_id

    for (var i = 0; i < toProcess.length; i++) {
      processOneQueueRow_(toProcess[i], {
        maxAttempts: maxAttempts,
        suppressedEmails: suppressedEmails,
        suppressedCompanies: suppressedCompanies,
        getLead: function (leadId) {
          if (!leadsCache) {
            leadsCache = {};
            SheetRepository.getRows(SHEET_NAMES.LEADS).forEach(function (l) { leadsCache[l.lead_id] = l; });
          }
          return leadsCache[leadId] || null;
        }
      });
    }
  } catch (err) {
    Logger.log('processEmailQueue: unhandled error: ' + err.message + '\n' + err.stack);
  } finally {
    lock.releaseLock();
  }
}

/**
 * Processes a single EMAIL_QUEUE row (suppression/reply checks, idempotent
 * re-check, send, event/lead updates). Runs entirely inside the caller's
 * LockService lock.
 * @private
 */
function processOneQueueRow_(queueRow, ctx) {
  var queueId = queueRow.queue_id;

  // Idempotent re-check: re-read the row's live status right before we
  // act on it, in case a concurrent process changed it since our initial
  // batch read (e.g. cancelled from the backend UI moments ago).
  var liveRow = SheetRepository.findRowById(SHEET_NAMES.EMAIL_QUEUE, queueId);
  if (!liveRow) {
    Logger.log('processOneQueueRow_: queue row ' + queueId + ' vanished, skipping.');
    return;
  }
  if (liveRow.status !== 'PENDING' && liveRow.status !== 'RETRY') {
    Logger.log('processOneQueueRow_: queue row ' + queueId + ' status changed to ' + liveRow.status + ', skipping.');
    return;
  }

  var recipientEmail = String(liveRow.recipient_email || '').trim().toLowerCase();
  var lead = liveRow.lead_id ? ctx.getLead(liveRow.lead_id) : null;
  var kind = liveRow.kind || 'INITIAL';

  // --- Suppression checks (by email and by company via LEADS -> company_id) ---
  var isSuppressedByEmail = ctx.suppressedEmails[recipientEmail] === true;
  var isSuppressedByCompany = lead && lead.company_id && ctx.suppressedCompanies[String(lead.company_id)] === true;

  if (isSuppressedByEmail || isSuppressedByCompany) {
    SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, queueId, {
      status: 'SKIPPED',
      error_message: 'SUPPRESSED: recipient or company is on the suppression list.',
      updated_at: nowIso()
    });
    logEmailEvent({
      email_id: liveRow.email_id, lead_id: liveRow.lead_id, company_id: lead ? lead.company_id : '',
      event_type: 'CANCELLED', metadata: { reason: 'SUPPRESSED', queue_id: queueId }
    });
    return;
  }

  // --- Reply / do-not-send-initial checks ---
  // Do not send an INITIAL/FOLLOW_UP email to a lead that has already
  // replied, been suppressed, or been marked not interested - UNLESS this
  // is an explicit MANUAL send the user queued themselves (System.txt
  // #112: manual emails still go through EMAIL_QUEUE and full tracking,
  // and a human explicitly decided to send it).
  var blockingStatuses = ['REPLIED', 'SUPPRESSED', 'NOT_INTERESTED'];
  if (kind !== 'MANUAL' && lead && blockingStatuses.indexOf(lead.status) !== -1) {
    SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, queueId, {
      status: 'SKIPPED',
      error_message: 'SKIPPED: lead status is ' + lead.status + ' - not sending an automatic ' + kind + ' email.',
      updated_at: nowIso()
    });
    logEmailEvent({
      email_id: liveRow.email_id, lead_id: liveRow.lead_id, company_id: lead.company_id,
      event_type: 'CANCELLED', metadata: { reason: lead.status, queue_id: queueId }
    });
    return;
  }

  // --- Mark PROCESSING before sending (extra idempotency guard: if this
  // execution crashes mid-send, the row is left PROCESSING rather than
  // PENDING; a stuck PROCESSING row is a visible signal for manual review
  // rather than a silent double-send risk, since a fresh worker run only
  // picks up PENDING/RETRY rows). ---
  SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, queueId, {
    status: 'PROCESSING',
    last_attempt_at: nowIso(),
    updated_at: nowIso()
  });

  // Everything from here on (logging, the actual send, and recording the
  // result) runs inside a try/catch. Without this, ANY uncaught exception
  // here - most commonly a Google Sheets 429 quota error thrown by
  // logEmailEvent()/updateRowById() under heavy load - would leave the row
  // stuck in PROCESSING forever, since a fresh worker run only ever picks
  // up PENDING/RETRY rows (this is exactly what happened in production:
  // several rows got stuck in PROCESSING with attempts still at 0 after a
  // quota error hit mid-send). Falling back to a RETRY/FAILED update here
  // guarantees the row always leaves PROCESSING with a real outcome.
  var result;
  try {
    logEmailEvent({
      email_id: liveRow.email_id, lead_id: liveRow.lead_id, company_id: lead ? lead.company_id : '',
      event_type: 'PROCESSING', metadata: { queue_id: queueId }
    });
    result = sendQueuedEmail(liveRow);
  } catch (crashErr) {
    result = { success: false, messageId: '', threadId: '', actualRecipient: '',
               error: 'Unhandled error while sending: ' + crashErr.message };
  }

  if (result.success) {
    var sentAt = nowIso();
    SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, queueId, {
      status: 'SENT',
      sent_at: sentAt,
      message_id: result.messageId,
      thread_id: result.threadId,
      test_mode: BotivateConfig.EMAIL_TEST_MODE(),
      error_message: '',
      updated_at: sentAt
    });

    logEmailEvent({
      email_id: liveRow.email_id, lead_id: liveRow.lead_id, company_id: lead ? lead.company_id : '',
      event_type: 'SENT', message_id: result.messageId,
      metadata: {
        queue_id: queueId,
        intended_recipient: liveRow.recipient_email,
        actual_recipient: result.actualRecipient,
        test_mode: BotivateConfig.EMAIL_TEST_MODE(),
        kind: kind
      }
    });

    // Only advance LEADS.status to CONTACTED if it's still in a
    // pre-contact state (QUEUED) - never clobber a status the lead has
    // since moved past (e.g. don't downgrade REPLIED/FOLLOW_UP_SENT back
    // to CONTACTED for a late-processed manual/follow-up send).
    if (lead && (lead.status === 'QUEUED' || lead.status === 'APPROVED' || lead.status === 'EMAIL_DRAFTED')) {
      SheetRepository.updateRowById(SHEET_NAMES.LEADS, lead.lead_id, {
        status: 'CONTACTED',
        last_activity_at: sentAt,
        updated_at: sentAt
      });
    } else if (lead) {
      SheetRepository.updateRowById(SHEET_NAMES.LEADS, lead.lead_id, {
        last_activity_at: sentAt,
        updated_at: sentAt
      });
    }

    logActivity({
      lead_id: liveRow.lead_id, company_id: lead ? lead.company_id : '',
      activity_type: 'EMAIL_SENT',
      description: 'Email sent (' + kind + '): "' + liveRow.subject + '" to ' + liveRow.recipient_email,
      metadata: { queue_id: queueId, message_id: result.messageId, thread_id: result.threadId }
    });
  } else {
    var attempts = (parseInt(liveRow.attempts, 10) || 0) + 1;
    var newStatus = attempts >= ctx.maxAttempts ? 'FAILED' : 'RETRY';
    var attemptTime = nowIso();

    SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, queueId, {
      status: newStatus,
      attempts: attempts,
      last_attempt_at: attemptTime,
      error_message: result.error,
      updated_at: attemptTime
    });

    logEmailEvent({
      email_id: liveRow.email_id, lead_id: liveRow.lead_id, company_id: lead ? lead.company_id : '',
      event_type: 'FAILED',
      metadata: { queue_id: queueId, attempts: attempts, status: newStatus, error: result.error }
    });

    logActivity({
      lead_id: liveRow.lead_id, company_id: lead ? lead.company_id : '',
      activity_type: 'EMAIL_SEND_FAILED',
      description: 'Send attempt ' + attempts + ' failed for queue ' + queueId + ': ' + result.error,
      metadata: { queue_id: queueId, status: newStatus }
    });
  }
}

/**
 * ONE-TIME CLEANUP UTILITY - not on any trigger, run manually once from the
 * Apps Script editor's function dropdown after a code fix that resolves a
 * known send failure. Resets every EMAIL_QUEUE row whose error_message
 * contains the given substring back to RETRY with attempts=0, so the fixed
 * QueueWorker code gets a fresh chance to send them on its next 1-minute
 * run, instead of them sitting FAILED forever because they already
 * exhausted max_attempts on a bug that is now fixed.
 *
 * Specifically written for the "Utilities.htmlEncode is not a function"
 * bug fixed in EmailSender.gs - run this ONCE after deploying that fix.
 * Safe to re-run (a no-op if no matching rows remain).
 */
function resetHtmlEncodeFailures() {
  var marker = 'Utilities.htmlEncode is not a function';
  var rows = SheetRepository.getRows(SHEET_NAMES.EMAIL_QUEUE);
  var resetCount = 0;
  rows.forEach(function (row) {
    if (row.status === 'FAILED' && String(row.error_message || '').indexOf(marker) !== -1) {
      SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, row.queue_id, {
        status: 'RETRY',
        attempts: 0,
        error_message: 'Reset by resetHtmlEncodeFailures() after the Utilities.htmlEncode fix.',
        updated_at: nowIso()
      });
      resetCount++;
    }
  });
  var message = 'resetHtmlEncodeFailures: reset ' + resetCount + ' row(s) from FAILED back to RETRY.';
  Logger.log(message);
  try {
    SpreadsheetApp.getUi().alert('Botivate Automation', message, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless - logging is sufficient.
  }
}

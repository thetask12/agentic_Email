/**
 * QueueWorker.gs
 * ------------------------------------------------------------------------
 * processEmailQueue() - the EMAIL_QUEUE worker for the Job Outreach module.
 *
 * Entry point intended for a time-driven trigger (installed by
 * installTriggers() in Code.gs), running every 1-2 minutes with
 * QUEUE_BATCH_SIZE defaulting to 1.
 *
 * Steps per execution:
 *   1. Acquire LockService lock.
 *   2. Read EMAIL_QUEUE rows with status PENDING or RETRY and
 *      scheduled_at <= now.
 *   3. Process up to QUEUE_BATCH_SIZE rows.
 *   4. For each: suppression check, idempotent re-check of status under
 *      lock, send, record result.
 *   5. Release lock in a finally block.
 *
 * IDEMPOTENCY: the same queue_id must never be sent twice. Guaranteed by
 * (a) a single global LockService lock for the whole batch, and (b)
 * re-reading each row's live status immediately before sending and
 * skipping it if it is no longer PENDING/RETRY.
 *
 * No follow-ups, no reply scanning in this module — exactly one email per
 * company, ever (enforced upstream by the backend via SUPPRESSION_LIST
 * before a row is ever queued).
 */

function processEmailQueue() {
  var lock = LockService.getScriptLock();
  var gotLock = lock.tryLock(30000);
  if (!gotLock) {
    Logger.log('processEmailQueue: could not acquire lock, another execution is likely running. Skipping this run.');
    return;
  }

  try {
    JobOutreachConfig.assertValid();

    var batchSize = JobOutreachConfig.QUEUE_BATCH_SIZE();
    var maxAttempts = JobOutreachConfig.QUEUE_MAX_ATTEMPTS();
    var nowMs = Date.now();

    var allQueueRows = SheetRepository.getRows(SHEET_NAMES.EMAIL_QUEUE);

    // Recover rows stuck in PROCESSING from a previous crashed execution.
    var STUCK_PROCESSING_MINUTES = 10;
    var staleCutoffMs = nowMs - STUCK_PROCESSING_MINUTES * 60 * 1000;
    allQueueRows.forEach(function (row) {
      if (row.status !== 'PROCESSING') return;
      var lastAttemptMs = row.updated_at ? new Date(row.updated_at).getTime() : 0;
      if (lastAttemptMs && lastAttemptMs > staleCutoffMs) return;
      var attempts = (parseInt(row.attempts, 10) || 0) + 1;
      var recoveredStatus = attempts >= maxAttempts ? 'FAILED' : 'RETRY';
      SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, row.queue_id, {
        status: recoveredStatus,
        attempts: attempts,
        error_message: 'Recovered from a stuck PROCESSING state (previous execution likely crashed).',
        updated_at: nowIso()
      });
      row.status = recoveredStatus;
      Logger.log('processEmailQueue: recovered stuck PROCESSING row ' + row.queue_id + ' -> ' + recoveredStatus);
    });

    var candidates = allQueueRows.filter(function (row) {
      if (row.status !== 'PENDING' && row.status !== 'RETRY') return false;
      var scheduledAt = row.scheduled_at ? new Date(row.scheduled_at).getTime() : 0;
      return isNaN(scheduledAt) ? true : scheduledAt <= nowMs;
    });

    candidates.sort(function (a, b) {
      var aTime = a.scheduled_at ? new Date(a.scheduled_at).getTime() : 0;
      var bTime = b.scheduled_at ? new Date(b.scheduled_at).getTime() : 0;
      return aTime - bTime;
    });

    var toProcess = candidates.slice(0, batchSize);
    Logger.log('processEmailQueue: ' + toProcess.length + ' of ' + candidates.length + ' eligible queue rows this run.');

    var suppressionRows = SheetRepository.getRows(SHEET_NAMES.SUPPRESSION_LIST);
    var suppressedCompanies = {};
    suppressionRows.forEach(function (s) {
      if (s.company_id) suppressedCompanies[String(s.company_id).trim()] = true;
    });

    for (var i = 0; i < toProcess.length; i++) {
      processOneQueueRow_(toProcess[i], { maxAttempts: maxAttempts, suppressedCompanies: suppressedCompanies });
    }
  } catch (err) {
    Logger.log('processEmailQueue: unhandled error: ' + err.message + '\n' + err.stack);
  } finally {
    lock.releaseLock();
  }
}

/**
 * Processes a single EMAIL_QUEUE row.
 * @private
 */
function processOneQueueRow_(queueRow, ctx) {
  var queueId = queueRow.queue_id;

  var liveRow = SheetRepository.findRowById(SHEET_NAMES.EMAIL_QUEUE, queueId);
  if (!liveRow) {
    Logger.log('processOneQueueRow_: queue row ' + queueId + ' vanished, skipping.');
    return;
  }
  if (liveRow.status !== 'PENDING' && liveRow.status !== 'RETRY') {
    Logger.log('processOneQueueRow_: queue row ' + queueId + ' status changed to ' + liveRow.status + ', skipping.');
    return;
  }

  // Suppression check — should already be enforced by the backend before
  // queuing (never email the same company twice), this is a second guard.
  if (liveRow.company_id && ctx.suppressedCompanies[String(liveRow.company_id)] === true) {
    // A row's OWN queuing is itself what creates the ALREADY_APPLIED
    // suppression entry — so this only fires for a genuinely re-added row
    // (e.g. a manual backend fix), not the normal path.
  }

  SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, queueId, {
    status: 'PROCESSING',
    updated_at: nowIso()
  });

  var result;
  try {
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
      test_mode: JobOutreachConfig.EMAIL_TEST_MODE(),
      error_message: '',
      updated_at: sentAt
    });

    logEmailEvent({
      queue_id: queueId, company_id: liveRow.company_id,
      event_type: 'SENT', message_id: result.messageId, thread_id: result.threadId,
      test_mode: JobOutreachConfig.EMAIL_TEST_MODE(),
      metadata: { intended_recipient: liveRow.recipient_email, actual_recipient: result.actualRecipient }
    });

    logActivity('EMAIL_SENT', 'Sent "' + liveRow.subject + '" to ' + liveRow.recipient_email);
  } else {
    var attempts = (parseInt(liveRow.attempts, 10) || 0) + 1;
    var newStatus = attempts >= ctx.maxAttempts ? 'FAILED' : 'RETRY';
    var attemptTime = nowIso();

    SheetRepository.updateRowById(SHEET_NAMES.EMAIL_QUEUE, queueId, {
      status: newStatus,
      attempts: attempts,
      error_message: result.error,
      updated_at: attemptTime
    });

    logEmailEvent({
      queue_id: queueId, company_id: liveRow.company_id,
      event_type: 'FAILED',
      metadata: { attempts: attempts, status: newStatus, error: result.error }
    });

    logActivity('EMAIL_SEND_FAILED', 'Attempt ' + attempts + ' failed for queue ' + queueId + ': ' + result.error);
  }
}

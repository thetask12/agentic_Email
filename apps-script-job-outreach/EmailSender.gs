/**
 * EmailSender.gs
 * ------------------------------------------------------------------------
 * Sends a single EMAIL_QUEUE row via GmailApp and returns the resulting
 * Gmail message ID + thread ID for storage.
 *
 * Plain-text application email only — NO inline images, NO banner, NO
 * signature GIF (per docs/job-outreach-schema.md "Email content rules").
 * The resume PDF is attached as a normal attachment (options.attachments),
 * fetched via DriveApp.getFileById(RESUME_DRIVE_FILE_ID).getBlob() — a
 * plain READ, so drive.readonly scope is sufficient (no setSharing/public-
 * URL trick needed, unlike the other Apps Script project's animated-GIF
 * signature).
 *
 * TEST MODE: when EMAIL_TEST_MODE is true, the actual Gmail recipient is
 * redirected to TEST_EMAIL, but the row's own recipient_email column (the
 * real intended recipient) is left untouched — QueueWorker keeps that value
 * intact in EMAIL_QUEUE and records it in EMAIL_EVENTS metadata.
 */

/**
 * Sends an email for the given EMAIL_QUEUE row.
 * @param {Object} queueRow A row object from EMAIL_QUEUE.
 * @return {{success: boolean, messageId: string, threadId: string,
 *   actualRecipient: string, error: string}}
 */
function sendQueuedEmail(queueRow) {
  var intendedRecipient = String(queueRow.recipient_email || '').trim();
  var testMode = JobOutreachConfig.EMAIL_TEST_MODE();
  var actualRecipient = intendedRecipient;

  if (!isValidEmail(intendedRecipient) && !testMode) {
    return { success: false, messageId: '', threadId: '', actualRecipient: '', error: 'Invalid recipient email: "' + intendedRecipient + '"' };
  }

  if (testMode) {
    var testEmail = JobOutreachConfig.TEST_EMAIL();
    if (!testEmail || !isValidEmail(testEmail)) {
      return { success: false, messageId: '', threadId: '', actualRecipient: '', error: 'EMAIL_TEST_MODE is on but TEST_EMAIL is missing/invalid.' };
    }
    actualRecipient = testEmail;
  }

  var senderName = JobOutreachConfig.SENDER_NAME();
  var subject = String(queueRow.subject || '(no subject)');
  var plainBody = String(queueRow.body || '');

  var options = { name: senderName || '' };

  var resumeBlob = getResumeBlob_();
  if (resumeBlob) {
    options.attachments = [resumeBlob];
  } else {
    Logger.log('sendQueuedEmail: resume blob unavailable — sending without attachment. Check RESUME_DRIVE_FILE_ID and Drive sharing.');
  }

  try {
    GmailApp.sendEmail(actualRecipient, subject, plainBody, options);
  } catch (sendErr) {
    return { success: false, messageId: '', threadId: '', actualRecipient: actualRecipient, error: 'GmailApp.sendEmail failed: ' + sendErr.message };
  }

  var lookup = { messageId: '', threadId: '' };
  try {
    lookup = findJustSentMessage_(actualRecipient, subject);
  } catch (lookupErr) {
    Logger.log('Warning: sent email but failed to look up message/thread id: ' + lookupErr.message);
  }

  if (lookup.threadId) {
    try {
      applySentLabelToThread_(lookup.threadId);
    } catch (labelErr) {
      Logger.log('Warning: failed to apply SENT label to thread ' + lookup.threadId + ': ' + labelErr.message);
    }
  }

  return {
    success: true,
    messageId: lookup.messageId || '',
    threadId: lookup.threadId || '',
    actualRecipient: actualRecipient,
    error: ''
  };
}

/**
 * Searches Gmail's Sent folder for the message we just sent, matching by
 * recipient + exact subject, and returns the most recent match.
 * @private
 */
function findJustSentMessage_(recipient, subject) {
  var safeSubject = subject.replace(/"/g, '\\"');
  var query = 'in:sent to:(' + recipient + ') subject:"' + safeSubject + '"';
  var threads = GmailApp.search(query, 0, 5);
  if (threads.length === 0) {
    return { messageId: '', threadId: '' };
  }
  var thread = threads[0];
  var messages = thread.getMessages();
  var lastMessage = messages[messages.length - 1];
  return {
    messageId: lastMessage.getId(),
    threadId: thread.getId()
  };
}

/**
 * Fetches the resume PDF blob from Drive by RESUME_DRIVE_FILE_ID. Cached
 * per script execution. Returns null (never throws) if not configured or
 * the file can't be read — callers must treat that as "send without
 * attachment", not "fail the whole send", though in practice you should fix
 * this before relying on real sends (a resume-less application email
 * defeats the point of this system).
 * @private
 */
var _resumeBlobCache_ = undefined;
function getResumeBlob_() {
  if (_resumeBlobCache_ !== undefined) return _resumeBlobCache_;
  var blob = null;
  try {
    var fileId = JobOutreachConfig.RESUME_DRIVE_FILE_ID();
    if (fileId) {
      blob = DriveApp.getFileById(fileId).getBlob();
    } else {
      Logger.log('getResumeBlob_: RESUME_DRIVE_FILE_ID is not configured.');
    }
  } catch (err) {
    Logger.log('getResumeBlob_: failed to fetch resume from Drive: ' + err.message);
    blob = null;
  }
  _resumeBlobCache_ = blob;
  return blob;
}

/**
 * Applies the configured SENT_LABEL to a thread, creating the label if it
 * does not already exist.
 * @private
 */
function applySentLabelToThread_(threadId) {
  var labelName = JobOutreachConfig.SENT_LABEL();
  if (!labelName) return;
  var label = GmailApp.getUserLabelByName(labelName);
  if (!label) {
    label = GmailApp.createLabel(labelName);
  }
  var thread = GmailApp.getThreadById(threadId);
  if (thread) {
    thread.addLabel(label);
  }
}

/**
 * ONE-TIME DIAGNOSTIC - run manually to confirm the resume PDF can be read
 * from Drive, without sending a real email.
 */
function testResumeAsset() {
  var fileId = JobOutreachConfig.RESUME_DRIVE_FILE_ID();
  var lines = ['RESUME_DRIVE_FILE_ID = "' + fileId + '"'];
  var blob = getResumeBlob_();
  if (blob) {
    lines.push('OK: resume fetched, ' + blob.getBytes().length + ' bytes, name="' + blob.getName() + '".');
  } else {
    lines.push('FAIL: could not fetch resume blob. Check the file id and that this Google account has at least view access.');
  }
  var summary = lines.join('\n');
  Logger.log(summary);
  try {
    SpreadsheetApp.getUi().alert('Resume Asset Diagnostic', summary, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless - logging is sufficient.
  }
}

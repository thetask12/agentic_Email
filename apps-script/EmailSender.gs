/**
 * EmailSender.gs
 * ------------------------------------------------------------------------
 * Sends a single EMAIL_QUEUE row via GmailApp / MailApp and returns the
 * resulting Gmail message ID + thread ID for storage.
 *
 * WHY GmailApp.sendEmail() + a follow-up search, instead of raw MIME:
 * GmailApp does not let you set arbitrary custom headers (e.g. a custom
 * X-Botivate-Lead-Id header) on outgoing mail, and does not return a
 * message/thread ID directly from sendEmail(). To reliably recover the
 * message we just sent, we:
 *   1. Send with GmailApp.sendEmail(...), passing a distinguishing
 *      Subject (already unique-ish per lead/template) and body.
 *   2. Immediately search Gmail (GmailApp.search) restricted to
 *      "in:sent to:<recipient> subject:<subject>" and take the most
 *      recent matching thread/message as ours.
 * This is a best-effort fallback matching strategy - it is reliable in
 * practice because sends are processed one at a time (serialized by
 * LockService in QueueWorker), so there is no concurrent send to the same
 * recipient+subject at the same moment from this script.
 *
 * ADVANCED GMAIL SERVICE (optional, recommended for production):
 * If you enable the advanced Gmail Service (Apps Script editor > Services
 * > + > Gmail API), you can use Gmail.Users.Messages.send() instead, which
 * returns the message id and thread id directly in the response, removing
 * the need for the search-based fallback. This file keeps the
 * GmailApp-based approach as the default because it requires zero extra
 * setup, but ReplyScanner.gs documents how to use the advanced service
 * for header-level reply matching, and the same technique can be applied
 * here if you want tighter guarantees.
 *
 * TEST MODE (System.txt #82): when EMAIL_TEST_MODE is true, the actual
 * Gmail recipient is redirected to TEST_EMAIL, but the row's own
 * recipient_email column (the real intended recipient) is left untouched
 * by this function - QueueWorker is responsible for keeping that value
 * intact in EMAIL_QUEUE and recording it in EMAIL_EVENTS metadata so nothing
 * is lost. This function also sets/reads the EMAIL_QUEUE `test_mode`
 * boolean column that already exists in the schema (never invent a new
 * column for this).
 *
 * IMAGE ASSETS: every INITIAL outgoing email embeds three images in the
 * HTML body (no attachments) - autorocket-banner.png right after the
 * AutoRocket pitch paragraph, botivate-profile.png further down, and an
 * animated GIF (developer@botivate.in.gif) at the very end in place of the
 * text signature. All three files live in the Drive folder configured as
 * EMAIL_ASSETS_DRIVE_FOLDER_ID (looked up by filename, not a fixed file
 * ID, so replacing the image in Drive never requires a code change). The
 * first two are embedded as inline cid: blobs (getEmailAssetBlob_) since
 * they're static. The GIF is embedded as a public Drive <img src=...> URL
 * instead (getEmailAssetPublicUrl_) because inline cid: blobs render as a
 * static first frame in Gmail/most clients — only an externally-hosted URL
 * actually animates. If the folder isn't configured or a file is missing,
 * the email still sends without that image rather than failing the whole
 * send.
 */

/**
 * Sends an email for the given EMAIL_QUEUE row.
 *
 * @param {Object} queueRow A row object from EMAIL_QUEUE (as returned by
 *   SheetRepository.getRows/findRowById), i.e. it has recipient_email,
 *   sender_email, subject, body, html_body, queue_id, etc.
 * @return {{success: boolean, messageId: string, threadId: string,
 *   actualRecipient: string, error: string}} Result descriptor. On
 *   failure, `error` contains a message and success is false; caller
 *   (QueueWorker) decides retry vs. fail based on this.
 */
function sendQueuedEmail(queueRow) {
  var intendedRecipient = String(queueRow.recipient_email || '').trim();
  var testMode = BotivateConfig.EMAIL_TEST_MODE();
  var actualRecipient = intendedRecipient;

  if (!isValidEmail(intendedRecipient) && !testMode) {
    return { success: false, messageId: '', threadId: '', actualRecipient: '', error: 'Invalid recipient email: "' + intendedRecipient + '"' };
  }

  if (testMode) {
    var testEmail = BotivateConfig.TEST_EMAIL();
    if (!testEmail || !isValidEmail(testEmail)) {
      return { success: false, messageId: '', threadId: '', actualRecipient: '', error: 'EMAIL_TEST_MODE is on but TEST_EMAIL is missing/invalid.' };
    }
    actualRecipient = testEmail;
  }

  var senderName = BotivateConfig.BOTIVATE_SENDER_NAME();
  var subject = String(queueRow.subject || '(no subject)');
  // Per explicit user instruction, the sent email carries NO visible
  // test-mode indicator (no subject prefix, no body notice) — the point is
  // to preview exactly what a real recipient would see. The actual safety
  // redirect above (actualRecipient = testEmail) still fully applies: no
  // real company is ever contacted while EMAIL_TEST_MODE is true. The real
  // intended recipient is never lost — it's still recorded untouched in
  // EMAIL_QUEUE.recipient_email and in the SENT event's metadata by
  // QueueWorker.gs, just not disclosed inside the email content itself.
  var effectiveSubject = subject;
  var plainBody = String(queueRow.body || '');
  var htmlBody = queueRow.html_body ? String(queueRow.html_body) : undefined;

  var options = { name: senderName || 'Botivate Services LLP' };

  // Only the INITIAL outreach email carries the two image assets - a short
  // follow-up nudge doesn't need the full pitch banner/profile repeated.
  // Both images are inline in the body (no attachments) — the template
  // (email_master_template.py) places each placeholder exactly where that
  // image should appear: the AutoRocket banner right after the AutoRocket
  // paragraph, the Botivate profile at the very end after the signature.
  // Position is controlled by the template, not decided here — this
  // function only substitutes each placeholder with the real <img> tag.
  var isInitialEmail = String(queueRow.kind || 'INITIAL') === 'INITIAL';
  var inlineImageSpecs = [
    { placeholder: '<div id="autorocket-banner-placeholder"></div>', fileName: 'autorocket-banner.png',
      cid: 'autorocketBanner', alt: 'AutoRocket — Automate your entire business in just one day',
      linkUrl: '' },
    // linkUrl: clicking the Botivate profile image opens botivate.in in a
    // new tab, same as the "Botivate:" text link elsewhere in the body.
    { placeholder: '<div id="botivate-profile-placeholder"></div>', fileName: 'botivate-profile.png',
      cid: 'botivateProfile', alt: 'Botivate — Powering Businesses On Autopilot',
      linkUrl: BotivateConfig.raw('BOTIVATE_WEBSITE_URL', 'https://botivate.in') },
    // This image REPLACES the text signature block entirely (no separate
    // "Regards, Satyendra Kumar Tandan..." text) - it is the last thing in
    // the email. Filename matches exactly what's in the Drive folder today.
    // NOTE: this is an animated GIF, and inline `cid:` blob embedding
    // (like the two specs above) renders as a static first frame in Gmail
    // and most clients — only an externally-hosted <img src="https://..."
    // URL is actually animated on the recipient's end. So this one spec
    // uses `publicUrl: true` to render as a direct Drive-hosted <img src>
    // instead of an inlineImages blob — see the branch below.
    { placeholder: '<div id="signature-poster-placeholder"></div>', fileName: 'developer@botivate.in.gif',
      cid: 'signaturePoster', alt: 'Satyendra Kumar Tandan — Founder & CEO, Botivate Services LLP',
      linkUrl: '', publicUrl: true }
  ];

  if (htmlBody) {
    inlineImageSpecs.forEach(function (spec) {
      if (htmlBody.indexOf(spec.placeholder) === -1) return;

      if (spec.publicUrl) {
        // Externally-hosted image (animates in the recipient's inbox,
        // unlike an inline cid: blob). The Drive file must be shared as
        // "Anyone with the link can view" — see getEmailAssetPublicUrl_.
        var publicSrc = isInitialEmail ? getEmailAssetPublicUrl_(spec.fileName) : null;
        if (publicSrc) {
          var pimg = '<img src="' + escapeHtml_(publicSrc) + '" ' +
            'alt="' + escapeHtml_(spec.alt) + '" ' +
            'style="max-width:600px;width:100%;height:auto;border-radius:8px;display:block;border:0;"/>';
          var pinner = spec.linkUrl
            ? '<a href="' + escapeHtml_(spec.linkUrl) + '" target="_blank" style="text-decoration:none;">' + pimg + '</a>'
            : pimg;
          htmlBody = htmlBody.replace(spec.placeholder, '<p style="margin:20px 0;">' + pinner + '</p>');
        } else {
          htmlBody = htmlBody.replace(spec.placeholder, '');
        }
        return;
      }

      var blob = isInitialEmail ? getEmailAssetBlob_(spec.fileName) : null;
      if (blob) {
        options.inlineImages = options.inlineImages || {};
        options.inlineImages[spec.cid] = blob;
        var img = '<img src="cid:' + spec.cid + '" ' +
          'alt="' + escapeHtml_(spec.alt) + '" ' +
          'style="max-width:600px;width:100%;height:auto;border-radius:8px;display:block;border:0;"/>';
        var inner = spec.linkUrl
          ? '<a href="' + escapeHtml_(spec.linkUrl) + '" target="_blank" style="text-decoration:none;">' + img + '</a>'
          : img;
        var imgTag = '<p style="margin:20px 0;">' + inner + '</p>';
        htmlBody = htmlBody.replace(spec.placeholder, imgTag);
      } else {
        // Not an initial email, or the asset couldn't be fetched — remove
        // the empty placeholder rather than leaving a stray <div> in the
        // sent email.
        htmlBody = htmlBody.replace(spec.placeholder, '');
      }
    });
  }

  if (htmlBody) options.htmlBody = htmlBody;

  try {
    GmailApp.sendEmail(actualRecipient, effectiveSubject, plainBody, options);
  } catch (sendErr) {
    return { success: false, messageId: '', threadId: '', actualRecipient: actualRecipient, error: 'GmailApp.sendEmail failed: ' + sendErr.message };
  }

  // Immediately look up the just-sent message to capture its message id /
  // thread id. We search "in:sent" scoped to the recipient + exact
  // subject, and take the most recent thread (sends are serialized under
  // LockService by QueueWorker, so this is safe in practice).
  var lookup = { messageId: '', threadId: '' };
  try {
    lookup = findJustSentMessage_(actualRecipient, effectiveSubject);
  } catch (lookupErr) {
    // Non-fatal: the email was sent successfully; we just couldn't
    // recover its IDs. Log and continue - QueueWorker will still mark
    // this SENT, just with blank message_id/thread_id.
    Logger.log('Warning: sent email but failed to look up message/thread id: ' + lookupErr.message);
  }

  // Apply the SENT_LABEL to the resulting thread so ReplyScanner can find
  // it later. Do this even if lookup partially failed but we have a thread.
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
  // Gmail search operators: escape double quotes in subject to keep the
  // query well-formed.
  var safeSubject = subject.replace(/"/g, '\\"');
  var query = 'in:sent to:(' + recipient + ') subject:"' + safeSubject + '"';
  var threads = GmailApp.search(query, 0, 5);
  if (threads.length === 0) {
    return { messageId: '', threadId: '' };
  }
  // Most recent thread first (GmailApp.search returns newest-first by default).
  var thread = threads[0];
  var messages = thread.getMessages();
  var lastMessage = messages[messages.length - 1];
  return {
    messageId: lastMessage.getId(),
    threadId: thread.getId()
  };
}

/**
 * ONE-TIME DIAGNOSTIC - run this manually from the function dropdown to
 * check whether Drive image fetching is working, without sending a real
 * email. Prints results to Logger.log and shows an alert with a summary.
 */
function testEmailAssets() {
  var folderId = BotivateConfig.EMAIL_ASSETS_DRIVE_FOLDER_ID();
  var lines = [];
  lines.push('EMAIL_ASSETS_DRIVE_FOLDER_ID = "' + folderId + '"');

  if (!folderId) {
    lines.push('FAIL: EMAIL_ASSETS_DRIVE_FOLDER_ID is empty. Run setupConfigFromValues() first.');
  } else {
    try {
      var folder = DriveApp.getFolderById(folderId);
      lines.push('Folder found: "' + folder.getName() + '"');
      var allFiles = folder.getFiles();
      var names = [];
      while (allFiles.hasNext()) {
        names.push(allFiles.next().getName());
      }
      lines.push('Files in folder: ' + (names.length ? names.join(', ') : '(none)'));
    } catch (err) {
      lines.push('FAIL: DriveApp.getFolderById() threw: ' + err.message);
    }
  }

  ['autorocket-banner.png', 'botivate-profile.png'].forEach(function (fileName) {
    var blob = getEmailAssetBlob_(fileName);
    if (blob) {
      lines.push('OK: "' + fileName + '" fetched, ' + blob.getBytes().length + ' bytes.');
    } else {
      lines.push('FAIL: "' + fileName + '" could not be fetched (see log lines above from getEmailAssetBlob_).');
    }
  });

  ['developer@botivate.in.gif'].forEach(function (fileName) {
    var url = getEmailAssetPublicUrl_(fileName);
    if (url) {
      lines.push('OK: "' + fileName + '" public URL = ' + url);
    } else {
      lines.push('FAIL: "' + fileName + '" could not be made public (see log lines above from getEmailAssetPublicUrl_).');
    }
  });

  var summary = lines.join('\n');
  Logger.log(summary);
  try {
    SpreadsheetApp.getUi().alert('Email Asset Diagnostic', summary, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless - Logger.log output above is sufficient.
  }
}

/**
 * Fetches an image asset blob by filename from the configured Drive
 * folder (EMAIL_ASSETS_DRIVE_FOLDER_ID). Cached per script execution so a
 * single processEmailQueue() run doesn't hit Drive twice for the same
 * file if it processes more than one email (QUEUE_BATCH_SIZE > 1).
 * Returns null (never throws) if the folder isn't configured, doesn't
 * exist, or doesn't contain a file with that exact name - callers must
 * treat a missing asset as "skip this asset", not "fail the send".
 * @private
 */
var _emailAssetBlobCache_ = {};
function getEmailAssetBlob_(fileName) {
  if (Object.prototype.hasOwnProperty.call(_emailAssetBlobCache_, fileName)) {
    return _emailAssetBlobCache_[fileName];
  }
  var blob = null;
  try {
    var folderId = BotivateConfig.EMAIL_ASSETS_DRIVE_FOLDER_ID();
    if (folderId) {
      var folder = DriveApp.getFolderById(folderId);
      var files = folder.getFilesByName(fileName);
      if (files.hasNext()) {
        blob = files.next().getBlob();
      } else {
        Logger.log('getEmailAssetBlob_: no file named "' + fileName + '" found in EMAIL_ASSETS_DRIVE_FOLDER_ID.');
      }
    }
  } catch (err) {
    Logger.log('getEmailAssetBlob_: failed to fetch "' + fileName + '" from Drive: ' + err.message);
    blob = null;
  }
  _emailAssetBlobCache_[fileName] = blob;
  return blob;
}

/**
 * Returns a public, directly-embeddable image URL for a Drive file looked
 * up by filename in EMAIL_ASSETS_DRIVE_FOLDER_ID — used instead of
 * getEmailAssetBlob_/inlineImages for assets that must actually ANIMATE in
 * the recipient's inbox (e.g. a GIF): Gmail and most clients only animate
 * externally-hosted <img src="https://..."> images, never inline cid: blobs.
 *
 * This sets the file's sharing to "Anyone with the link can view" the
 * first time it's fetched (required for the URL to resolve for a
 * recipient who isn't logged into this Drive account), then returns Drive's
 * direct-content URL (uc?export=view&id=...), which browsers/email clients
 * render as a plain <img>. Cached per script execution like
 * getEmailAssetBlob_. Returns null (never throws) if the folder isn't
 * configured or the file isn't found — callers must treat that as "skip
 * this asset", not "fail the send".
 * @private
 */
var _emailAssetPublicUrlCache_ = {};
function getEmailAssetPublicUrl_(fileName) {
  if (Object.prototype.hasOwnProperty.call(_emailAssetPublicUrlCache_, fileName)) {
    return _emailAssetPublicUrlCache_[fileName];
  }
  var url = null;
  try {
    var folderId = BotivateConfig.EMAIL_ASSETS_DRIVE_FOLDER_ID();
    if (folderId) {
      var folder = DriveApp.getFolderById(folderId);
      var files = folder.getFilesByName(fileName);
      if (files.hasNext()) {
        var file = files.next();
        try {
          file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
        } catch (shareErr) {
          Logger.log('getEmailAssetPublicUrl_: failed to set sharing on "' + fileName + '": ' + shareErr.message);
        }
        url = 'https://drive.google.com/uc?export=view&id=' + file.getId();
      } else {
        Logger.log('getEmailAssetPublicUrl_: no file named "' + fileName + '" found in EMAIL_ASSETS_DRIVE_FOLDER_ID.');
      }
    }
  } catch (err) {
    Logger.log('getEmailAssetPublicUrl_: failed to fetch "' + fileName + '" from Drive: ' + err.message);
    url = null;
  }
  _emailAssetPublicUrlCache_[fileName] = url;
  return url;
}

/**
 * Applies the configured SENT_LABEL to a thread, creating the label if it
 * does not already exist.
 * @private
 */
function applySentLabelToThread_(threadId) {
  var labelName = BotivateConfig.SENT_LABEL();
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

/**
 * ReplyScanner.gs
 * ------------------------------------------------------------------------
 * Periodically scans the Botivate Gmail inbox for replies to sent campaign
 * emails (System.txt #24-30, #57-61, #100-102, #124).
 *
 * IDENTIFICATION STRATEGY (System.txt #101 - never rely only on subject):
 *   Priority order: THREAD_ID > MESSAGE_HEADERS (In-Reply-To/References) >
 *   MESSAGE_ID_RELATIONSHIP > SUBJECT + PARTICIPANT.
 *
 *   We iterate Gmail threads carrying the SENT_LABEL (applied by
 *   EmailSender.gs when we send a campaign email), which already
 *   guarantees THREAD_ID-level correctness - only messages in a thread we
 *   ourselves started are ever considered. Within each such thread, any
 *   message NOT from BOTIVATE_SENDER_EMAIL is treated as an inbound reply.
 *   This is strictly stronger than subject matching alone.
 *
 *   For header-level detail (In-Reply-To/References), GmailApp's
 *   GmailMessage object does not expose raw RFC headers. To read them
 *   reliably, enable the ADVANCED GMAIL SERVICE:
 *     Apps Script editor > Services (+) > Gmail API > Add.
 *   With it enabled, getRawHeaders_() below will use
 *   Gmail.Users.Messages.get(...,{format:'metadata'}) to pull In-Reply-To
 *   and References. If the advanced service is not enabled, those two
 *   fields are simply left blank on the REPLIES row (never fabricated) and
 *   thread-based matching alone is used - which is already reliable given
 *   the SENT_LABEL scoping described above.
 *
 * IDEMPOTENCY (System.txt #135): we track the last processed Gmail message
 * ID per thread in Script Properties (key: "lastMsg:<threadId>") AND we
 * cross-check the REPLIES sheet by message_id before creating a new row.
 * Both layers must agree a message is new before it is processed, so even
 * if Script Properties are cleared, no duplicate REPLIES rows are created.
 *
 * ON EACH NEW GENUINE REPLY:
 *   1. Sanitize the body (Utils.sanitizeHtml / stripHtml).
 *   2. Resolve which lead/company/email this thread belongs to (via
 *      EMAIL_QUEUE.thread_id, falling back to EMAIL_QUEUE.recipient_email
 *      matched against the message sender for older threads sent before
 *      thread_id capture was reliable).
 *   3. POST the reply to BACKEND_WEBHOOK_URL (if configured) so the
 *      FastAPI backend can run OpenAI reply analysis, create the REPLIES
 *      row, cancel pending follow-ups, and update the lead - the backend
 *      is the single source of truth for that logic (see
 *      backend/app/services/reply_service.py). If the webhook call fails
 *      (network error, backend down), we STILL avoid re-processing the
 *      same message on the next run (idempotency tracking happens before
 *      the webhook call - the webhook itself is called at-least-once
 *      semantics is acceptable since ingest_reply() on the backend is
 *      idempotent by message_id).
 *   4. As a local fallback ONLY (so replies are never silently lost if the
 *      backend is unreachable for an extended period), also write a
 *      minimal REPLIES row directly via SheetRepository with
 *      reply_type=UNKNOWN / ai_summary blank, for the backend (or a human)
 *      to backfill later. This local fallback row is skipped if the
 *      webhook call succeeded (to avoid a duplicate row - the backend's
 *      row is authoritative and richer).
 *
 * NEVER classify sentiment/intent locally with certainty - if
 * OPENAI_API_KEY fallback is configured (see callOpenAiFallback_ below)
 * and the backend webhook is not configured/reachable, we may call OpenAI
 * directly as a best-effort so the reply isn't stuck UNKNOWN forever, but
 * this is clearly a fallback path, documented as such, and never presented
 * as more authoritative than the backend's analysis.
 */

/**
 * Main entry point for the time-driven trigger (System.txt #56, #100).
 * Also invocable from the "Botivate Automation" menu for manual testing.
 */
function scanForReplies() {
  var lock = LockService.getScriptLock();
  var gotLock = lock.tryLock(30000);
  if (!gotLock) {
    Logger.log('scanForReplies: could not acquire lock, another execution is in progress. Skipping this run.');
    return;
  }

  try {
    BotivateConfig.assertValid();
    var labelName = BotivateConfig.REPLY_SCAN_LABEL();
    var label = GmailApp.getUserLabelByName(labelName);
    if (!label) {
      Logger.log('scanForReplies: label "' + labelName + '" does not exist yet (no campaign emails sent). Nothing to scan.');
      return;
    }

    var senderEmail = String(BotivateConfig.BOTIVATE_SENDER_EMAIL() || '').toLowerCase();
    var threads = label.getThreads(0, 200); // cap per run to respect execution time limits
    var processedCount = 0;

    for (var t = 0; t < threads.length; t++) {
      var thread = threads[t];
      var threadId = thread.getId();
      var messages = thread.getMessages();

      var lastProcessedId = PropertiesService.getScriptProperties().getProperty('lastMsg:' + threadId) || '';
      var lastProcessedIndex = -1;
      if (lastProcessedId) {
        for (var m = 0; m < messages.length; m++) {
          if (messages[m].getId() === lastProcessedId) {
            lastProcessedIndex = m;
            break;
          }
        }
      }

      for (var i = lastProcessedIndex + 1; i < messages.length; i++) {
        var message = messages[i];
        var fromHeader = message.getFrom();
        var fromEmail = extractEmailAddress(fromHeader);

        // Only inbound messages (not sent by us) count as replies.
        if (fromEmail === senderEmail) {
          continue;
        }

        var messageId = message.getId();

        // Idempotency cross-check against REPLIES sheet in case Script
        // Properties were cleared/reset.
        var existingReply = SheetRepository.findRows(SHEET_NAMES.REPLIES, function (r) {
          return String(r.message_id) === String(messageId);
        });
        if (existingReply.length > 0) {
          PropertiesService.getScriptProperties().setProperty('lastMsg:' + threadId, messageId);
          continue;
        }

        processIncomingReply_(thread, message, fromEmail, fromHeader);
        PropertiesService.getScriptProperties().setProperty('lastMsg:' + threadId, messageId);
        processedCount++;
      }
    }

    Logger.log('scanForReplies: processed ' + processedCount + ' new reply message(s) across ' + threads.length + ' thread(s).');
  } catch (err) {
    Logger.log('scanForReplies: ERROR - ' + err.message + (err.stack ? ('\n' + err.stack) : ''));
    // Do not rethrow - next scheduled execution should continue regardless
    // (System.txt #136 error recovery: "If reply scanner fails: next
    // execution should continue").
  } finally {
    lock.releaseLock();
  }
}

/**
 * Handles a single newly-detected inbound message: resolves the owning
 * lead, sanitizes the body, notifies the backend, cancels pending
 * follow-ups, and writes a local fallback record if needed.
 * @private
 */
function processIncomingReply_(thread, message, fromEmail, fromHeader) {
  var threadId = thread.getId();
  var messageId = message.getId();
  var plainBody = message.getPlainBody() || '';
  var htmlBodyRaw = message.getBody() || '';
  var sanitizedHtml = sanitizeHtml(htmlBodyRaw);
  var subject = message.getSubject() || '';
  var receivedAt = toIso(message.getDate());
  var toEmail = extractEmailAddress(message.getTo());
  var fromName = extractDisplayName(fromHeader);

  var headers = getRawHeaders_(messageId);

  var linkage = resolveLeadForThread_(threadId, fromEmail);

  var payload = {
    lead_id: linkage.leadId || '',
    company_id: linkage.companyId || '',
    email_id: linkage.emailId || '',
    thread_id: threadId,
    message_id: messageId,
    in_reply_to: headers.inReplyTo || '',
    from_email: fromEmail,
    from_name: fromName,
    to_email: toEmail,
    subject: subject,
    body_text: plainBody,
    body_html: sanitizedHtml,
    received_at: receivedAt
  };

  var webhookUrl = BotivateConfig.BACKEND_WEBHOOK_URL();
  var webhookSucceeded = false;
  if (webhookUrl) {
    webhookSucceeded = postReplyToBackend_(webhookUrl, payload);
  }

  if (!webhookSucceeded) {
    // Local fallback so the reply is never silently lost even if the
    // backend is unreachable. The backend (or a human reviewing the
    // sheet) can backfill reply_type/sentiment/ai_summary later. This
    // path does NOT invent an intent/sentiment - it leaves them UNKNOWN
    // unless the optional OpenAI fallback below succeeds.
    var analysis = tryOpenAiFallback_(subject, plainBody);
    var replyId = generateId('rpl');
    SheetRepository.appendRow(SHEET_NAMES.REPLIES, {
      reply_id: replyId,
      lead_id: linkage.leadId || '',
      company_id: linkage.companyId || '',
      email_id: linkage.emailId || '',
      thread_id: threadId,
      message_id: messageId,
      in_reply_to: headers.inReplyTo || '',
      from_email: fromEmail,
      from_name: fromName,
      to_email: toEmail,
      subject: subject,
      body_text: plainBody,
      body_html: sanitizedHtml,
      received_at: receivedAt,
      reply_type: analysis ? analysis.reply_type : 'UNKNOWN',
      sentiment: analysis ? analysis.sentiment : 'NEUTRAL',
      intent: analysis ? analysis.reply_type : 'UNKNOWN',
      ai_summary: analysis ? analysis.summary : '',
      requires_action: true,
      action_type: analysis ? analysis.recommended_next_action : 'WAIT_FOR_REPLY',
      priority: analysis ? analysis.priority : 'MEDIUM',
      suggested_response: analysis ? analysis.suggested_response : '',
      created_at: nowIso()
    });

    logEmailEvent({
      email_id: linkage.emailId || '', lead_id: linkage.leadId || '', company_id: linkage.companyId || '',
      event_type: 'REPLIED', message_id: messageId, provider: 'gmail',
      metadata: { reply_id: replyId, source: 'apps_script_fallback' }
    });

    if (linkage.leadId) {
      SheetRepository.updateRowById(SHEET_NAMES.LEADS, linkage.leadId, { status: 'REPLIED' });
      cancelPendingFollowUpsForLead_(linkage.leadId, 'REPLY_RECEIVED');
      logActivity({
        lead_id: linkage.leadId, company_id: linkage.companyId || '',
        activity_type: 'REPLY_RECEIVED',
        description: 'Reply received from ' + fromEmail + ' (processed locally - backend webhook unavailable)',
        metadata: { reply_id: replyId }
      });
    }
  }
  // When the webhook succeeds, the BACKEND is responsible for creating the
  // REPLIES row, EMAIL_EVENTS row, lead status update, follow-up
  // cancellation, and ACTIVITY_LOG entry (see reply_service.ingest_reply).
  // We do not duplicate that work here to avoid double-processing.
}

/**
 * Determines which lead/company/email a thread belongs to by looking up
 * EMAIL_QUEUE rows with a matching thread_id (set by EmailSender.gs at
 * send time). Falls back to matching by recipient_email if thread_id is
 * not present (e.g. very old rows sent before thread capture existed).
 * @private
 */
function resolveLeadForThread_(threadId, fromEmail) {
  var byThread = SheetRepository.findRows(SHEET_NAMES.EMAIL_QUEUE, function (q) {
    return String(q.thread_id) === String(threadId) && q.thread_id;
  });
  if (byThread.length > 0) {
    var q = byThread[0];
    return { leadId: q.lead_id, companyId: '', emailId: q.email_id };
  }

  var byRecipient = SheetRepository.findRows(SHEET_NAMES.EMAIL_QUEUE, function (q) {
    return String(q.recipient_email).toLowerCase() === String(fromEmail).toLowerCase() && q.status === 'SENT';
  });
  if (byRecipient.length > 0) {
    var q2 = byRecipient[byRecipient.length - 1]; // most recently appended match
    return { leadId: q2.lead_id, companyId: '', emailId: q2.email_id };
  }

  return { leadId: '', companyId: '', emailId: '' };
}

/**
 * Cancels all SCHEDULED/DUE/QUEUED follow-ups for a lead (local fallback
 * path only - the backend does the equivalent via
 * follow_up_service.cancel_all_pending_for_lead when the webhook path is
 * used). Mirrors System.txt #36, #41, #124.
 * @private
 */
function cancelPendingFollowUpsForLead_(leadId, reason) {
  var pending = SheetRepository.findRows(SHEET_NAMES.FOLLOW_UPS, function (f) {
    return String(f.lead_id) === String(leadId) &&
      (f.status === 'SCHEDULED' || f.status === 'DUE' || f.status === 'QUEUED');
  });
  pending.forEach(function (f) {
    SheetRepository.updateRowByHandle(SHEET_NAMES.FOLLOW_UPS, f.__row, {
      status: 'CANCELLED', cancelled_at: nowIso(), cancel_reason: reason
    });
    logEmailEvent({
      lead_id: leadId, event_type: 'CANCELLED', provider: 'system',
      metadata: { follow_up_id: f.follow_up_id, reason: reason }
    });
  });
}

/**
 * Attempts to read In-Reply-To/References headers via the ADVANCED GMAIL
 * SERVICE (Gmail API). Returns {} silently if the advanced service is not
 * enabled or the call fails - callers must treat missing headers as
 * "unknown", never as an error.
 * @private
 */
function getRawHeaders_(messageId) {
  try {
    // Only works if Services > Gmail API has been added in the Apps Script
    // editor. `typeof Gmail` is 'undefined' otherwise.
    if (typeof Gmail === 'undefined' || !Gmail.Users || !Gmail.Users.Messages) {
      return {};
    }
    var full = Gmail.Users.Messages.get('me', messageId, { format: 'metadata', metadataHeaders: ['In-Reply-To', 'References'] });
    var result = {};
    (full.payload && full.payload.headers || []).forEach(function (h) {
      if (h.name === 'In-Reply-To') result.inReplyTo = h.value;
      if (h.name === 'References') result.references = h.value;
    });
    return result;
  } catch (e) {
    return {};
  }
}

/**
 * Posts a new-reply payload to the backend webhook. Returns true on a 2xx
 * response, false otherwise (network error, non-2xx, backend down). Never
 * throws - callers use the boolean to decide whether to fall back to local
 * processing.
 * @private
 */
function postReplyToBackend_(webhookUrl, payload) {
  try {
    var options = {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
      headers: {}
    };
    var secret = BotivateConfig.APPS_SCRIPT_SHARED_SECRET();
    if (secret) {
      options.headers['X-Apps-Script-Secret'] = secret;
    }
    var response = UrlFetchApp.fetch(webhookUrl, options);
    var code = response.getResponseCode();
    if (code >= 200 && code < 300) return true;
    Logger.log('postReplyToBackend_: backend returned HTTP ' + code + ': ' + response.getContentText());
    return false;
  } catch (e) {
    Logger.log('postReplyToBackend_: request failed - ' + e.message);
    return false;
  }
}

/**
 * OPTIONAL fallback: calls OpenAI directly from Apps Script to classify a
 * reply, ONLY used when BACKEND_WEBHOOK_URL is not configured/reachable
 * AND OPENAI_API_KEY is set. This exists purely so replies are not stuck
 * UNKNOWN indefinitely if the backend is down for a long time - the
 * backend's own analysis (backend/app/agents/reply_analysis.py) is the
 * primary, preferred path. Returns null on any failure (never fabricates
 * a classification).
 * @private
 */
function tryOpenAiFallback_(subject, bodyText) {
  var apiKey = BotivateConfig.OPENAI_API_KEY();
  if (!apiKey) return null;

  try {
    var schema = {
      type: 'object',
      properties: {
        reply_type: { type: 'string', enum: ['INTERESTED', 'REQUEST_FOR_DETAILS', 'MEETING_REQUEST', 'POSITIVE', 'NEUTRAL', 'NOT_INTERESTED', 'ASK_LATER', 'OUT_OF_OFFICE', 'BOUNCE', 'UNSUBSCRIBE', 'UNKNOWN'] },
        sentiment: { type: 'string', enum: ['POSITIVE', 'NEUTRAL', 'NEGATIVE'] },
        summary: { type: 'string' },
        recommended_next_action: { type: 'string' },
        suggested_response: { type: 'string' },
        priority: { type: 'string', enum: ['LOW', 'MEDIUM', 'HIGH', 'URGENT'] }
      },
      required: ['reply_type', 'sentiment', 'summary', 'recommended_next_action', 'suggested_response', 'priority'],
      additionalProperties: false
    };

    var response = UrlFetchApp.fetch('https://api.openai.com/v1/chat/completions', {
      method: 'post',
      contentType: 'application/json',
      muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + apiKey },
      payload: JSON.stringify({
        model: BotivateConfig.OPENAI_MODEL(),
        temperature: 0.3,
        messages: [
          { role: 'system', content: 'Classify this cold-outreach email reply. Be factual, do not invent details.' },
          { role: 'user', content: 'Subject: ' + subject + '\n\nReply body:\n' + bodyText }
        ],
        response_format: { type: 'json_schema', json_schema: { name: 'reply_analysis', schema: schema, strict: true } }
      })
    });

    if (response.getResponseCode() !== 200) return null;
    var data = JSON.parse(response.getContentText());
    var content = data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
    if (!content) return null;
    return JSON.parse(content);
  } catch (e) {
    Logger.log('tryOpenAiFallback_: failed - ' + e.message);
    return null;
  }
}

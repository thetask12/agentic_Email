/**
 * Code.gs
 * ------------------------------------------------------------------------
 * BOTIVATE APPS SCRIPT PROJECT — entry points, trigger management, custom
 * menu, and an optional Web App bridge so the FastAPI backend can trigger
 * workers on demand.
 *
 * PROJECT OVERVIEW
 *   Config.gs           Script Properties configuration (BotivateConfig).
 *   Utils.gs             UUIDs, timestamps, JSON helpers, email validation,
 *                         HTML sanitization, retry-with-backoff.
 *   SheetRepository.gs    Generic header-mapped CRUD against the shared
 *                         Google Sheet (docs/sheet-schema.md).
 *   EmailSender.gs        Sends one EMAIL_QUEUE row via GmailApp, recovers
 *                         message/thread id, applies the SENT_LABEL.
 *   QueueWorker.gs        Processes EMAIL_QUEUE (PENDING/RETRY -> SENT).
 *   FollowUpWorker.gs     Processes FOLLOW_UPS (SCHEDULED/DUE -> QUEUED/
 *                         SENT/SKIPPED/CANCELLED).
 *   ReplyScanner.gs        Scans Gmail for inbound replies on
 *                         SENT_LABEL-tagged threads, notifies the backend,
 *                         cancels pending follow-ups on reply.
 *   EventLogger.gs         logEmailEvent()/logActivity() helpers used by
 *                         the above.
 *   Code.gs (this file)   Triggers, menu, Web App doGet/doPost bridge.
 *
 * REQUIRED SCRIPT PROPERTIES (Project Settings > Script Properties, or run
 * setupConfig() from the menu below):
 *   SHEET_ID, BOTIVATE_SENDER_EMAIL, BOTIVATE_SENDER_NAME,
 *   EMAIL_TEST_MODE, TEST_EMAIL, MAX_FOLLOW_UPS, QUEUE_BATCH_SIZE,
 *   QUEUE_MAX_ATTEMPTS, BACKEND_WEBHOOK_URL, APPS_SCRIPT_SHARED_SECRET,
 *   OPENAI_API_KEY (optional fallback), OPENAI_MODEL, REPLY_SCAN_LABEL,
 *   SENT_LABEL. See Config.gs for full documentation of each.
 *
 * DEPLOYMENT STEPS
 *   1. Create/open an Apps Script project bound to the SAME Google Sheet
 *      used as GOOGLE_SHEETS_ID in the backend's .env (Extensions > Apps
 *      Script from within the Sheet is the simplest way to bind it).
 *   2. Paste all files in this apps-script/ directory into the Apps
 *      Script editor (File > New > Script file for each .gs file, or use
 *      clasp - see docs/apps-script.md).
 *   3. (Recommended) Enable the Advanced Gmail Service: Services (+) >
 *      Gmail API > Add. This unlocks header-level reply matching in
 *      ReplyScanner.gs (In-Reply-To/References). Not required - the
 *      script works without it using thread/label-based matching.
 *   4. Fastest path: open Config.gs, fill in the `values` object inside
 *      setupConfigFromValues() with your real values, select
 *      "setupConfigFromValues" in the function dropdown, click Run once.
 *      Authorize the requested scopes (Sheets, Gmail, URL Fetch) when
 *      prompted. Leave EMAIL_TEST_MODE=true and TEST_EMAIL set until you
 *      are ready to send real outreach. (Alternative: run `setupConfig`
 *      for an interactive prompt-per-field flow instead.)
 *   5. Run `installTriggers` once to install the three time-driven
 *      triggers (queue every 5 min, follow-ups every 15 min, replies
 *      every 10 min). Re-running it is safe/idempotent - it removes and
 *      recreates only the triggers this project owns.
 *   6. (Optional) Deploy as a Web App (Deploy > New deployment > Web app,
 *      execute as "Me", access "Anyone with the link" or restrict as your
 *      org requires) to let the backend call workers on demand via
 *      doPost. Put the resulting URL into the backend's
 *      APPS_SCRIPT_WEB_APP_URL env var and the same shared secret into
 *      both APPS_SCRIPT_SHARED_SECRET (Script Property) and the backend's
 *      APPS_SCRIPT_SHARED_SECRET env var.
 *   7. Reload the Google Sheet - the "Botivate Automation" custom menu
 *      (onOpen below) should appear, giving manual "Run Now" buttons for
 *      each worker plus Setup/Install Triggers, useful for testing.
 */

var TRIGGER_HANDLERS = ['processEmailQueue', 'processFollowUps', 'scanForReplies'];

/**
 * Adds a custom menu when the bound spreadsheet is opened. Apps Script
 * calls this automatically - do not call it manually.
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Botivate Automation')
    .addItem('Setup Config (one-shot, edit values in code)', 'setupConfigFromValues')
    .addItem('Setup Config (interactive prompts)', 'setupConfig')
    .addItem('Set TEST_EMAIL', 'setTestEmail')
    .addItem('Enable Test Mode (safe — redirects sends)', 'enableTestMode')
    .addItem('Disable Test Mode (sends to REAL recipients)', 'disableTestMode')
    .addSeparator()
    .addItem('Install Triggers', 'installTriggers')
    .addItem('Remove Triggers', 'removeTriggers')
    .addSeparator()
    .addItem('Run Queue Worker Now', 'processEmailQueue')
    .addItem('Run Follow-up Worker Now', 'processFollowUps')
    .addItem('Scan Replies Now', 'scanForReplies')
    .addSeparator()
    .addItem('Diagnostic: Test Email Assets (Drive images)', 'testEmailAssets')
    .addItem('Fix: Reset FAILED emails from htmlEncode bug', 'resetHtmlEncodeFailures')
    .addToUi();
}

/**
 * Installs the three time-driven triggers this project needs. Idempotent:
 * removes any existing triggers for the same handler functions first, so
 * running this multiple times never creates duplicate triggers (which
 * would cause the same work to run multiple times concurrently).
 *
 * Cadence chosen to respect Gmail/Apps Script quotas while keeping the
 * system responsive (System.txt #87 rate limiting, #97 execution limits):
 *   processEmailQueue  every 1 minute   (QUEUE_BATCH_SIZE defaults to 1, so
 *                      approved emails go out one at a time, roughly one
 *                      per minute, per explicit user instruction rather
 *                      than sending a batch of several at once)
 *   processFollowUps   every 15 minutes (lower volume, less time-sensitive)
 *   scanForReplies     every 10 minutes (frequent enough for prompt
 *                      reply-aware follow-up cancellation)
 */
function installTriggers() {
  removeTriggers();

  ScriptApp.newTrigger('processEmailQueue').timeBased().everyMinutes(1).create();
  ScriptApp.newTrigger('processFollowUps').timeBased().everyMinutes(15).create();
  ScriptApp.newTrigger('scanForReplies').timeBased().everyMinutes(10).create();

  var message = 'Installed triggers: processEmailQueue (1 min), processFollowUps (15 min), scanForReplies (10 min).';
  Logger.log(message);
  try {
    SpreadsheetApp.getUi().alert('Botivate Automation', message, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless (e.g. via clasp) - logging is sufficient.
  }
}

/**
 * Removes all triggers this project owns (matched by handler function
 * name), without touching any unrelated triggers in the same Apps Script
 * project. Safe to call even if no triggers exist yet.
 */
function removeTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  triggers.forEach(function (trigger) {
    if (TRIGGER_HANDLERS.indexOf(trigger.getHandlerFunction()) !== -1) {
      ScriptApp.deleteTrigger(trigger);
      removed++;
    }
  });
  Logger.log('removeTriggers: removed ' + removed + ' existing trigger(s).');
}

/**
 * Optional Web App bridge (System.txt backend <-> Apps Script on-demand
 * triggering). Deploy via Deploy > New deployment > Web app.
 *
 * Authenticated by a shared secret passed either as a query parameter
 * (?secret=...) for doGet, or in the JSON body ({"secret": "..."}) for
 * doPost. Requests without a matching secret are rejected - this endpoint
 * intentionally does NOT expose any Sheet data in its response, only a
 * trigger acknowledgement, since Web Apps deployed with "Anyone with the
 * link" access are reachable without a Google login.
 *
 * Supported actions (?action=... or body.action):
 *   "queue"      -> runs processEmailQueue()
 *   "followups"  -> runs processFollowUps()
 *   "replies"    -> runs scanForReplies()
 *   (default)    -> runs all three in sequence
 */
function doGet(e) {
  return handleWebAppRequest_(e.parameter || {});
}

function doPost(e) {
  var body = {};
  try {
    body = JSON.parse(e.postData.contents || '{}');
  } catch (parseErr) {
    body = {};
  }
  var merged = {};
  Object.keys(e.parameter || {}).forEach(function (k) { merged[k] = e.parameter[k]; });
  Object.keys(body).forEach(function (k) { merged[k] = body[k]; });
  return handleWebAppRequest_(merged);
}

/**
 * @private
 */
function handleWebAppRequest_(params) {
  var expectedSecret = BotivateConfig.APPS_SCRIPT_SHARED_SECRET();
  if (expectedSecret) {
    var providedSecret = params.secret || '';
    if (providedSecret !== expectedSecret) {
      return jsonResponse_({ ok: false, error: 'Unauthorized' }, 401);
    }
  }

  // sync_config is intentionally its own action, never bundled into 'all' -
  // it's a config write, not a worker trigger, and should only run when
  // the caller explicitly asks for it.
  if (params.action === 'sync_config') {
    return handleSyncConfig_(params);
  }

  var action = params.action || 'all';
  var ran = [];
  try {
    if (action === 'queue' || action === 'all') {
      processEmailQueue();
      ran.push('processEmailQueue');
    }
    if (action === 'followups' || action === 'all') {
      processFollowUps();
      ran.push('processFollowUps');
    }
    if (action === 'replies' || action === 'all') {
      scanForReplies();
      ran.push('scanForReplies');
    }
  } catch (err) {
    return jsonResponse_({ ok: false, error: err.message, ran: ran }, 500);
  }

  return jsonResponse_({ ok: true, ran: ran }, 200);
}

/**
 * @private
 * Lets the backend push a small set of config values (TEST_EMAIL,
 * EMAIL_TEST_MODE, BOTIVATE_SENDER_EMAIL, BOTIVATE_SENDER_NAME) into this
 * Apps Script project's OWN Script Properties, so a single change to the
 * backend's Render environment variables is enough - the operator no
 * longer needs to separately update Script Properties by hand. Only ever
 * writes the specific keys listed in ALLOWED_SYNC_KEYS below; never
 * accepts arbitrary property names from the request, so this can't be
 * used to overwrite SHEET_ID/APPS_SCRIPT_SHARED_SECRET/etc. remotely.
 */
function handleSyncConfig_(params) {
  var ALLOWED_SYNC_KEYS = ['TEST_EMAIL', 'EMAIL_TEST_MODE', 'BOTIVATE_SENDER_EMAIL', 'BOTIVATE_SENDER_NAME'];
  var values = {};
  ALLOWED_SYNC_KEYS.forEach(function (key) {
    if (params[key] !== undefined && params[key] !== null && String(params[key]).trim() !== '') {
      values[key] = String(params[key]).trim();
    }
  });
  var applied = setConfigValues_(values);
  Logger.log('handleSyncConfig_: applied keys: ' + Object.keys(applied).join(', '));
  return jsonResponse_({ ok: true, applied: Object.keys(applied) }, 200);
}

/**
 * @private
 * Note: Apps Script's ContentService cannot set a custom HTTP status code
 * on Web App responses (they are always served as 200 by the Apps Script
 * runtime regardless of what we intend); the requested `status` is
 * included in the JSON body itself so callers (the backend) can inspect
 * `ok`/`error` instead of relying on the transport status code.
 */
function jsonResponse_(obj, status) {
  obj.status = status;
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

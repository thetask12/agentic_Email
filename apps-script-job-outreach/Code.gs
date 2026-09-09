/**
 * Code.gs
 * ------------------------------------------------------------------------
 * JOB OUTREACH APPS SCRIPT PROJECT — a personal job-application system,
 * entirely separate from the Botivate/AutoRocket apps-script/ project. No
 * company/brand identity anywhere in this project.
 *
 * PROJECT OVERVIEW
 *   Config.gs           Script Properties configuration (JobOutreachConfig).
 *   Utils.gs             UUIDs, timestamps, JSON helpers, email validation,
 *                         retry-with-backoff.
 *   SheetRepository.gs    Generic header-mapped CRUD against the Job
 *                         Outreach Google Sheet (docs/job-outreach-schema.md).
 *   EmailSender.gs        Sends one EMAIL_QUEUE row via GmailApp (plain
 *                         text, resume PDF attached), recovers
 *                         message/thread id, applies a Gmail label.
 *   QueueWorker.gs        Processes EMAIL_QUEUE (PENDING/RETRY -> SENT).
 *   EventLogger.gs         logEmailEvent()/logActivity() helpers.
 *   Code.gs (this file)   Triggers + custom menu.
 *
 * No follow-up worker and no reply scanner in this project — out of scope
 * (one email per company, no automation beyond the single send).
 *
 * REQUIRED SCRIPT PROPERTIES (Project Settings > Script Properties, or run
 * setupConfigFromValues() from Config.gs):
 *   SHEET_ID, SENDER_NAME, EMAIL_TEST_MODE, TEST_EMAIL,
 *   RESUME_DRIVE_FILE_ID, QUEUE_BATCH_SIZE, QUEUE_MAX_ATTEMPTS,
 *   DAILY_EMAIL_CAP. See Config.gs for full documentation of each.
 *
 * DEPLOYMENT STEPS
 *   1. Create/open an Apps Script project bound to the Job Outreach Google
 *      Sheet (Sheet ID 1iJXsPZdBCVmExx6l4DIzSHC2jdxCRJz2-naBXdTLoww unless
 *      it changed — Extensions > Apps Script from within the Sheet is the
 *      simplest way to bind it).
 *   2. CRITICAL — authorize this project under the candidate's own Google
 *      account, prabhatkumarsictc12@gmail.com, NOT any other account.
 *      GmailApp.sendEmail() always sends from whichever Google account
 *      authorized/installed the triggers, regardless of any SENDER_NAME
 *      config value — the account you're logged into when you run
 *      setupConfigFromValues()/installTriggers() and click through the
 *      OAuth consent screen IS the sending account. (See the identical
 *      gotcha documented for the Botivate system in root CLAUDE.md.)
 *   3. Paste all files in this apps-script-job-outreach/ directory into the
 *      Apps Script editor (File > New > Script file for each .gs file, or
 *      use clasp — see README.md in this folder).
 *   4. Open Config.gs, fill in the `values` object inside
 *      setupConfigFromValues() with your real SHEET_ID (and adjust
 *      TEST_EMAIL if desired), select "setupConfigFromValues" in the
 *      function dropdown, click Run once. Authorize the requested scopes
 *      (Sheets, Gmail, Drive readonly) when prompted. Leave
 *      EMAIL_TEST_MODE=true and TEST_EMAIL set until ready to send real
 *      applications.
 *   5. Run `installTriggers` once to install the queue worker trigger.
 *      Re-running it is safe/idempotent.
 *   6. Reload the Google Sheet - the "Job Outreach Automation" custom menu
 *      (onOpen below) should appear.
 *   7. Make sure this Google account (prabhatkumarsictc12@gmail.com) has at
 *      least VIEW access to the resume PDF in Google Drive (share it with
 *      that account, or make it "Anyone with the link can view") — the
 *      queue worker fetches it via DriveApp.getFileById(...).getBlob().
 */

var TRIGGER_HANDLERS = ['processEmailQueue'];

/**
 * Adds a custom menu when the bound spreadsheet is opened. Apps Script
 * calls this automatically - do not call it manually.
 */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Job Outreach Automation')
    .addItem('Setup Config (edit values in code)', 'setupConfigFromValues')
    .addItem('Enable Test Mode (safe — redirects sends)', 'enableTestMode')
    .addItem('Disable Test Mode (sends to REAL recipients)', 'disableTestMode')
    .addSeparator()
    .addItem('Install Triggers', 'installTriggers')
    .addItem('Remove Triggers', 'removeTriggers')
    .addSeparator()
    .addItem('Run Queue Worker Now', 'processEmailQueue')
    .addSeparator()
    .addItem('Diagnostic: Test Resume Asset (Drive)', 'testResumeAsset')
    .addToUi();
}

/**
 * Installs the queue worker trigger. Idempotent: removes any existing
 * trigger for the same handler function first, so running this multiple
 * times never creates duplicates.
 */
function installTriggers() {
  removeTriggers();

  ScriptApp.newTrigger('processEmailQueue').timeBased().everyMinutes(1).create();

  var message = 'Installed trigger: processEmailQueue (every 1 min).';
  Logger.log(message);
  try {
    SpreadsheetApp.getUi().alert('Job Outreach Automation', message, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless (e.g. via clasp) - logging is sufficient.
  }
}

/**
 * Removes all triggers this project owns (matched by handler function
 * name). Safe to call even if no triggers exist yet.
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

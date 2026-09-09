/**
 * Config.gs
 * ------------------------------------------------------------------------
 * Centralized configuration for the Botivate Apps Script project.
 *
 * All configuration is read from Script Properties (PropertiesService),
 * NEVER hardcoded, and NEVER stored in the Google Sheet itself (System.txt
 * #81 SECURITY: never put secrets in the Google Sheet).
 *
 * FASTEST SETUP: edit the `values` object inside setupConfigFromValues()
 * below with your real values, select "setupConfigFromValues" in the
 * function dropdown at the top of this editor, and click Run once. That's
 * the only manual step - no per-field prompts.
 *
 * Alternatives: run setupConfig() for an interactive prompt-per-field flow
 * (or use the "Botivate Automation > Setup Config" menu item), or set
 * properties directly via Project Settings > Script Properties.
 *
 * Required Script Properties:
 *   SHEET_ID                    - the Google Sheet ID (same as backend's
 *                                  GOOGLE_SHEETS_ID) that this script reads/writes.
 *   BOTIVATE_SENDER_EMAIL       - the Gmail/Workspace address that sends outreach
 *                                  (must be the account running this script, or an
 *                                  alias it is allowed to send as).
 *   BOTIVATE_SENDER_NAME        - display name used in the "From" field.
 *
 * Optional Script Properties (sane defaults applied if absent):
 *   EMAIL_TEST_MODE             - "true"/"false". Default "true" (safe default).
 *   TEST_EMAIL                  - required if EMAIL_TEST_MODE is true.
 *   MAX_FOLLOW_UPS              - default 4.
 *   QUEUE_BATCH_SIZE            - default 1 (sends approved emails one at a
 *                                  time; the queue trigger runs every 1
 *                                  minute, so this paces sends to roughly
 *                                  one per minute rather than a burst).
 *   QUEUE_MAX_ATTEMPTS          - default 3.
 *   BACKEND_WEBHOOK_URL         - FastAPI endpoint that receives new-reply
 *                                  notifications for OpenAI analysis. Optional -
 *                                  if blank, replies are stored with
 *                                  reply_type/sentiment/ai_summary left blank/UNKNOWN
 *                                  for the backend to backfill later via its own poll.
 *   APPS_SCRIPT_SHARED_SECRET   - shared secret used both to (a) authenticate
 *                                  outbound webhook calls to the backend
 *                                  (sent as header X-Apps-Script-Secret) and
 *                                  (b) authenticate inbound doGet/doPost calls
 *                                  FROM the backend into this script's Web App.
 *   OPENAI_API_KEY              - OPTIONAL fallback so Apps Script itself can
 *                                  call OpenAI directly for reply analysis if
 *                                  BACKEND_WEBHOOK_URL is not configured/reachable.
 *                                  Prefer letting the backend do AI analysis;
 *                                  this is only a fallback (see ReplyScanner.gs).
 *   OPENAI_MODEL                 - default "gpt-4o-mini" when OPENAI_API_KEY fallback used.
 *   REPLY_SCAN_LABEL             - Gmail label applied to sent campaign threads,
 *                                  scanned for replies. Default "Botivate/Sent".
 *   SENT_LABEL                   - Gmail label applied to threads right after
 *                                  sending. Default "Botivate/Sent" (same as
 *                                  REPLY_SCAN_LABEL by default - one label is
 *                                  used both to mark and to scan; kept as two
 *                                  properties in case you want to separate them).
 */

// Namespaced holder object so we don't pollute global scope with many names.
var BotivateConfig = (function () {
  function props() {
    return PropertiesService.getScriptProperties();
  }

  function get(key, defaultValue) {
    var v = props().getProperty(key);
    if (v === null || v === undefined || v === '') {
      return defaultValue;
    }
    return v;
  }

  function getBool(key, defaultValue) {
    var v = props().getProperty(key);
    if (v === null || v === undefined || v === '') {
      return defaultValue;
    }
    return String(v).trim().toLowerCase() === 'true';
  }

  function getInt(key, defaultValue) {
    var v = props().getProperty(key);
    if (v === null || v === undefined || v === '') {
      return defaultValue;
    }
    var n = parseInt(v, 10);
    return isNaN(n) ? defaultValue : n;
  }

  return {
    SHEET_ID: function () { return get('SHEET_ID', ''); },
    BOTIVATE_SENDER_EMAIL: function () { return get('BOTIVATE_SENDER_EMAIL', ''); },
    BOTIVATE_SENDER_NAME: function () { return get('BOTIVATE_SENDER_NAME', 'Botivate Services LLP'); },

    EMAIL_TEST_MODE: function () { return getBool('EMAIL_TEST_MODE', true); },
    TEST_EMAIL: function () { return get('TEST_EMAIL', ''); },

    MAX_FOLLOW_UPS: function () { return getInt('MAX_FOLLOW_UPS', 4); },
    QUEUE_BATCH_SIZE: function () { return getInt('QUEUE_BATCH_SIZE', 1); },
    QUEUE_MAX_ATTEMPTS: function () { return getInt('QUEUE_MAX_ATTEMPTS', 3); },

    BACKEND_WEBHOOK_URL: function () { return get('BACKEND_WEBHOOK_URL', ''); },
    APPS_SCRIPT_SHARED_SECRET: function () { return get('APPS_SCRIPT_SHARED_SECRET', ''); },

    OPENAI_API_KEY: function () { return get('OPENAI_API_KEY', ''); },
    OPENAI_MODEL: function () { return get('OPENAI_MODEL', 'gpt-4o-mini'); },

    REPLY_SCAN_LABEL: function () { return get('REPLY_SCAN_LABEL', 'Botivate/Sent'); },
    SENT_LABEL: function () { return get('SENT_LABEL', 'Botivate/Sent'); },

    // Google Drive folder containing the two email image assets, looked up
    // by filename (not a fixed per-file ID) so replacing an image in Drive
    // never requires a code change. Expected files inside this folder:
    //   autorocket-banner.png  (embedded inline in the email body)
    //   botivate-profile.png   (sent as a regular attachment)
    EMAIL_ASSETS_DRIVE_FOLDER_ID: function () { return get('EMAIL_ASSETS_DRIVE_FOLDER_ID', ''); },

    // Raw accessor, for anything not covered above.
    raw: function (key, defaultValue) { return get(key, defaultValue); },

    // Validate the minimum required configuration. Throws with a clear
    // message if something mandatory is missing, so workers fail loudly
    // and visibly (in Apps Script execution logs) instead of silently
    // misbehaving.
    assertValid: function () {
      var missing = [];
      if (!this.SHEET_ID()) missing.push('SHEET_ID');
      if (!this.BOTIVATE_SENDER_EMAIL()) missing.push('BOTIVATE_SENDER_EMAIL');
      if (this.EMAIL_TEST_MODE() && !this.TEST_EMAIL()) missing.push('TEST_EMAIL (required because EMAIL_TEST_MODE=true)');
      if (missing.length > 0) {
        throw new Error('Botivate Apps Script configuration incomplete. Missing: ' + missing.join(', ') + '. Run setupConfig() or set Script Properties manually.');
      }
    }
  };
})();

/**
 * ONE-SHOT setup: paste your real values below and run THIS function once
 * (select "setupConfigFromValues" in the function dropdown at the top of
 * the editor, click Run). No prompts, no clicking through 14 dialogs -
 * every Script Property is set in a single PropertiesService call.
 *
 * Fill in the object below with your actual values (same ones as the
 * backend's .env), then Run. Re-run any time to update values - it's
 * idempotent and only overwrites keys you actually put a value for
 * (keys left as '' are skipped, not cleared).
 */
function setupConfigFromValues() {
  var values = {
    SHEET_ID: '1or9IURXosJ546yiIAefXfOCkA2UoimJs9hbelcVlTVI',
    BOTIVATE_SENDER_EMAIL: 'info@botivate.in',
    BOTIVATE_SENDER_NAME: 'Satyendra Kumar Tandan',

    EMAIL_TEST_MODE: 'true',
    TEST_EMAIL: 'prabhatkumarsictc7070@gmail.com',

    MAX_FOLLOW_UPS: '4',
    QUEUE_BATCH_SIZE: '1',
    QUEUE_MAX_ATTEMPTS: '3',

    // Drive folder holding autorocket-banner.png (inline) and
    // botivate-profile.png (attachment) — from the folder URL
    // https://drive.google.com/drive/folders/1YQlinkwKIlS1S0Qj3Dy9SDh-mt5UtV3D
    EMAIL_ASSETS_DRIVE_FOLDER_ID: '1YQlinkwKIlS1S0Qj3Dy9SDh-mt5UtV3D',

    // Set this to the same random string you put in the backend's
    // APPS_SCRIPT_SHARED_SECRET env var. Leave '' to skip for now.
    APPS_SCRIPT_SHARED_SECRET: '',

    // Your deployed backend's public URL + /api/replies/webhook.
    // Leave '' until the backend is deployed - replies still get stored,
    // just without AI analysis until this is set and re-run.
    BACKEND_WEBHOOK_URL: '',

    // Optional fallback only - leave blank to let the backend do AI analysis.
    OPENAI_API_KEY: '',
    OPENAI_MODEL: 'gpt-4o-mini',

    REPLY_SCAN_LABEL: 'Botivate/Sent',
    SENT_LABEL: 'Botivate/Sent'
  };

  setConfigValues_(values);
  Logger.log('Botivate Script Properties saved. Run installTriggers() next.');
}

/**
 * Shared implementation: writes every non-empty key in `values` to Script
 * Properties in a single batched call. Used by both the one-shot
 * setupConfigFromValues() above and the interactive setupConfig() prompt
 * flow below, so there is exactly one place that actually writes config.
 */
function setConfigValues_(values) {
  var scriptProps = PropertiesService.getScriptProperties();
  var toSet = {};
  Object.keys(values).forEach(function (key) {
    var v = values[key];
    if (v !== null && v !== undefined && String(v).trim() !== '') {
      toSet[key] = String(v).trim();
    }
  });
  if (Object.keys(toSet).length > 0) {
    scriptProps.setProperties(toSet, false); // false = don't delete keys not present
  }
  return toSet;
}

/**
 * ONE-CLICK UTILITY - run this manually from the function dropdown or the
 * "Botivate Automation" menu whenever you just need to change TEST_EMAIL
 * without re-running the full setupConfigFromValues() (which would also
 * re-apply every other value in that function, including
 * BOTIVATE_SENDER_EMAIL/NAME - this only touches TEST_EMAIL). Edit the
 * address below, then Run.
 */
function setTestEmail() {
  var newTestEmail = 'prabhatkumarsictc7070@gmail.com';
  setConfigValues_({ TEST_EMAIL: newTestEmail });
  var message = 'TEST_EMAIL set to: ' + newTestEmail;
  Logger.log(message);
  try {
    SpreadsheetApp.getUi().alert('Botivate Automation', message, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless - logging is sufficient.
  }
}

/**
 * ONE-CLICK UTILITY - run this from the function dropdown or the
 * "Botivate Automation" menu to turn EMAIL_TEST_MODE ON. While on, every
 * outgoing email is redirected to TEST_EMAIL instead of the real
 * recipient - no real company is ever contacted. Deliberately a separate
 * function from disableTestMode() (rather than one toggle) so which one
 * you run always matches what you intend, with no need to check the
 * current state first.
 */
function enableTestMode() {
  setConfigValues_({ EMAIL_TEST_MODE: 'true' });
  var message = 'EMAIL_TEST_MODE is now ON. All outgoing emails will be redirected to TEST_EMAIL (' +
    BotivateConfig.TEST_EMAIL() + ').';
  Logger.log(message);
  try {
    SpreadsheetApp.getUi().alert('Botivate Automation', message, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless - logging is sufficient.
  }
}

/**
 * ONE-CLICK UTILITY - run this from the function dropdown or the
 * "Botivate Automation" menu to turn EMAIL_TEST_MODE OFF. Once off, every
 * outgoing email goes to the REAL company email address, sent from
 * BOTIVATE_SENDER_EMAIL. Double-check the email content/template before
 * running this - it takes effect on the very next queue worker run
 * (within ~1 minute), and there is no undo for emails already sent.
 */
function disableTestMode() {
  setConfigValues_({ EMAIL_TEST_MODE: 'false' });
  var message = 'EMAIL_TEST_MODE is now OFF. Outgoing emails will go to REAL recipients from ' +
    BotivateConfig.BOTIVATE_SENDER_EMAIL() + '. Make sure this is intentional.';
  Logger.log(message);
  try {
    SpreadsheetApp.getUi().alert('Botivate Automation — REAL SENDING ENABLED', message, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless - logging is sufficient.
  }
}

/**
 * Interactive fallback: prompts (using the spreadsheet UI) for each
 * required/optional value one at a time. Prefer setupConfigFromValues()
 * above - this is kept only for cases where pasting values into code isn't
 * convenient. Leave a prompt blank to keep the existing stored value (or
 * the default) unchanged.
 */
function setupConfig() {
  var ui;
  try {
    ui = SpreadsheetApp.getUi();
  } catch (e) {
    // Not bound to a spreadsheet / running headless - fall back to logging
    // instructions instead of crashing.
    Logger.log('setupConfig() must be run from within the bound Google Sheet ' +
      'so it can show prompts. Alternatively, set Script Properties directly: ' +
      'Project Settings > Script Properties, or via ' +
      'PropertiesService.getScriptProperties().setProperties({...}) in the editor.');
    return;
  }

  var scriptProps = PropertiesService.getScriptProperties();

  var fields = [
    { key: 'SHEET_ID', label: 'Google Sheet ID (same as backend GOOGLE_SHEETS_ID)', required: true },
    { key: 'BOTIVATE_SENDER_EMAIL', label: 'Botivate sender Gmail/Workspace address', required: true },
    { key: 'BOTIVATE_SENDER_NAME', label: 'Botivate sender display name', required: false, defaultValue: 'Botivate Services LLP' },
    { key: 'EMAIL_TEST_MODE', label: 'Email test mode? (true/false) - keep true until go-live', required: false, defaultValue: 'true' },
    { key: 'TEST_EMAIL', label: 'Test email address (used when EMAIL_TEST_MODE=true)', required: false },
    { key: 'MAX_FOLLOW_UPS', label: 'Max follow-ups per lead', required: false, defaultValue: '4' },
    { key: 'QUEUE_BATCH_SIZE', label: 'Queue batch size per run', required: false, defaultValue: '1' },
    { key: 'QUEUE_MAX_ATTEMPTS', label: 'Max send attempts before FAILED', required: false, defaultValue: '3' },
    { key: 'BACKEND_WEBHOOK_URL', label: 'Backend webhook URL for new replies (optional)', required: false },
    { key: 'APPS_SCRIPT_SHARED_SECRET', label: 'Shared secret for backend <-> Apps Script auth', required: false },
    { key: 'OPENAI_API_KEY', label: 'OpenAI API key (optional fallback for reply analysis)', required: false },
    { key: 'OPENAI_MODEL', label: 'OpenAI model (optional fallback)', required: false, defaultValue: 'gpt-4o-mini' },
    { key: 'REPLY_SCAN_LABEL', label: 'Gmail label to scan for replies', required: false, defaultValue: 'Botivate/Sent' },
    { key: 'SENT_LABEL', label: 'Gmail label applied to sent campaign threads', required: false, defaultValue: 'Botivate/Sent' }
  ];

  fields.forEach(function (field) {
    var existing = scriptProps.getProperty(field.key);
    var promptText = field.label + (existing ? ' [current: ' + existing + ']' : '') +
      (field.defaultValue ? ' [default: ' + field.defaultValue + ']' : '');
    var response = ui.prompt('Botivate Setup', promptText, ui.ButtonSet.OK_CANCEL);
    if (response.getSelectedButton() !== ui.Button.OK) {
      return; // user cancelled this field, skip
    }
    var value = response.getResponseText().trim();
    if (value === '') {
      // Keep existing value; if none exists yet, fall back to the default.
      if (!existing && field.defaultValue) {
        scriptProps.setProperty(field.key, field.defaultValue);
      }
      return;
    }
    scriptProps.setProperty(field.key, value);
  });

  ui.alert('Botivate Setup', 'Configuration saved. You can re-run Setup Config any time to update values.', ui.ButtonSet.OK);
}

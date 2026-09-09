/**
 * Config.gs
 * ------------------------------------------------------------------------
 * Centralized configuration for the Job Outreach Apps Script project — a
 * personal job-application system, separate from the Botivate/AutoRocket
 * apps-script/ project. No company/brand identity anywhere in this file.
 *
 * All configuration is read from Script Properties (PropertiesService),
 * never hardcoded and never stored in the Google Sheet itself.
 *
 * FASTEST SETUP: edit the `values` object inside setupConfigFromValues()
 * below with your real values, select "setupConfigFromValues" in the
 * function dropdown at the top of this editor, and click Run once.
 *
 * Required Script Properties:
 *   SHEET_ID              - the Job Outreach Google Sheet ID (same as the
 *                            backend's JOB_OUTREACH_SHEET_ID).
 *   SENDER_NAME            - display name used in the "From" field
 *                            (the candidate's own name, not a company).
 *
 * Optional Script Properties (sane defaults applied if absent):
 *   EMAIL_TEST_MODE        - "true"/"false". Default "true" (safe default).
 *   TEST_EMAIL             - required if EMAIL_TEST_MODE is true.
 *   RESUME_DRIVE_FILE_ID   - Google Drive file id of the resume PDF,
 *                            attached to every outgoing application email.
 *   QUEUE_BATCH_SIZE       - default 1 (one send per trigger run).
 *   QUEUE_MAX_ATTEMPTS     - default 3.
 *   DAILY_EMAIL_CAP        - default 100 (informational here; the backend
 *                            is the actual enforcer of the daily cap when
 *                            queuing new rows — this worker just sends
 *                            whatever is already PENDING).
 */

var JobOutreachConfig = (function () {
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
    SENDER_NAME: function () { return get('SENDER_NAME', ''); },

    EMAIL_TEST_MODE: function () { return getBool('EMAIL_TEST_MODE', true); },
    TEST_EMAIL: function () { return get('TEST_EMAIL', ''); },

    RESUME_DRIVE_FILE_ID: function () { return get('RESUME_DRIVE_FILE_ID', ''); },

    QUEUE_BATCH_SIZE: function () { return getInt('QUEUE_BATCH_SIZE', 1); },
    QUEUE_MAX_ATTEMPTS: function () { return getInt('QUEUE_MAX_ATTEMPTS', 3); },
    DAILY_EMAIL_CAP: function () { return getInt('DAILY_EMAIL_CAP', 100); },

    SENT_LABEL: function () { return get('SENT_LABEL', 'JobOutreach/Sent'); },

    // Validate the minimum required configuration. Throws with a clear
    // message if something mandatory is missing, so the worker fails
    // loudly and visibly instead of silently misbehaving.
    assertValid: function () {
      var missing = [];
      if (!this.SHEET_ID()) missing.push('SHEET_ID');
      if (this.EMAIL_TEST_MODE() && !this.TEST_EMAIL()) missing.push('TEST_EMAIL (required because EMAIL_TEST_MODE=true)');
      if (missing.length > 0) {
        throw new Error('Job Outreach Apps Script configuration incomplete. Missing: ' + missing.join(', ') + '. Run setupConfigFromValues() first.');
      }
    }
  };
})();

/**
 * ONE-SHOT setup: paste your real values below and run THIS function once
 * (select "setupConfigFromValues" in the function dropdown, click Run).
 * Idempotent — re-run any time to update values; only overwrites keys you
 * actually set (blank values are skipped, not cleared).
 */
function setupConfigFromValues() {
  var values = {
    // Fill in with the Job Outreach Sheet ID
    // (1iJXsPZdBCVmExx6l4DIzSHC2jdxCRJz2-naBXdTLoww unless it changed).
    SHEET_ID: '1iJXsPZdBCVmExx6l4DIzSHC2jdxCRJz2-naBXdTLoww',

    // The candidate's own name — this is a personal application system,
    // not a company sender.
    SENDER_NAME: 'Prabhat Kumar Singh',

    EMAIL_TEST_MODE: 'true',
    TEST_EMAIL: 'thetasklinker@gmail.com',

    // Drive file id of the resume PDF (from
    // https://drive.google.com/file/d/<id>/view).
    RESUME_DRIVE_FILE_ID: '1CijF9kbtlaTuay4iVsguC12Dnkc9lCc-',

    QUEUE_BATCH_SIZE: '1',
    QUEUE_MAX_ATTEMPTS: '3',
    DAILY_EMAIL_CAP: '100',

    SENT_LABEL: 'JobOutreach/Sent'
  };

  setConfigValues_(values);
  Logger.log('Job Outreach Script Properties saved. Run installTriggers() next.');
}

/**
 * Shared implementation: writes every non-empty key in `values` to Script
 * Properties in a single batched call.
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
 * ONE-CLICK UTILITY - turns EMAIL_TEST_MODE ON. While on, every outgoing
 * application email is redirected to TEST_EMAIL instead of the real
 * recipient - no real company is ever contacted. Deliberately a separate
 * function from disableTestMode() (not one toggle) so which one you run
 * always matches what you intend.
 */
function enableTestMode() {
  setConfigValues_({ EMAIL_TEST_MODE: 'true' });
  var message = 'EMAIL_TEST_MODE is now ON. All outgoing emails will be redirected to TEST_EMAIL (' +
    JobOutreachConfig.TEST_EMAIL() + ').';
  Logger.log(message);
  try {
    SpreadsheetApp.getUi().alert('Job Outreach Automation', message, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless - logging is sufficient.
  }
}

/**
 * ONE-CLICK UTILITY - turns EMAIL_TEST_MODE OFF. Once off, every outgoing
 * email goes to the REAL company contact address. Double-check the email
 * content before running this - it takes effect on the very next queue
 * worker run, and there is no undo for emails already sent.
 */
function disableTestMode() {
  setConfigValues_({ EMAIL_TEST_MODE: 'false' });
  var message = 'EMAIL_TEST_MODE is now OFF. Outgoing emails will go to REAL recipients. Make sure this is intentional.';
  Logger.log(message);
  try {
    SpreadsheetApp.getUi().alert('Job Outreach Automation — REAL SENDING ENABLED', message, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (e) {
    // Running headless - logging is sufficient.
  }
}

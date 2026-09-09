/**
 * SheetRepository.gs
 * ------------------------------------------------------------------------
 * Generic, header-mapped CRUD helper for reading/writing rows in the
 * shared Google Sheet database (docs/sheet-schema.md is the source of
 * truth for tab names and column order).
 *
 * Design notes:
 *  - Row objects are plain JS objects keyed by the sheet's header row
 *    (row 1). Column order in the Sheet does not need to match property
 *    insertion order in code - we always look up by header name.
 *  - The physical spreadsheet row number is NEVER used as a stored ID.
 *    It is only ever used as an ephemeral in-memory lookup handle during
 *    a single execution (System.txt #64 ROW IDENTIFIERS). Every entity
 *    has its own UUID column (e.g. queue_id, event_id, follow_up_id) and
 *    all cross-references between sheets use those UUIDs.
 *  - All reads/writes go through SpreadsheetApp against the single
 *    spreadsheet identified by Config's SHEET_ID, so this operates on the
 *    exact same Sheet the FastAPI backend uses via the Sheets API.
 *  - Because both the backend and Apps Script can write to the same
 *    Sheet, every mutating operation here re-reads the current header
 *    row and current data before writing, and uses LockService in the
 *    calling workers (QueueWorker/FollowUpWorker/ReplyScanner) to avoid
 *    read-modify-write races for the resources they own.
 */

var SHEET_NAMES = {
  CONFIG: 'CONFIG',
  SEARCH_RUNS: 'SEARCH_RUNS',
  JOBS: 'JOBS',
  COMPANIES: 'COMPANIES',
  CONTACTS: 'CONTACTS',
  LEADS: 'LEADS',
  EMAIL_TEMPLATES: 'EMAIL_TEMPLATES',
  EMAIL_DRAFTS: 'EMAIL_DRAFTS',
  EMAIL_QUEUE: 'EMAIL_QUEUE',
  EMAIL_EVENTS: 'EMAIL_EVENTS',
  FOLLOW_UPS: 'FOLLOW_UPS',
  FOLLOW_UP_TEMPLATES: 'FOLLOW_UP_TEMPLATES',
  REPLIES: 'REPLIES',
  CONVERSATIONS: 'CONVERSATIONS',
  CAMPAIGNS: 'CAMPAIGNS',
  SUPPRESSION_LIST: 'SUPPRESSION_LIST',
  SOURCE_STATUS: 'SOURCE_STATUS',
  ACTIVITY_LOG: 'ACTIVITY_LOG',
  LEAD_NOTES: 'LEAD_NOTES',
  SETTINGS: 'SETTINGS'
};

// The primary-key column name for each sheet, used by findRowById/updateRowById.
var SHEET_ID_COLUMNS = {
  CONFIG: 'key',
  SEARCH_RUNS: 'run_id',
  JOBS: 'job_id',
  COMPANIES: 'company_id',
  CONTACTS: 'contact_id',
  LEADS: 'lead_id',
  EMAIL_TEMPLATES: 'template_id',
  EMAIL_DRAFTS: 'email_id',
  EMAIL_QUEUE: 'queue_id',
  EMAIL_EVENTS: 'event_id',
  FOLLOW_UPS: 'follow_up_id',
  FOLLOW_UP_TEMPLATES: 'template_id',
  REPLIES: 'reply_id',
  CONVERSATIONS: 'conversation_id',
  CAMPAIGNS: 'campaign_id',
  SUPPRESSION_LIST: 'suppression_id',
  SOURCE_STATUS: 'source',
  ACTIVITY_LOG: 'activity_id',
  LEAD_NOTES: 'note_id',
  SETTINGS: 'key'
};

/**
 * Opens the shared spreadsheet by SHEET_ID from Config. Cached per
 * execution (Apps Script executions are short-lived, so a simple module
 * variable is fine - no cross-execution caching is attempted here).
 */
var SheetRepository = (function () {
  var _spreadsheet = null;

  function getSpreadsheet() {
    if (_spreadsheet) return _spreadsheet;
    var sheetId = BotivateConfig.SHEET_ID();
    if (!sheetId) {
      throw new Error('SHEET_ID is not configured. Run setupConfig() first.');
    }
    _spreadsheet = SpreadsheetApp.openById(sheetId);
    return _spreadsheet;
  }

  function getSheet(sheetName) {
    var ss = getSpreadsheet();
    var sheet = ss.getSheetByName(sheetName);
    if (!sheet) {
      throw new Error('Sheet tab "' + sheetName + '" was not found in the spreadsheet. ' +
        'Verify docs/sheet-schema.md tab names match exactly.');
    }
    return sheet;
  }

  /** Reads the header row (row 1) as an array of column names. */
  function getHeaders(sheet) {
    var lastCol = sheet.getLastColumn();
    if (lastCol === 0) return [];
    return sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  }

  /** Converts a raw row array + header array into a keyed object. */
  function rowArrayToObject(headers, rowArray) {
    var obj = {};
    for (var i = 0; i < headers.length; i++) {
      var key = headers[i];
      if (!key) continue; // skip blank header cells
      obj[key] = rowArray[i];
    }
    return obj;
  }

  /** Converts a keyed object into a row array matching the given headers. */
  function objectToRowArray(headers, obj) {
    return headers.map(function (h) {
      if (!h) return '';
      var v = obj.hasOwnProperty(h) ? obj[h] : '';
      return (v === undefined || v === null) ? '' : v;
    });
  }

  return {
    getSpreadsheet: getSpreadsheet,
    getSheet: getSheet,

    /**
     * Returns ALL data rows (excluding the header) from a sheet as an
     * array of {..., __row: <1-based physical row number>} objects.
     * __row is an EPHEMERAL lookup handle for use within this single
     * execution only (e.g. to call setValues on a specific row) - it
     * must never be persisted as an identifier anywhere.
     *
     * @param {string} sheetName one of SHEET_NAMES values.
     * @return {Array<Object>}
     */
    getRows: function (sheetName) {
      var sheet = getSheet(sheetName);
      var lastRow = sheet.getLastRow();
      var lastCol = sheet.getLastColumn();
      if (lastRow < 2 || lastCol === 0) return [];

      var headers = getHeaders(sheet);
      var values = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();

      var rows = [];
      for (var i = 0; i < values.length; i++) {
        var obj = rowArrayToObject(headers, values[i]);
        obj.__row = i + 2; // physical row number, 1-based, ephemeral only
        rows.push(obj);
      }
      return rows;
    },

    /**
     * Finds a single row by its entity ID column (per SHEET_ID_COLUMNS).
     * Returns null if not found.
     * @param {string} sheetName
     * @param {string} id
     * @return {Object|null}
     */
    findRowById: function (sheetName, id) {
      var idColumn = SHEET_ID_COLUMNS[sheetName];
      if (!idColumn) throw new Error('No ID column configured for sheet "' + sheetName + '"');
      var rows = this.getRows(sheetName);
      for (var i = 0; i < rows.length; i++) {
        if (String(rows[i][idColumn]) === String(id)) return rows[i];
      }
      return null;
    },

    /**
     * Finds all rows matching a predicate function(rowObj): boolean.
     * @param {string} sheetName
     * @param {function(Object):boolean} predicate
     * @return {Array<Object>}
     */
    findRows: function (sheetName, predicate) {
      return this.getRows(sheetName).filter(predicate);
    },

    /**
     * Appends a new row. Missing columns are written as ''. Returns the
     * object that was written (without __row, since append doesn't know
     * the resulting row number without a re-read; callers that need it
     * should call findRowById immediately after using the object's own
     * UUID column).
     * @param {string} sheetName
     * @param {Object} rowObject
     */
    appendRow: function (sheetName, rowObject) {
      var sheet = getSheet(sheetName);
      var headers = getHeaders(sheet);
      if (headers.length === 0) {
        throw new Error('Sheet "' + sheetName + '" has no header row. Create headers per docs/sheet-schema.md first.');
      }
      var rowArray = objectToRowArray(headers, rowObject);
      retryWithBackoff(function () {
        sheet.appendRow(rowArray);
      }, { maxAttempts: 3, baseDelayMs: 500 });
      return rowObject;
    },

    /**
     * Updates an existing row identified by its entity ID column, merging
     * `patch` fields into the existing row (existing values are preserved
     * for any column not present in patch). No-ops (throws) if the ID is
     * not found - callers should check existence first if that's expected.
     *
     * NOTE ON RACE CONDITIONS: this re-reads the row's current values
     * immediately before writing, and only rewrites the full row range in
     * a single setValues call, minimizing (but not eliminating) the
     * window for a race with a concurrent backend write. Callers that
     * need strict read-modify-write safety across processes (e.g.
     * QueueWorker sending an email) MUST hold a LockService lock around
     * the check-then-update sequence.
     *
     * @param {string} sheetName
     * @param {string} id
     * @param {Object} patch Partial object of column:value to merge in.
     * @return {Object} the updated row object.
     */
    updateRowById: function (sheetName, id, patch) {
      var idColumn = SHEET_ID_COLUMNS[sheetName];
      if (!idColumn) throw new Error('No ID column configured for sheet "' + sheetName + '"');
      var sheet = getSheet(sheetName);
      var headers = getHeaders(sheet);
      var lastRow = sheet.getLastRow();
      if (lastRow < 2) throw new Error('Sheet "' + sheetName + '" has no data rows.');

      var idColIndex = headers.indexOf(idColumn);
      if (idColIndex === -1) throw new Error('ID column "' + idColumn + '" not found in headers of "' + sheetName + '"');

      var numRows = lastRow - 1;
      var idValues = sheet.getRange(2, idColIndex + 1, numRows, 1).getValues();
      var physicalRow = -1;
      for (var i = 0; i < idValues.length; i++) {
        if (String(idValues[i][0]) === String(id)) {
          physicalRow = i + 2;
          break;
        }
      }
      if (physicalRow === -1) {
        throw new Error('Row with ' + idColumn + '="' + id + '" not found in "' + sheetName + '"');
      }

      var currentValues = sheet.getRange(physicalRow, 1, 1, headers.length).getValues()[0];
      var currentObj = rowArrayToObject(headers, currentValues);
      var merged = {};
      headers.forEach(function (h) {
        if (!h) return;
        merged[h] = patch.hasOwnProperty(h) ? patch[h] : currentObj[h];
      });

      var newRowArray = objectToRowArray(headers, merged);
      var targetRow = physicalRow;
      retryWithBackoff(function () {
        sheet.getRange(targetRow, 1, 1, headers.length).setValues([newRowArray]);
      }, { maxAttempts: 3, baseDelayMs: 500 });

      return merged;
    },

    /**
     * Updates a row using its ALREADY-KNOWN ephemeral __row handle (as
     * returned by getRows()/findRows() within the SAME execution). Faster
     * than updateRowById when you already iterated the sheet and have the
     * row objects in hand. Do not persist __row across executions.
     * @param {string} sheetName
     * @param {number} physicalRow
     * @param {Object} patch
     */
    updateRowByHandle: function (sheetName, physicalRow, patch) {
      var sheet = getSheet(sheetName);
      var headers = getHeaders(sheet);
      var currentValues = sheet.getRange(physicalRow, 1, 1, headers.length).getValues()[0];
      var currentObj = rowArrayToObject(headers, currentValues);
      var merged = {};
      headers.forEach(function (h) {
        if (!h) return;
        merged[h] = patch.hasOwnProperty(h) ? patch[h] : currentObj[h];
      });
      var newRowArray = objectToRowArray(headers, merged);
      retryWithBackoff(function () {
        sheet.getRange(physicalRow, 1, 1, headers.length).setValues([newRowArray]);
      }, { maxAttempts: 3, baseDelayMs: 500 });
      return merged;
    }
  };
})();

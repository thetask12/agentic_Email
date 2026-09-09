/**
 * SheetRepository.gs
 * ------------------------------------------------------------------------
 * Generic, header-mapped CRUD helper for reading/writing rows in the
 * Job Outreach Google Sheet (docs/job-outreach-schema.md is the source of
 * truth for tab names and column order). Ported from
 * apps-script/SheetRepository.gs, generalized to this module's tabs.
 *
 * The physical spreadsheet row number is NEVER used as a stored ID — every
 * entity has its own UUID column, and cross-references between tabs use
 * those UUIDs.
 */

var SHEET_NAMES = {
  SETTINGS: 'SETTINGS',
  JOB_LISTINGS: 'JOB_LISTINGS',
  COMPANIES: 'COMPANIES',
  EMAIL_QUEUE: 'EMAIL_QUEUE',
  EMAIL_EVENTS: 'EMAIL_EVENTS',
  SUPPRESSION_LIST: 'SUPPRESSION_LIST',
  SEARCH_RUNS: 'SEARCH_RUNS',
  ACTIVITY_LOG: 'ACTIVITY_LOG'
};

// The primary-key column name for each sheet, used by findRowById/updateRowById.
var SHEET_ID_COLUMNS = {
  SETTINGS: 'key',
  JOB_LISTINGS: 'job_id',
  COMPANIES: 'company_id',
  EMAIL_QUEUE: 'queue_id',
  EMAIL_EVENTS: 'event_id',
  SUPPRESSION_LIST: 'suppression_id',
  SEARCH_RUNS: 'run_id',
  ACTIVITY_LOG: 'log_id'
};

/**
 * Opens the Job Outreach spreadsheet by SHEET_ID from Config. Cached per
 * execution.
 */
var SheetRepository = (function () {
  var _spreadsheet = null;

  function getSpreadsheet() {
    if (_spreadsheet) return _spreadsheet;
    var sheetId = JobOutreachConfig.SHEET_ID();
    if (!sheetId) {
      throw new Error('SHEET_ID is not configured. Run setupConfigFromValues() first.');
    }
    _spreadsheet = SpreadsheetApp.openById(sheetId);
    return _spreadsheet;
  }

  function getSheet(sheetName) {
    var ss = getSpreadsheet();
    var sheet = ss.getSheetByName(sheetName);
    if (!sheet) {
      throw new Error('Sheet tab "' + sheetName + '" was not found. Verify docs/job-outreach-schema.md tab names match exactly.');
    }
    return sheet;
  }

  function getHeaders(sheet) {
    var lastCol = sheet.getLastColumn();
    if (lastCol === 0) return [];
    return sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  }

  function rowArrayToObject(headers, rowArray) {
    var obj = {};
    for (var i = 0; i < headers.length; i++) {
      var key = headers[i];
      if (!key) continue;
      obj[key] = rowArray[i];
    }
    return obj;
  }

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
     * Returns ALL data rows (excluding the header) as an array of
     * {..., __row: <1-based physical row number>} objects. __row is an
     * EPHEMERAL lookup handle for this execution only.
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
        obj.__row = i + 2;
        rows.push(obj);
      }
      return rows;
    },

    /** Finds a single row by its entity ID column. Returns null if not found. */
    findRowById: function (sheetName, id) {
      var idColumn = SHEET_ID_COLUMNS[sheetName];
      if (!idColumn) throw new Error('No ID column configured for sheet "' + sheetName + '"');
      var rows = this.getRows(sheetName);
      for (var i = 0; i < rows.length; i++) {
        if (String(rows[i][idColumn]) === String(id)) return rows[i];
      }
      return null;
    },

    /** Finds all rows matching a predicate function(rowObj): boolean. */
    findRows: function (sheetName, predicate) {
      return this.getRows(sheetName).filter(predicate);
    },

    /** Appends a new row. Missing columns are written as ''. */
    appendRow: function (sheetName, rowObject) {
      var sheet = getSheet(sheetName);
      var headers = getHeaders(sheet);
      if (headers.length === 0) {
        throw new Error('Sheet "' + sheetName + '" has no header row. Run the setup script first.');
      }
      var rowArray = objectToRowArray(headers, rowObject);
      retryWithBackoff(function () {
        sheet.appendRow(rowArray);
      }, { maxAttempts: 3, baseDelayMs: 500 });
      return rowObject;
    },

    /**
     * Updates an existing row identified by its entity ID column, merging
     * `patch` fields into the existing row.
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
    }
  };
})();

# Job Outreach Apps Script — deployment via clasp

This folder is a separate Apps Script project from `../apps-script/` (the
Botivate/AutoRocket system). It must be authorized under the candidate's own
Google account, **prabhatkumarsictc12@gmail.com** — see the header comment
in `Code.gs` for why (GmailApp always sends from whichever account
authorized the triggers).

Claude Code cannot run `clasp login` (it requires an interactive OAuth
browser flow) or push this project itself — these are one-time manual steps
for you to run locally.

## One-time setup

```bash
npm install -g @google/clasp

# Log in AS prabhatkumarsictc12@gmail.com (a browser window will open).
clasp login
```

### Option A — brand-new Apps Script project bound to the Sheet

```bash
cd apps-script-job-outreach
clasp create --title "Job Outreach Automation" --type sheets --parentId <JOB_OUTREACH_SHEET_ID>
```

Replace `<JOB_OUTREACH_SHEET_ID>` with the Job Outreach Google Sheet ID
(`1iJXsPZdBCVmExx6l4DIzSHC2jdxCRJz2-naBXdTLoww` unless it has changed).
`clasp create --type sheets --parentId ...` both creates the Apps Script
project AND binds it to that existing Sheet, so `onOpen()`'s custom menu
appears the next time you open the Sheet.

### Option B — a project already exists

```bash
cd apps-script-job-outreach
clasp clone <SCRIPT_ID>
```

## Push the code

```bash
cd apps-script-job-outreach
clasp push
```

Re-run `clasp push` any time you edit a `.gs`/`appsscript.json` file here.

## After pushing

1. Open the Apps Script editor (`clasp open`), open `Config.gs`, fill in the
   `values` object inside `setupConfigFromValues()` (at minimum `SHEET_ID`;
   adjust `TEST_EMAIL` if you want test sends to land somewhere other than
   the default), select `setupConfigFromValues` in the function dropdown,
   click **Run**. Authorize the requested scopes (Sheets, Gmail, Drive
   readonly) — make sure you are authorizing as
   **prabhatkumarsictc12@gmail.com**.
2. Run `installTriggers` once (from the function dropdown, or reload the
   Sheet and use the "Job Outreach Automation" menu it adds).
3. Share the Job Outreach Google Sheet with
   `JOB_OUTREACH_SERVICE_ACCOUNT_EMAIL` (the backend's service account, so
   the FastAPI backend can read/write it) as an Editor.
4. Share the resume Drive file
   (`https://drive.google.com/file/d/1CijF9kbtlaTuay4iVsguC12Dnkc9lCc-/view`)
   with `prabhatkumarsictc12@gmail.com` (at least Viewer access), since
   that's the account whose Drive access the Apps Script queue worker uses
   to attach it.

## `.clasp.json` / `.claspignore`

`clasp create`/`clasp clone` write `.clasp.json` (and optionally
`.claspignore`) into this folder. These must never be committed — the root
`.gitignore` already has a line for `apps-script-job-outreach/.clasp.json`
(mirroring the existing `apps-script/.clasp.json` entry) and
`apps-script-job-outreach/.claspignore`.

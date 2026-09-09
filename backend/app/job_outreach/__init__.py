"""
Job Outreach module — a separate, standalone personal job-application system
sharing this repo/backend process with the existing job-intelligence/sales
outreach system (see root CLAUDE.md), but with its OWN Google Sheet, service
account, sender identity, and Apps Script project. Nothing in this package
is imported by, or imports from, the rest of app/ outside of small generic
utility helpers (app/utils/ids.py, app/utils/time_utils.py) that are safe to
share because they carry no state and no Botivate-specific behavior.

See docs/job-outreach-schema.md for the exact Sheet schema this package
implements against.
"""

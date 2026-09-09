# Google Sheets Database Schema (Source of Truth)

This document is the single source of truth for every sheet tab, its exact
column order, and the enums used across the backend, Apps Script, and
frontend. All three subsystems must match this file exactly.

Spreadsheet ID is provided via `GOOGLE_SHEETS_ID`. One spreadsheet, one tab
per entity, header row = row 1 (frozen), data starts row 2.

## Tabs (in creation order)

1. CONFIG
2. SEARCH_RUNS
3. JOBS
4. COMPANIES
5. CONTACTS
6. LEADS
7. EMAIL_TEMPLATES
8. EMAIL_DRAFTS
9. EMAIL_QUEUE
10. EMAIL_EVENTS
11. FOLLOW_UPS
12. FOLLOW_UP_TEMPLATES
13. REPLIES
14. CONVERSATIONS
15. CAMPAIGNS
16. SUPPRESSION_LIST
17. SOURCE_STATUS
18. ACTIVITY_LOG
19. LEAD_NOTES
20. SETTINGS

## CONFIG
`key | value | description | updated_at`

## SEARCH_RUNS
`run_id | query | job_title | state | city | sources | date_filter | experience | result_limit | results | qualified | companies | emails | leads | status | started_at | completed_at | error_message`

status: `PENDING | RUNNING | COMPLETED | FAILED | CANCELLED`

## JOBS
`job_id | source | source_job_id | job_title | company_id | company_name | location | city | state | country | description | experience | salary | employment_type | posted_date | skills | qualification | job_url | application_url | source_url | extraction_confidence | run_id | is_qualified | created_at | updated_at`

## COMPANIES
`company_id | company_name | normalized_name | official_website | domain | industry | city | state | country | phone | linkedin_url | company_description | website_confidence | research_status | created_at | updated_at`

research_status: `PENDING | RESEARCHING | COMPLETED | FAILED | NOT_FOUND`

## CONTACTS
`contact_id | company_id | contact_name | designation | email | email_type | email_source_url | email_confidence | phone | linkedin_url | verification_status | created_at | updated_at`

email_type: `GENERIC | HR | FOUNDER | DEPARTMENT | UNKNOWN`
verification_status: `UNVERIFIED | VERIFIED | INVALID`

## LEADS
`lead_id | company_id | job_id | contact_id | lead_score | botivate_opportunity_score | automation_signals | pain_points | recommended_solution | priority | status | owner | next_action | next_action_date | notes | created_at | updated_at | last_activity_at`

status (LEAD_STATUS): `NEW | QUALIFIED | EMAIL_DRAFTED | APPROVED | QUEUED | CONTACTED | REPLIED | FOLLOW_UP_DUE | FOLLOW_UP_SENT | IN_CONVERSATION | MEETING_REQUESTED | MEETING_SCHEDULED | MEETING_COMPLETED | PROPOSAL_SENT | INTERESTED | NOT_INTERESTED | BOUNCED | NO_RESPONSE | SUPPRESSED | WON | LOST | CLOSED`

recommended_solution: `AUTOROCKET | CUSTOM_AUTOMATION | BOTH | MANUAL_REVIEW`
priority: `LOW | MEDIUM | HIGH | URGENT`
next_action: `CALL | SEND_PROFILE | SEND_PRICING | SCHEDULE_MEETING | FOLLOW_UP | WAIT_FOR_REPLY | SEND_DEMO | SEND_PROPOSAL | NO_ACTION | CLOSE`

## EMAIL_TEMPLATES
`template_id | name | category | subject | plain_text_body | html_body | is_active | is_default | created_at | updated_at`

category: `INITIAL | FOLLOW_UP`

## EMAIL_DRAFTS
`email_id | lead_id | company_id | template_id | recipient_email | sender_email | subject | plain_text_body | html_body | personalization_points | facts_used | confidence | status | created_at | updated_at`

status: `DRAFT | APPROVED | REJECTED | QUEUED | SENT`

## EMAIL_QUEUE
`queue_id | email_id | lead_id | recipient_email | sender_email | subject | body | html_body | kind | priority | scheduled_at | status | attempts | max_attempts | last_attempt_at | sent_at | message_id | thread_id | error_message | test_mode | created_at | updated_at`

kind: `INITIAL | FOLLOW_UP | MANUAL`
status (QUEUE_STATUS): `PENDING | PROCESSING | SENT | RETRY | FAILED | CANCELLED | SKIPPED`

## EMAIL_EVENTS
`event_id | email_id | lead_id | company_id | event_type | timestamp | message_id | provider | metadata | created_at`

event_type: `CREATED | APPROVED | QUEUED | PROCESSING | SENT | DELIVERED | BOUNCED | FAILED | OPENED | CLICKED | REPLIED | FOLLOW_UP_SCHEDULED | FOLLOW_UP_SENT | CANCELLED`

## FOLLOW_UPS
`follow_up_id | lead_id | company_id | original_email_id | sequence_number | template_id | subject | body | html_body | scheduled_at | status | sent_at | message_id | reply_received | cancelled_at | cancel_reason | notes | created_at | updated_at`

status: `DRAFT | SCHEDULED | DUE | QUEUED | SENT | CANCELLED | SKIPPED | FAILED`

## FOLLOW_UP_TEMPLATES
`template_id | name | sequence_number | subject | body | is_active | created_at | updated_at`

## REPLIES
`reply_id | lead_id | company_id | email_id | thread_id | message_id | in_reply_to | from_email | from_name | to_email | subject | body_text | body_html | received_at | reply_type | sentiment | intent | ai_summary | requires_action | action_type | priority | suggested_response | created_at`

reply_type: `INTERESTED | REQUEST_FOR_DETAILS | MEETING_REQUEST | POSITIVE | NEUTRAL | NOT_INTERESTED | ASK_LATER | OUT_OF_OFFICE | BOUNCE | UNSUBSCRIBE | UNKNOWN`
sentiment: `POSITIVE | NEUTRAL | NEGATIVE`

## CONVERSATIONS
`conversation_id | lead_id | company_id | thread_id | status | last_message_at | last_message_direction | message_count | created_at | updated_at`

status: `ACTIVE | WAITING | CLOSED`
last_message_direction: `OUTBOUND | INBOUND`

## CAMPAIGNS
`campaign_id | name | description | job_title | state | city | sources | template_id | status | created_at | updated_at`

status: `DRAFT | ACTIVE | PAUSED | COMPLETED | ARCHIVED`

## SUPPRESSION_LIST
`suppression_id | email | company_id | reason | source | created_at`

reason: `UNSUBSCRIBE | BOUNCE | MANUAL | COMPLAINT`

## SOURCE_STATUS
`source | display_name | enabled | last_status | last_checked_at | notes`

last_status: `OK | BLOCKED | UNAVAILABLE | RATE_LIMITED`

## ACTIVITY_LOG
`activity_id | lead_id | company_id | activity_type | description | metadata | created_at | created_by`

## LEAD_NOTES
`note_id | lead_id | note | created_by | created_at`

## SETTINGS
`key | value | description | updated_at`
(app-level toggles: AUTO_SEND, AUTO_REPLY, AUTO_FOLLOWUP_AUTOMATION, MAX_FOLLOW_UPS, QUEUE_BATCH_SIZE, QUEUE_MAX_ATTEMPTS)

---
All timestamps are ISO-8601 UTC strings. All IDs are UUID v4 strings prefixed
by entity type (e.g. `job_`, `cmp_`, `lead_`, `eml_`, `fu_`, `rpl_`, `evt_`,
`run_`, `camp_`, `sup_`, `act_`, `note_`, `tpl_`, `q_`).

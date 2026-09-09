# Email Send / Delivery / Open Tracking

## What we actually track (real signals only)
| Event | Source | Reliable? |
|---|---|---|
| `SENT` | Apps Script confirms `GmailApp.sendEmail()` succeeded | Yes |
| `FAILED` | Apps Script catches a send exception | Yes |
| `REPLIED` | ReplyScanner finds a genuinely new inbound message on a tracked thread | Yes |
| `FOLLOW_UP_SENT` | FollowUpWorker confirms a queued follow-up sent | Yes |
| `CANCELLED` | User action or reply-triggered auto-cancel | Yes |
| `DELIVERED` | **Not implemented** — GmailApp has no delivery-confirmation API | No |
| `BOUNCED` | **Not implemented** unless a bounce arrives as a message Gmail can detect (best-effort only; not guaranteed) | Partial |
| `OPENED` / `CLICKED` | **Not implemented** — no tracking pixel/link-wrapping is used | No |

## Frontend contract
Per System.txt rules #22-23, #76: the frontend must never claim a status
stronger than what's known. Any email whose status is `SENT` but has no
`DELIVERED`/`BOUNCED` event must display:

> **SENT — DELIVERY STATUS UNKNOWN**

Any email with no `OPENED` event must display open status as:

> **OPEN TRACKING NOT AVAILABLE**

These are literal strings the frontend should render — not silently omit
the field, so the limitation is visible rather than implied.

## Why we didn't add a tracking pixel
Adding a 1x1 tracking pixel or link-wrapping for open/click tracking is a
deliberate choice, not an oversight: it requires hosting a tracking
endpoint, degrades in most modern email clients (image blocking, Gmail
image proxying breaks IP/timing accuracy), and — per the rule against
fabricating or overstating tracking data — we'd rather clearly say
"not available" than ship an unreliable signal presented as fact. If this
is required later, `docs/architecture.md` notes where such an endpoint
would hook in.

## Bounce handling
If GmailApp surfaces a bounce as an inbound message (varies by provider and
is not guaranteed), `ReplyScanner.gs` cannot distinguish it perfectly from
a real reply today — this is a known limitation. Do not rely on automatic
bounce suppression; use the manual "mark as bounced" path (`lead.status =
BOUNCED` via `PATCH /api/leads/{id}`) which also feeds
`SUPPRESSION_LIST` via the existing suppression flow when appropriate.

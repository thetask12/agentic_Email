// Mirrors backend/docs/sheet-schema.md exactly. Keep in sync.

export type LeadStatus =
  | "NEW" | "QUALIFIED" | "EMAIL_DRAFTED" | "APPROVED" | "QUEUED" | "CONTACTED"
  | "REPLIED" | "FOLLOW_UP_DUE" | "FOLLOW_UP_SENT" | "IN_CONVERSATION"
  | "MEETING_REQUESTED" | "MEETING_SCHEDULED" | "MEETING_COMPLETED" | "PROPOSAL_SENT"
  | "INTERESTED" | "NOT_INTERESTED" | "BOUNCED" | "NO_RESPONSE" | "SUPPRESSED"
  | "WON" | "LOST" | "CLOSED";

export type QueueStatus = "PENDING" | "PROCESSING" | "SENT" | "RETRY" | "FAILED" | "CANCELLED" | "SKIPPED";
export type FollowUpStatus = "DRAFT" | "SCHEDULED" | "DUE" | "QUEUED" | "SENT" | "CANCELLED" | "SKIPPED" | "FAILED";
export type EmailDraftStatus = "DRAFT" | "APPROVED" | "REJECTED" | "QUEUED" | "SENT";
export type ReplyType =
  | "INTERESTED" | "REQUEST_FOR_DETAILS" | "MEETING_REQUEST" | "POSITIVE" | "NEUTRAL"
  | "NOT_INTERESTED" | "ASK_LATER" | "OUT_OF_OFFICE" | "BOUNCE" | "UNSUBSCRIBE" | "UNKNOWN";
export type Sentiment = "POSITIVE" | "NEUTRAL" | "NEGATIVE";
export type Priority = "LOW" | "MEDIUM" | "HIGH" | "URGENT";
export type ResearchStatus = "PENDING" | "RESEARCHING" | "COMPLETED" | "FAILED" | "NOT_FOUND";
export type RecommendedSolution = "AUTOROCKET" | "CUSTOM_AUTOMATION" | "BOTH" | "MANUAL_REVIEW";
export type SearchRunStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
export type CampaignStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "COMPLETED" | "ARCHIVED";

export interface Job {
  job_id: string;
  source: string;
  source_job_id: string;
  job_title: string;
  company_id: string;
  company_name: string;
  location: string;
  city: string;
  state: string;
  country: string;
  description: string;
  experience: string;
  salary: string;
  employment_type: string;
  posted_date: string;
  skills: string;
  qualification: string;
  job_url: string;
  application_url: string;
  source_url: string;
  extraction_confidence: number;
  run_id: string;
  is_qualified: boolean;
  created_at: string;
  updated_at: string;
}

export interface Company {
  company_id: string;
  company_name: string;
  normalized_name: string;
  official_website: string;
  domain: string;
  industry: string;
  city: string;
  state: string;
  country: string;
  phone: string;
  linkedin_url: string;
  company_description: string;
  website_confidence: number;
  research_status: ResearchStatus;
  created_at: string;
  updated_at: string;
  jobs?: Job[];
  contacts?: Contact[];
  leads?: Lead[];
}

export interface Contact {
  contact_id: string;
  company_id: string;
  contact_name: string;
  designation: string;
  email: string;
  email_type: string;
  email_source_url: string;
  email_confidence: number;
  phone: string;
  linkedin_url: string;
  verification_status: string;
  created_at: string;
  updated_at: string;
}

export interface Lead {
  lead_id: string;
  company_id: string;
  job_id: string;
  contact_id: string;
  lead_score: number;
  botivate_opportunity_score: number;
  automation_signals: string;
  pain_points: string;
  recommended_solution: RecommendedSolution;
  priority: Priority;
  status: LeadStatus;
  owner: string;
  next_action: string;
  next_action_date: string;
  notes: string;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
  company_name?: string;
  job_title?: string;
  source?: string;
  email_sent?: boolean;
  sent_at?: string;
  has_reply?: boolean;
  follow_up_count?: number;
}

export interface LeadDetail extends Omit<Lead, "notes"> {
  company: Company;
  job: Job;
  contact: Contact;
  email_drafts: EmailDraft[];
  email_queue: EmailQueueItem[];
  replies: Reply[];
  follow_ups: FollowUp[];
  activity: ActivityLogEntry[];
  notes: LeadNote[];
  conversations: Conversation[];
}

export interface EmailTemplate {
  template_id: string;
  name: string;
  category: "INITIAL" | "FOLLOW_UP";
  subject: string;
  plain_text_body: string;
  html_body: string;
  is_active: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmailDraft {
  email_id: string;
  lead_id: string;
  company_id: string;
  template_id: string;
  recipient_email: string;
  sender_email: string;
  subject: string;
  plain_text_body: string;
  html_body: string;
  personalization_points: string;
  facts_used: string;
  confidence: number;
  status: EmailDraftStatus;
  created_at: string;
  updated_at: string;
}

export interface EmailQueueItem {
  queue_id: string;
  email_id: string;
  lead_id: string;
  recipient_email: string;
  sender_email: string;
  subject: string;
  body: string;
  html_body: string;
  kind: "INITIAL" | "FOLLOW_UP" | "MANUAL";
  priority: string;
  scheduled_at: string;
  status: QueueStatus;
  attempts: number;
  max_attempts: number;
  last_attempt_at: string;
  sent_at: string;
  message_id: string;
  thread_id: string;
  error_message: string;
  test_mode: boolean;
  created_at: string;
  updated_at: string;
}

export interface FollowUp {
  follow_up_id: string;
  lead_id: string;
  company_id: string;
  original_email_id: string;
  sequence_number: number;
  template_id: string;
  subject: string;
  body: string;
  html_body: string;
  scheduled_at: string;
  status: FollowUpStatus;
  sent_at: string;
  message_id: string;
  reply_received: boolean;
  cancelled_at: string;
  cancel_reason: string;
  notes: string;
  created_at: string;
  updated_at: string;
  company_name?: string;
  overdue?: boolean;
}

export interface Reply {
  reply_id: string;
  lead_id: string;
  company_id: string;
  email_id: string;
  thread_id: string;
  message_id: string;
  from_email: string;
  from_name: string;
  to_email: string;
  subject: string;
  body_text: string;
  body_html: string;
  received_at: string;
  reply_type: ReplyType;
  sentiment: Sentiment;
  intent: string;
  ai_summary: string;
  requires_action: boolean;
  action_type: string;
  priority: Priority;
  suggested_response: string;
  created_at: string;
  company_name?: string;
  owner?: string;
  lead_status?: LeadStatus;
}

export interface Conversation {
  conversation_id: string;
  lead_id: string;
  company_id: string;
  thread_id: string;
  status: "ACTIVE" | "WAITING" | "CLOSED";
  last_message_at: string;
  last_message_direction: "OUTBOUND" | "INBOUND";
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  direction: "OUTBOUND" | "INBOUND";
  timestamp: string;
  subject: string;
  body: string;
  kind?: string;
  message_id?: string;
  from_email?: string;
  reply_type?: string;
  sentiment?: string;
  ai_summary?: string;
  suggested_response?: string;
}

export interface ActivityLogEntry {
  activity_id: string;
  lead_id: string;
  company_id: string;
  activity_type: string;
  description: string;
  metadata: string;
  created_at: string;
  created_by: string;
}

export interface LeadNote {
  note_id: string;
  lead_id: string;
  note: string;
  created_by: string;
  created_at: string;
}

export interface Campaign {
  campaign_id: string;
  name: string;
  description: string;
  job_title: string;
  state: string;
  city: string;
  sources: string;
  template_id: string;
  status: CampaignStatus;
  created_at: string;
  updated_at: string;
  funnel?: {
    jobs: number;
    leads: number;
    emails_sent: number;
    replies: number;
    interested: number;
    meetings: number;
  };
}

export interface SearchRun {
  run_id: string;
  query: string;
  job_title: string;
  state: string;
  city: string;
  sources: string;
  date_filter: string;
  experience: string;
  result_limit: number;
  results: number;
  qualified: number;
  companies: number;
  emails: number;
  leads: number;
  status: SearchRunStatus;
  started_at: string;
  completed_at: string;
  error_message: string;
}

export interface SourceStatus {
  source: string;
  display_name: string;
  enabled: boolean;
  last_status: string;
  last_checked_at: string;
  notes: string;
}

export interface DashboardData {
  email_test_mode: boolean;
  totals: Record<string, number>;
  today: Record<string, number>;
  follow_up_alerts: { due_today: number; overdue: number; upcoming: number };
  pipeline: Record<string, number>;
}

export interface AnalyticsData {
  leads_by_state: Record<string, number>;
  leads_by_source: Record<string, number>;
  leads_by_job_title: Record<string, number>;
  emails_by_day: Record<string, number>;
  replies_by_day: Record<string, number>;
  follow_ups_by_day: Record<string, number>;
  reply_rate: number;
  positive_reply_rate: number;
  meeting_rate: number;
  total_leads: number;
  total_sent: number;
  opportunity_score_distribution: Record<string, number>;
  pipeline: Record<string, number>;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
}

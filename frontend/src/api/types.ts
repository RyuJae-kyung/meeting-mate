export type Basis = 'fact' | 'inference' | 'uncertain'
export interface BriefingItem { text: string; basis: Basis; source: string | null }

export interface User {
  id: number; email: string; name: string; job_title: string | null; role: 'member' | 'admin'
  email_notifications: boolean; created_at: string
}

export interface Participant {
  id: number; meeting_id: number; name: string; email: string; role: string; responsibility: string
  access_token: string | null; created_at: string
}

export interface Material {
  id: number; original_filename: string; file_type: string; size_bytes: number; status: 'processed' | 'failed'
  error: string | null; title: string | null; summary: string | null; summary_source: string | null
  keywords: string[]; uploaded_at: string
}
export interface MaterialDetail extends Material { extracted_text: string; segments: { loc: string; text: string }[] }

export type MeetingStatus = 'scheduled' | 'ready' | 'completed'
export interface MeetingListItem {
  id: number; title: string; purpose: string; start_at: string; end_at: string | null; location: string | null
  online_url: string | null; status: MeetingStatus; owner_id: number; participant_count: number
  material_count: number; has_briefing: boolean
}
export interface MeetingDetail extends MeetingListItem {
  agenda: string; agenda_items: string[]; created_at: string; updated_at: string; can_edit: boolean
  owner_name: string; participants: Participant[]; materials: Material[]
}

export interface GeneralBriefingContent {
  purpose_summary: BriefingItem[]; agenda_items: BriefingItem[]; expected_discussions: BriefingItem[]
  pre_questions: BriefingItem[]; checklist: BriefingItem[]; issues: BriefingItem[]; material_summaries: BriefingItem[]
}
export interface PersonalBriefingContent {
  focus_summary: string; key_agenda: BriefingItem[]; materials_to_review: BriefingItem[]
  expected_questions: BriefingItem[]; preparation: BriefingItem[]; related_terms: string[]
}
export interface Briefing<T = Record<string, unknown>> {
  id: number; meeting_id: number; participant_id: number | null; content: T; source: 'openai' | 'mock'
  model: string | null; is_edited: boolean; created_at: string; updated_at: string
}
export interface GlossaryTerm {
  id: number; meeting_id: number; term: string; easy_explanation: string; work_meaning: string
  related_concepts: string[]; context: string; source_ref: string | null; why_important: string
  is_uncertain: boolean; source: string; is_edited: boolean
}
export interface GenerateResult {
  source: string; general_briefing_id: number; glossary_count: number; participant_briefing_count: number
  meeting_status: MeetingStatus; warnings: string[]
}
export interface EmailLog {
  id: number; meeting_id: number; participant_id: number | null; job_id: number | null; recipient: string
  email_type: string; subject: string; status: 'sent' | 'failed' | 'retrying'; provider: string
  provider_message_id: string | null; error: string | null; attempts: number; sent_at: string | null; created_at: string
}
export interface EmailJob {
  id: number; meeting_id: number; participant_ids: number[]; mode: 'now' | 'scheduled' | 'before_meeting'
  minutes_before: number | null; scheduled_at: string; status: string; error: string | null
  created_at: string; processed_at: string | null
}
export interface EmailPreview { to: string; subject: string; html: string; provider: string }
export interface Dashboard {
  upcoming: MeetingListItem[]; recent: MeetingListItem[]; ready: MeetingListItem[]
  recent_emails: EmailLog[]; pending_email_jobs: EmailJob[]
  counts: { scheduled: number; ready: number; completed: number; failed_emails: number }
}
export interface SystemStatus {
  ai_provider: string; ai_model: string | null; email_provider: string; email_from: string
  scheduler_enabled: boolean; scheduler_interval_seconds: number; calendar: string
  max_upload_mb: number; allowed_file_types: string[]
}
export interface PublicBriefing {
  meeting_title: string; meeting_purpose: string; start_at: string; end_at: string | null; location: string | null
  online_url: string | null; agenda_items: string[]; participant_name: string; participant_role: string
  participant_responsibility: string; personal: Briefing<PersonalBriefingContent> | null
  checklist: BriefingItem[]; glossary: GlossaryTerm[]
}

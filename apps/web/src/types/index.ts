export type UserRole =
  | "admin"
  | "dispatcher"
  | "doctor"
  | "driver"
  | "nurse"
  | "lab_tech"
  | "pharmacist"
  | "ward_manager";
export type PresenceStatus =
  | "active"
  | "break"
  | "available"
  | "busy"
  | "offline"
  | "duty_rounds"
  | "in_surgery"
  | "emergency"
  | "on_leave"
  | "unavailable"
  | "en_route"
  | "on_scene"
  | "transporting";


export interface Organization {
  id: string;
  name: string;
  city?: string;
  domain?: string;
  twilioWebhookUrl?: string;
  timezone: string;
}

export interface UserProfile {
  id: string;
  orgId: string;
  email: string;
  fullName: string;
  role: UserRole;
  presenceStatus: PresenceStatus;
  specialization?: string;
  isArchived?: boolean;
  archivedAt?: string;
  archivedUntil?: string;
}

export type AuditActionType =
  | "ROLE_CHANGE"
  | "STATUS_CHANGE"
  | "SOFT_DELETE"
  | "RESTORE_USER"
  | "ADD_USER"
  | "LEAVE_APPROVE"
  | "LEAVE_REJECT";

export interface AdminAuditLog {
  id: string;
  adminId: string;
  adminEmail: string;
  targetUserId: string;
  targetUserName: string;
  actionType: AuditActionType;
  oldState: string;
  newState: string;
  timestamp: string;
}

export interface SystemAuditLog {
  id: string;
  actorId: string;
  actorEmail: string;
  targetId: string | null;
  targetName: string | null;
  actionType: string;
  oldState: any;
  newState: any;
  metadata?: any;
  createdAt: string;
}

export type LeaveStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface DoctorLeave {
  id: string;
  orgId: string;
  doctorId: string;
  doctorName?: string;
  startDate: string;
  endDate: string;
  reason: string;
  status: LeaveStatus;
  reviewedBy?: string;
  reviewedAt?: string;
  createdAt: string;
}

export interface PrescriptionItem {
  drug: string;
  prescribedOn?: string;
  courseDuration?: string;
}

export interface PatientRecord {
  id: string;
  orgId: string;
  phoneNumber: string;
  firstName: string;
  lastName: string;
  dob?: string;
  gender?: string;
  bloodGroup?: string;
  email?: string;
  address?: string;
  emergencyContactName?: string;
  emergencyContactPhone?: string;
  hipaaConsentGiven?: boolean;
  age?: number;
  lastVisitDate?: string;
  symptoms?: string[];
  chronicConditions?: string[];
  allergies?: string[];
  prescriptions?: PrescriptionItem[];
  medicalHistory?: Record<string, any>;
  createdByType?: "VOICE_AI" | "DISPATCHER" | "DOCTOR";
  createdBy?: string;
  createdAt: string;
}

export interface AppointmentRecord {
  id: string;
  orgId: string;
  patientId: string;
  patientName?: string;
  patientPhone?: string;
  doctorId?: string;
  doctorName?: string;
  specialization?: string;
  startTime: string;
  endTime: string;
  status: "scheduled" | "in_progress" | "completed" | "no_show" | "cancelled";
  chiefComplaint?: string;
  doctorNotes?: string;
  bookedByType?: "dispatcher" | "ai_agent";
  bookedByName?: string;
  verificationStatus?: "verified" | "pending_review" | "auto_confirmed" | "rejected";
  autoConfirmDeadline?: string;
  audioRecordingUrl?: string;
  cancellationReason?: string;
  createdAt: string;
}

export interface DoctorRecommendationItem {
  doctor_id: string;
  doctor_name: string;
  specialization: string;
  match_score: number;
  match_reason: string;
  presence_status?: string;
  status_note?: string;
  estimated_return_time?: string;
  next_available_slot: string | null;
  available_slots_count: number;
  active_load_count: number;
}

export interface DoctorRecommendationResponse {
  cause: string;
  detected_specialty: string;
  urgency?: 'OPD_ROUTINE' | 'OPD_URGENT' | 'ER_EMERGENCY_OVERRIDE';
  clinical_explanation?: string;
  has_on_duty_specialists?: boolean;
  specialists_on_duty_count?: number;
  fallback_recommendation?: string;
  recommendations: DoctorRecommendationItem[];
}

export interface VoiceSimulatorModalProps {
  isOpen: boolean;
  onClose: () => void;
  orgId?: string;
}

export interface ChatTurn {
  sender: 'user' | 'ai';
  text: string;
  timestamp: string;
  isFiller?: boolean;
}

export interface AudioQueueItem {
  b64: string;
  eventType: 'AI_FILLER' | 'AI_RESPONSE' | 'AUDIO_CHUNK';
  text: string;
}

export interface VoiceDirective {
  id: string;
  org_id: string;
  org_name?: string;
  category: string;
  directive_type: 'DO_SAY' | 'DO_NOT_SAY' | 'STYLE' | 'FAQ';
  instruction: string;
  is_active: boolean;
  priority: number;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface GuardrailViolation {
  id: string;
  session_id?: string;
  turn_number: number;
  ai_response_text: string;
  matched_rule: string;
  action_taken: 'HARD_BLOCKED' | 'SOFT_FLAGGED' | 'ALLOWED';
  created_at?: string;
}

export interface VoiceCallSessionRecord {
  id: string;
  org_id: string;
  org_name?: string;
  caller_phone: string;
  caller_name: string;
  session_type: string;
  triage_status: string;
  call_outcome: string;
  total_turns: number;
  duration_seconds: number;
  full_transcript?: string;
  sentiment_score?: string;
  security_flagged?: boolean;
  audio_recording_url?: string;
  room_name?: string;
  start_time: string;
  end_time?: string;
}

export interface VoiceCallTurnRecord {
  id: string;
  session_id: string;
  org_id: string;
  turn_number: number;
  user_transcript: string;
  user_audio_url?: string;
  ai_filler_text?: string;
  ai_filler_audio_url?: string;
  ai_response_text: string;
  ai_response_audio_url?: string;
  stt_latency_ms?: number;
  llm_latency_ms?: number;
  tts_latency_ms?: number;
  total_latency_ms?: number;
  created_at: string;
}

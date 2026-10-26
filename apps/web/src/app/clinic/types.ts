export interface BillItem {
  id?: string;
  name: string;
  quantity?: number;
  unit_price?: number;
  amount: number;
  category?: 'consultation' | 'medicine' | 'procedure' | 'other' | string;
}

export interface VisitChargeType {
  id: string;
  name: string;
  fee: number;
  active?: boolean;
}

export interface ClinicBillingCatalogItem {
  id: string;
  name: string;
  unit_price: number;
  category: 'medicine' | 'procedure' | 'other' | string;
  unit?: string;
  active?: boolean;
}

export interface ClinicBillingCatalog {
  visit_charge_types: VisitChargeType[];
  billing_catalog: ClinicBillingCatalogItem[];
  consultation_fee?: number | null;
  currency_symbol?: string | null;
}

export interface AppointmentItem {
  gender?: string | null;
  blood_group?: string | null;
  address?: string | null;
  dob?: string | null;
  reported_age?: number | null;
  age_unit?: 'years' | 'months' | null;
  bill_finalized_at?: string | null;
  urgency_reason?: string | null;
  doctor_name?: string | null;
  id: string;
  patient_id?: string;
  patient_name: string;
  patient_phone: string;
  appointment_date?: string;
  appointment_time?: string;
  status:
    | "scheduled"
    | "arrived"
    | "in_progress"
    | "completed"
    | "cancelled"
    | "skipped"
    | "no_show";
  chief_complaint?: string;
  source: "ai_voice" | "walk_in" | "manual";
  payment_status: "paid" | "pending";
  payment_method?: string | null;
  fee: number;
  amount_paid?: number;
  balance_due?: number;
  payment_receipts?: Array<{ id: string; amount: number; method: string; reference?: string | null; received_at: string; received_by?: string | null; received_by_name?: string | null }>;
  bill_items?: BillItem[];
  token_number?: number | null;
  display_token?: string | null;
  token_prefix?: "T" | "W" | "R" | null;
  shift_type?: "MORNING" | "EVENING" | null;
  doctor_id?: string | null;
  appointment_window_start?: string | null;
  appointment_window_end?: string | null;
  consultation_started_at?: string | null;
  consultation_ended_at?: string | null;
  actual_duration_seconds?: number | null;
  call_count?: number | null;
  checked_in_at?: string | null;
  called_at?: string | null;
  queue_state?: "not_checked_in" | "waiting" | "called" | "stepped_out" | "served" | null;
  encounter_state?: "not_started" | "in_progress" | "completed" | null;
  created_at?: string;
  doctor_notes?: string | null;
  recent_diagnosis?: string | null;
}

export interface VisitEventItem {
  id: string;
  visit_id: string;
  org_id: string;
  event_type: string;
  occurred_at: string;
  actor_id?: string | null;
  actor_type?: string;
  notes?: string | null;
  metadata?: Record<string, any>;
}

export interface CapacityHourlyBucket {
  hour_label: string;
  total_slots: number;
  booked_slots: number;
  available_slots: number;
  in_queue_clearance_zone: boolean;
  slots: {
    time: string;
    is_booked: boolean;
    is_in_clearance: boolean;
  }[];
}

export interface ClinicSlotItem {
  time_label: string;
  window_label?: string;
  recommended_arrival?: string;
  session: "morning" | "evening" | "overtime";
  start_time: string;
  end_time: string;
  is_available: boolean;
  status_type:
    | "AVAILABLE"
    | "BOOKED"
    | "NO_SHOW"
    | "IN_PROGRESS"
    | "COMPLETED"
    | "CANCELLED"
    | "CLOSED";
  window_state?: "OPEN" | "LIMITED" | "CLOSED" | "PAST";
  is_past?: boolean;
  booking_quota?: number;
  theoretical_capacity?: number;
  booked_count?: number;
  booked_patients?: Array<{
    appointment_id: string;
    patient_name: string;
    patient_phone: string;
    chief_complaint?: string;
    status: string;
    source: string;
    payment_status?: string;
    appointment_time?: string;
  }>;
  appointment_id?: string | null;
  patient_name?: string | null;
  patient_phone?: string | null;
  chief_complaint?: string | null;
  source?: "ai_voice" | "walk_in" | "manual" | null;
  payment_status?: "paid" | "pending" | null;
  is_overtime?: boolean;
}

export interface ClinicDailySlotsResponse {
  org_id: string;
  target_date: string;
  is_open: boolean;
  reason?: string;
  slot_duration_minutes: number;
  slot_buffer_minutes: number;
  window_duration_minutes?: number;
  booking_quota_per_window?: number;
  max_daily_patients: number;
  total_booked: number;
  is_capacity_reached: boolean;
  slots: ClinicSlotItem[];
  emergency_phone?: string;
  closure?: {
    id: string;
    title: string;
    override_type: string;
    start_date: string;
    end_date: string;
    reason?: string;
    emergency_phone?: string;
  };
}

export interface QueuePatient {
  token: string;
  name: string;
  age: string;
  gender: string;
  type: string;
  slot: string;
  waitMins: string;
  reason: string;
  feeStatus: string;
  isCurrent: boolean;
}

export interface QuickBookingFormData {
  patientName: string;
  phone: string;
  slotTime: string;
  appointmentDate: string;
  type: string;
  symptoms: string;
  fee: string;
}

export interface ClinicPreviousVisit {
  appointment_id: string;
  date: string;
  time?: string;
  chief_complaint?: string;
  doctor_notes?: string;
  recent_diagnosis?: string;
  status?: string;
  token?: string;
}

export interface ClinicLivePatient {
  appointment_id: string;
  patient_id?: string;
  patient_name: string;
  patient_phone: string;
  appointment_time: string;
  start_time?: string;
  end_time?: string;
  status: AppointmentItem["status"];
  chief_complaint?: string;
  doctor_notes?: string;
  fee: number;
  payment_status: "paid" | "pending";
  source: "ai_voice" | "walk_in" | "manual";
  gender?: string | null;
  blood_group?: string | null;
  display_token?: string | null;
  age?: string | null;
  dob?: string | null;
  recent_diagnosis?: string | null;
  allergies?: string[];
  chronic_conditions?: string[];
  previous_visits?: ClinicPreviousVisit[];
  bill_items?: BillItem[];
}

export interface ClinicEmergencyCallback {
  session_id: string;
  caller_phone: string;
  emergency_reason: string;
  call_time: string;
  duration_seconds: number;
  severity: string;
  audio_url?: string | null;
  transcript_snippet?: string | null;
}

export interface ClinicDashboardSummary {
  total_today: number;
  completed_count: number;
  in_room_count: number;
  waiting_count: number;
  no_show_count: number;
  revenue_collected: number;
  revenue_pending: number;
}

export interface ClinicLiveDashboardData {
  doctor_name: string;
  clinic_name: string;
  specialty: string;
  today_date: string;
  today_date_label: string;
  summary: ClinicDashboardSummary;
  active_patient: ClinicLivePatient | null;
  next_patient: ClinicLivePatient | null;
  waiting_queue: ClinicLivePatient[];
  emergency_callbacks: ClinicEmergencyCallback[];
}

export interface ClinicAnalyticsDailyTrend {
  date: string;
  day_label: string;
  total: number;
  completed: number;
  no_show: number;
}

export interface ClinicAnalyticsData {
  org_id: string;
  clinic_name: string;
  lead_doctor_name: string;
  period?: "week" | "month" | "year";
  total_appointments?: number;
  completed_count?: number;
  completion_rate_pct?: number;
  no_show_rate_pct: number;
  slot_utilization_pct: number;
  total_patients_registered: number;
  total_revenue?: number;
  upi_revenue?: number;
  cash_revenue?: number;
  source_breakdown: {
    ai_voice: number;
    walk_in: number;
    manual: number;
  };
  daily_trends: ClinicAnalyticsDailyTrend[];
  total_appointments_30d?: number;
  completed_count_30d?: number;
}

export interface ClinicRevenueTransactionItem {
  id: string;
  patient_name: string;
  patient_phone: string;
  fee_amount: number;
  amount_paid?: number;
  balance_due?: number;
  status: "settled" | "pending";
  payment_method: "UPI" | "Cash" | "Card" | "Pending";
  source: string;
  appointment_date: string;
  appointment_time: string;
  collected_at?: string | null;
  collected_date?: string | null;
  collected_time?: string | null;
  bill_items?: BillItem[];
}

export interface ClinicRevenueResponse {
  org_id: string;
  period: "today" | "week" | "month" | "all";
  total_settled: number;
  total_pending: number;
  upi_total: number;
  cash_total: number;
  transactions: ClinicRevenueTransactionItem[];
  currency_code?: string | null;
  currency_symbol?: string | null;
}

export interface CallSessionRecord {
  id: string;
  caller_phone: string;
  caller_name: string;
  time_ago: string;
  duration: string;
  call_outcome:
    | "appointment_booked"
    | "timing_inquiry"
    | "rescheduled"
    | "deflected_emergency";
  language: string;
  transcript_preview: string;
  whatsapp_sent: boolean;
  audio_url?: string;
}

export interface ClinicCallSessionItem {
  full_transcript?: string | null;
  recording_status?: string | null;
  turns?: { role: string; text: string; offset_seconds?: number }[];
  patient_id?: string | null;
  patient_name?: string | null;
  id: string;
  caller_phone: string;
  caller_name: string;
  start_time: string;
  duration_seconds: number;
  triage_status: string;
  call_outcome: string;
  missed_reason?: string | null;
  handled_by: string;
  is_missed?: boolean;
  summary: string;
  audio_recording_url?: string | null;
}

export interface EscalationItem {
  id: string;
  title: string;
  patient: string;
  phone: string;
  detail: string;
  time: string;
  urgency: "critical" | "high" | "medium";
  actionType: "call" | "refill" | "lab";
}

export interface Escalation {
  id: string;
  type: "callback" | "refill" | "lab";
  patient: string;
  phone: string;
  age: string;
  gender: string;
  time: string;
  urgency: "critical" | "high" | "normal";
  summary: string;
  notes: string;
  status: "pending" | "resolved";
}

export interface PatientRecordItem {
  id: string;
  name: string;
  phone: string;
  dob?: string | null;
  gender?: string | null;
  blood_group?: string | null;
  age_gender: string;
  last_visit: string;
  total_visits: number;
  allergies?: string;
  chronic_conditions?: string;
  recent_diagnosis?: string;
  notes?: string[];
  note_entries?: { id: string; text: string; created_at: string; author_name: string; author_id?: string | null }[];
  visit_history?: { id: string; date: string | null; status: string; doctor_notes?: string; diagnosis?: string }[];
}

export interface FeeTransaction {
  id: string;
  patient_name: string;
  appointment_time: string;
  fee_amount: number;
  payment_method: "UPI" | "Cash" | "Card" | "Pending";
  collected_at: string;
  status: "settled" | "pending";
}

export interface EmergencyBlock {
  id: string;
  date: string;
  scope: "full_day" | "remainder_of_day";
  blockedFromTime?: string;
  reason: string;
  createdAt: string;
}

export interface DoctorLeave {
  id: string;
  startDate: string;
  endDate: string;
  reason: string;
  createdAt: string;
  collisionAction?: "prepone" | "postpone" | "manual_triage";
}

export interface DateOverride {
  id: string;
  date: string;
  overrideType: "open_special" | "custom_hours" | "closed_special";
  morningStart?: string;
  morningEnd?: string;
  eveningStart?: string;
  eveningEnd?: string;
  reason?: string;
}

export interface RescheduleSuggestion {
  date: string;
  slotTime: string;
  isSpilloverBuffer: boolean;
  availableRemainingCapacity: number;
}

export interface RescheduleAuditItem {
  id: string;
  appointmentId: string;
  patientName: string;
  patientPhone: string;
  originalDate: string;
  originalSlot: string;
  newDate: string;
  newSlot: string;
  triggerReason: "emergency_block" | "doctor_leave" | "manual_doctor_transfer";
  notificationStatus: "sent" | "pending" | "failed";
  createdAt: string;
}

export interface DaySchedule {
  isOpen: boolean;
  morningStart: string;
  morningEnd: string;
  eveningStart: string;
  eveningEnd: string;
  windows?: Array<{ name: string; start: string; end: string }>;
}

export interface ClinicClosureItem {
  id: string;
  org_id: string;
  doctor_id?: string | null;
  title: string;
  override_type?: 'vacation' | 'emergency_closure' | 'special_hours';
  is_available?: boolean;
  start_date: string;
  end_date: string;
  custom_hours?: Array<{ name?: string; start: string; end: string }> | null;
  reason?: string | null;
  emergency_phone?: string | null;
  created_at: string;
}

export type ScheduleOverrideItem = ClinicClosureItem;

export interface VoicePersona {
  id: string;
  label: string;
  desc: string;
  provider: "deepgram" | "gemini";
  sampleAudio?: string;
  tier: "starter" | "pro";
  category: "standard" | "studio";
  gender: "feminine" | "masculine";
  accent: string;
  language: string;
  badge?: string;
  role?: string;
  tone?: string;
  defaultPhrase?: string;
}

export interface LanguageOption {
  id: string;
  name: string;
  nativeName: string;
  flag: string;
  region: "indian" | "global";
  category?: string;
  defaultPhrase: string;
  transliteratedPhrase?: string;
  scriptPhrase?: string;
  voices: string[];
}

export interface LanguageMode {
  id: string;
  label: string;
  desc: string;
}

export interface CountryEmergencyProfile {
  code: string;
  name: string;
  emergencyPhone: string;
  backupEmergencyPhone?: string;
  currency: string;
  currencySymbol: string;
}

export interface ClinicProfile {
  clinicName: string;
  doctorName: string;
  doctorEmail: string;
  doctorPhone: string;
  registrationNumber: string;
  city: string;
  clinicAddress: string;
  timezone: string;
  specialty: string;
  consultationFee: string;
  emergencyPhone: string;
  defaultGreetingPrompt: string;
}

export interface GreetingLanguage {
  id: "en" | "hi" | "kn" | "te" | "ta" | "mr" | "bn" | "gu";
  name: string;
  nativeName: string;
  flag: string;
  template: string;
  scriptTemplate?: string;
  friendlyTemplate?: string;
  conciseTemplate?: string;
}

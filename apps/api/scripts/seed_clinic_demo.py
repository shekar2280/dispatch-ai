import argparse
import asyncio
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from pathlib import Path
import sys
import uuid
import zoneinfo

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy.future import select
from sqlalchemy import delete, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models.organization import Organization
from app.models.user import User
from app.models.clinic_membership import ClinicMembership
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.payment_receipt import PaymentReceipt
from app.models.call_session import CallLog
from app.models.call_turn import VoiceCallTurn
from app.models.schedule_override import ScheduleOverride
from app.models.visit_event import VisitEvent
from app.models.audit_log import SystemAuditLog

UTC = zoneinfo.ZoneInfo("UTC")

async def run_seed(org_id: uuid.UUID, anchor_date: date):
    async with AsyncSessionLocal() as db:
        org = await db.get(Organization, org_id)
        if not org:
            raise RuntimeError(f"Organization {org_id} not found")

        tz = zoneinfo.ZoneInfo(org.timezone)
        lead_doctor = await db.scalar(
            select(User).join(ClinicMembership, ClinicMembership.user_id == User.id).where(
                ClinicMembership.org_id == org_id,
                ClinicMembership.status == "active",
                ClinicMembership.role.in_(("doctor", "admin")),
                User.org_id == org_id,
                User.role == "doctor",
                User.is_active.is_(True),
            ).order_by(User.id)
        )
        if not lead_doctor:
            raise RuntimeError("The selected clinic needs an active doctor membership")
        doctor_id = lead_doctor.id

        appt_ids_query = select(Appointment.id).where(Appointment.org_id == org_id)
        await db.execute(
            delete(SystemAuditLog).where(
                SystemAuditLog.org_id == org_id,
                SystemAuditLog.target_id.in_(appt_ids_query),
            )
        )
        await db.execute(delete(VoiceCallTurn).where(VoiceCallTurn.org_id == org_id))
        await db.execute(delete(VisitEvent).where(VisitEvent.org_id == org_id))
        await db.execute(delete(PaymentReceipt).where(PaymentReceipt.org_id == org_id))
        await db.execute(delete(Appointment).where(Appointment.org_id == org_id))
        await db.execute(delete(CallLog).where(CallLog.org_id == org_id))
        await db.execute(delete(ScheduleOverride).where(ScheduleOverride.org_id == org_id))
        await db.execute(delete(Patient).where(Patient.org_id == org_id))

        patients_data = [
            {
                "id": uuid.uuid4(),
                "first_name": "Alex",
                "last_name": "Example",
                "phone_number": "+447700900013",
                "dob": date(1998, 1, 28),
                "gender": "Male",
                "blood_group": "O+",
                "recent_diagnosis": "Exercise-Induced Asthma",
                "medical_history": {
                    "allergies": ["Peanuts", "Dust Mites"],
                    "chronic_conditions": ["Asthma"],
                    "notes": ["Uses albuterol inhaler before intense workouts"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Maya",
                "last_name": "Example",
                "phone_number": "+447700900013",
                "dob": date(2002, 5, 14),
                "gender": "Female",
                "blood_group": "B+",
                "recent_diagnosis": "Allergic Rhinitis",
                "medical_history": {
                    "allergies": ["Penicillin"],
                    "chronic_conditions": [],
                    "notes": ["Seasonal flare-ups every monsoon and winter"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Rajesh",
                "last_name": "Sharma",
                "phone_number": "+447700900001",
                "dob": date(1974, 8, 12),
                "gender": "Male",
                "blood_group": "A+",
                "recent_diagnosis": "Essential Hypertension",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": ["Hypertension", "Type 2 Diabetes"],
                    "notes": ["Metformin 500mg BD, Telmisartan 40mg OD"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Aarav",
                "last_name": "Sharma",
                "phone_number": "+447700900001",
                "dob": date(2018, 3, 22),
                "gender": "Male",
                "blood_group": "A+",
                "recent_diagnosis": "Acute Viral Pharyngitis",
                "medical_history": {
                    "allergies": ["Amoxicillin"],
                    "chronic_conditions": [],
                    "notes": ["Child patient sharing father Rajesh phone"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Priya",
                "last_name": "Deshmukh",
                "phone_number": "+447700900002",
                "dob": date(1989, 11, 3),
                "gender": "Female",
                "blood_group": "O+",
                "recent_diagnosis": "Chronic Migraine without Aura",
                "medical_history": {
                    "allergies": ["Sulfa drugs"],
                    "chronic_conditions": ["Migraine"],
                    "notes": ["Triggers include sleep deprivation and bright screens"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Ananya",
                "last_name": "Iyer",
                "phone_number": "+447700900003",
                "dob": date(1996, 4, 18),
                "gender": "Female",
                "blood_group": "AB+",
                "recent_diagnosis": "Gastroesophageal Reflux Disease",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": ["GERD"],
                    "notes": ["Reports postprandial heartburn and sour eructation"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Rohan",
                "last_name": "Mehta",
                "phone_number": "+447700900004",
                "dob": date(1991, 7, 19),
                "gender": "Male",
                "blood_group": "B+",
                "recent_diagnosis": "Acute Lumbar Muscle Strain",
                "medical_history": {
                    "allergies": ["Ibuprofen"],
                    "chronic_conditions": [],
                    "notes": ["Gym deadlift injury, prescribed muscle relaxants"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Deepa",
                "last_name": "Nair",
                "phone_number": "+447700900005",
                "dob": date(1968, 12, 5),
                "gender": "Female",
                "blood_group": "A-",
                "recent_diagnosis": "Bilateral Knee Osteoarthritis",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": ["Osteoarthritis", "Hypothyroidism"],
                    "notes": ["Thyronorm 50mcg empty stomach morning"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Vikramaditya",
                "last_name": "Rao",
                "phone_number": "+447700900006",
                "dob": date(1982, 4, 16),
                "gender": "Male",
                "blood_group": "B-",
                "recent_diagnosis": "Hyperuricemia & Gouty Arthritis",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": ["Gout"],
                    "notes": ["Elevated serum uric acid 8.4 mg/dL"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Sneha",
                "last_name": "Kulkarni",
                "phone_number": "+447700900007",
                "dob": date(1999, 9, 9),
                "gender": "Female",
                "blood_group": "O-",
                "recent_diagnosis": "Polycystic Ovarian Syndrome",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": ["PCOS"],
                    "notes": ["Irregular menstrual cycles, lifestyle modification advised"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Arjun",
                "last_name": "Kapoor",
                "phone_number": "+447700900008",
                "dob": date(2004, 2, 14),
                "gender": "Male",
                "blood_group": "AB-",
                "recent_diagnosis": "Annual Wellness Check",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": [],
                    "notes": ["All vitals within normal parameters"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Kavita",
                "last_name": "Rao",
                "phone_number": "+447700900000",
                "dob": date(1970, 6, 30),
                "gender": "Female",
                "blood_group": "B+",
                "recent_diagnosis": "Acute Coronary Syndrome Evaluation",
                "medical_history": {
                    "allergies": ["Aspirin"],
                    "chronic_conditions": ["Ischemic Heart Disease"],
                    "notes": ["History of stent placement in 2021"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Sunil",
                "last_name": "Verma",
                "phone_number": "+447700900014",
                "dob": date(1985, 10, 20),
                "gender": "Male",
                "blood_group": "O+",
                "recent_diagnosis": "Parent/Guardian Profile",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": [],
                    "notes": ["Primary contact for pediatric emergency callback"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Amitabh",
                "last_name": "Bachchan",
                "phone_number": "+447700900009",
                "dob": date(1942, 10, 11),
                "gender": "Male",
                "blood_group": "B+",
                "recent_diagnosis": "Post-Surgical Joint Rehabilitation",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": ["Osteoarthritis"],
                    "notes": ["Routine orthopaedic follow-up scheduled via Voice AI"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Deepak",
                "last_name": "Patel",
                "phone_number": "+447700900010",
                "dob": date(1989, 1, 15),
                "gender": "Male",
                "blood_group": "A+",
                "recent_diagnosis": "Functional Dyspepsia",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": [],
                    "notes": ["Cancelled follow-up visit due to symptom resolution"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Pooja",
                "last_name": "Hegde",
                "phone_number": "+447700900011",
                "dob": date(1993, 10, 13),
                "gender": "Female",
                "blood_group": "A+",
                "recent_diagnosis": "Contact Dermatitis",
                "medical_history": {
                    "allergies": ["Nickel jewelry", "Fragrance"],
                    "chronic_conditions": [],
                    "notes": ["Prescribed topical hydrocortisone and cetirizine"],
                },
            },
            {
                "id": uuid.uuid4(),
                "first_name": "Vikram",
                "last_name": "Malhotra",
                "phone_number": "+447700900012",
                "dob": date(1978, 7, 25),
                "gender": "Male",
                "blood_group": "B+",
                "recent_diagnosis": "Cervical Spondylosis",
                "medical_history": {
                    "allergies": [],
                    "chronic_conditions": ["Cervical Spondylosis"],
                    "notes": ["Neck stiffness radiating to right shoulder"],
                },
            },
        ]

        patient_map = {}
        for p in patients_data:
            patient_obj = Patient(
                id=p["id"],
                org_id=org_id,
                phone_number=p["phone_number"],
                first_name=p["first_name"],
                last_name=p["last_name"],
                dob=p["dob"],
                gender=p["gender"],
                blood_group=p["blood_group"],
                recent_diagnosis=p["recent_diagnosis"],
                medical_history=p["medical_history"],
                created_by_type="SYSTEM_SEED",
            )
            db.add(patient_obj)
            patient_map[p["first_name"]] = patient_obj

        await db.flush()

        base_date = anchor_date
        now_dt = datetime.combine(anchor_date, time(17, 30), tzinfo=tz)

        active_emergency_1 = CallLog(
            id=uuid.uuid4(),
            org_id=org_id,
            caller_phone="+447700900000",
            caller_name="Kavita Rao",
            patient_id=patient_map["Kavita"].id,
            session_type="telephony",
            triage_status="emergency",
            intent_classification="EMERGENCY_CHEST_PAIN",
            triage_latency_ms=180,
            call_outcome="emergency",
            attended_by="Voice AI Tulsi",
            chief_complaint="Acute severe crushing chest pain radiating to left jaw, diaphoresis for 25 minutes",
            total_turns=4,
            duration_seconds=78,
            full_transcript="Caller: I have unbearable chest pain spreading into my left arm and jaw. Tulsi: Ma'am, please sit down immediately and remain calm. This sounds like an acute cardiac emergency. I am alerting clinic emergency staff right now, and you must dial 108 or proceed to the nearest emergency room immediately.",
            turns=[
                {"speaker": "user", "text": "I have unbearable chest pain spreading into my left arm and jaw."},
                {"speaker": "ai", "text": "Ma'am, please sit down immediately and remain calm. This sounds like an acute cardiac emergency. I am alerting clinic emergency staff right now, and you must dial 108 immediately."},
            ],
            sentiment_score="urgent",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=0), time(16, 45), tzinfo=tz).astimezone(UTC),
            connected_at=datetime.combine(anchor_date + timedelta(days=0), time(16, 45, 3), tzinfo=tz).astimezone(UTC),
            end_time=datetime.combine(anchor_date + timedelta(days=0), time(16, 46, 21), tzinfo=tz).astimezone(UTC),
        )
        db.add(active_emergency_1)

        active_emergency_2 = CallLog(
            id=uuid.uuid4(),
            org_id=org_id,
            caller_phone="+447700900014",
            caller_name="Sunil Verma",
            patient_id=patient_map["Sunil"].id,
            session_type="telephony",
            triage_status="emergency",
            intent_classification="PEDIATRIC_FEVER_SEIZURE",
            triage_latency_ms=195,
            call_outcome="emergency",
            attended_by="Voice AI Tulsi",
            chief_complaint="Child fever 104F with brief febrile seizure episode",
            total_turns=4,
            duration_seconds=92,
            full_transcript="Caller: My son has a 104 fever and just had a convulsion! Tulsi: Sir, keep him on his side on a flat surface and ensure his airway is clear. Do not put anything in his mouth. I am flagging this as an emergency for the doctor immediately.",
            turns=[
                {"speaker": "user", "text": "My son has a 104 fever and just had a convulsion!"},
                {"speaker": "ai", "text": "Sir, keep him on his side on a flat surface and ensure his airway is clear. Do not put anything in his mouth. I am flagging this as an emergency for the doctor immediately."},
            ],
            sentiment_score="urgent",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=0), time(15, 10), tzinfo=tz).astimezone(UTC),
            connected_at=datetime.combine(anchor_date + timedelta(days=0), time(15, 10, 2), tzinfo=tz).astimezone(UTC),
            end_time=datetime.combine(anchor_date + timedelta(days=0), time(15, 11, 34), tzinfo=tz).astimezone(UTC),
        )
        db.add(active_emergency_2)

        booking_call_id = uuid.uuid4()
        booking_call = CallLog(
            id=booking_call_id,
            org_id=org_id,
            caller_phone="+447700900009",
            caller_name="Amitabh Bachchan",
            patient_id=patient_map["Amitabh"].id,
            session_type="voice_simulator",
            triage_status="admin",
            intent_classification="APPOINTMENT_BOOKING",
            triage_latency_ms=210,
            call_outcome="appointment_booked",
            attended_by="Voice AI Tulsi",
            chief_complaint="Follow-up consultation for knee pain rehabilitation",
            total_turns=6,
            duration_seconds=115,
            full_transcript="Caller: I'd like to book an appointment with Dr. Priyanshu Bharti for knee rehabilitation. Tulsi: Certainly! Dr. Priyanshu Bharti has openings tomorrow at 10:00 AM or 11:30 AM. Caller: 10:00 AM works. Tulsi: Your appointment is booked for tomorrow at 10:00 AM.",
            turns=[
                {"speaker": "user", "text": "I'd like to book an appointment with Dr. Priyanshu Bharti for knee rehabilitation."},
                {"speaker": "ai", "text": "Certainly! Dr. Priyanshu Bharti has openings tomorrow at 10:00 AM or 11:30 AM. Would 10:00 AM suit you?"},
                {"speaker": "user", "text": "10:00 AM works."},
                {"speaker": "ai", "text": "Confirmed! Your appointment is booked for tomorrow at 10:00 AM with token T-1."},
            ],
            sentiment_score="satisfied",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=0), time(11, 20), tzinfo=tz).astimezone(UTC),
            connected_at=datetime.combine(anchor_date + timedelta(days=0), time(11, 20, 2), tzinfo=tz).astimezone(UTC),
            end_time=datetime.combine(anchor_date + timedelta(days=0), time(11, 21, 57), tzinfo=tz).astimezone(UTC),
        )
        db.add(booking_call)

        reschedule_call = CallLog(
            id=uuid.uuid4(),
            org_id=org_id,
            caller_phone="+447700900013",
            caller_name="Alex Example",
            patient_id=patient_map["Alex"].id,
            session_type="voice_simulator",
            triage_status="admin",
            intent_classification="APPOINTMENT_RESCHEDULE",
            triage_latency_ms=230,
            call_outcome="appointment_rescheduled",
            attended_by="Voice AI Tulsi",
            chief_complaint="Reschedule asthma checkup from morning to afternoon",
            total_turns=6,
            duration_seconds=104,
            full_transcript="Caller: Can I reschedule my appointment today? Tulsi: Hello Alex! I found your scheduled visit. Would you like to move it to the evening slot at 5:00 PM? Caller: Yes, 5:00 PM is perfect. Tulsi: All set! Your visit has been rescheduled to 5:00 PM.",
            turns=[
                {"speaker": "user", "text": "Can I reschedule my appointment today?"},
                {"speaker": "ai", "text": "Hello Alex! I found your visit. Would you like to move it to the evening at 5:00 PM?"},
                {"speaker": "user", "text": "Yes, 5:00 PM is perfect."},
                {"speaker": "ai", "text": "All set! Your appointment has been moved to 5:00 PM today."},
            ],
            sentiment_score="satisfied",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=0), time(14, 15), tzinfo=tz).astimezone(UTC),
            connected_at=datetime.combine(anchor_date + timedelta(days=0), time(14, 15, 2), tzinfo=tz).astimezone(UTC),
            end_time=datetime.combine(anchor_date + timedelta(days=0), time(14, 16, 46), tzinfo=tz).astimezone(UTC),
        )
        db.add(reschedule_call)

        cancel_call = CallLog(
            id=uuid.uuid4(),
            org_id=org_id,
            caller_phone="+447700900010",
            caller_name="Deepak Patel",
            patient_id=patient_map["Deepak"].id,
            session_type="voice_simulator",
            triage_status="admin",
            intent_classification="APPOINTMENT_CANCEL",
            triage_latency_ms=190,
            call_outcome="appointment_cancelled",
            attended_by="Voice AI Tulsi",
            chief_complaint="Cancel follow-up appointment due to symptom recovery",
            total_turns=4,
            duration_seconds=65,
            full_transcript="Caller: I want to cancel my follow-up appointment today as I am completely fine now. Tulsi: Glad to hear you're feeling better Deepak! I have cancelled your visit.",
            turns=[
                {"speaker": "user", "text": "I want to cancel my follow-up appointment today as I am completely fine now."},
                {"speaker": "ai", "text": "Glad to hear you are feeling better Deepak! I have cancelled your appointment."},
            ],
            sentiment_score="satisfied",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=0), time(10, 5), tzinfo=tz).astimezone(UTC),
            connected_at=datetime.combine(anchor_date + timedelta(days=0), time(10, 5, 2), tzinfo=tz).astimezone(UTC),
            end_time=datetime.combine(anchor_date + timedelta(days=0), time(10, 6, 7), tzinfo=tz).astimezone(UTC),
        )
        db.add(cancel_call)

        shared_phone_call = CallLog(
            id=uuid.uuid4(),
            org_id=org_id,
            caller_phone="+447700900013",
            caller_name="Maya Example",
            patient_id=patient_map["Maya"].id,
            session_type="telephony",
            triage_status="admin",
            intent_classification="PATIENT_DISAMBIGUATION",
            triage_latency_ms=215,
            call_outcome="inquiry",
            attended_by="Voice AI Tulsi",
            chief_complaint="Inquiry about allergy consultation for Maya under Alex shared phone",
            total_turns=5,
            duration_seconds=88,
            full_transcript="Caller: Hi, I'm Maya calling from my family number. Can you tell me Dr. Priyanshu's allergy clinic days? Tulsi: Hello Maya! Dr. Priyanshu Bharti conducts allergy reviews Monday through Saturday.",
            turns=[
                {"speaker": "user", "text": "Hi, I'm Maya calling from my family number. Can you tell me Dr. Priyanshu's allergy clinic days?"},
                {"speaker": "ai", "text": "Hello Maya! Dr. Priyanshu Bharti conducts allergy reviews Monday through Saturday during regular clinic hours."},
            ],
            sentiment_score="satisfied",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=-1), time(16, 20), tzinfo=tz).astimezone(UTC),
            connected_at=datetime.combine(anchor_date + timedelta(days=-1), time(16, 20, 3), tzinfo=tz).astimezone(UTC),
            end_time=datetime.combine(anchor_date + timedelta(days=-1), time(16, 21, 31), tzinfo=tz).astimezone(UTC),
        )
        db.add(shared_phone_call)

        inquiry_call = CallLog(
            id=uuid.uuid4(),
            org_id=org_id,
            caller_phone="+447700900011",
            caller_name="Pooja Hegde",
            patient_id=patient_map["Pooja"].id,
            session_type="telephony",
            triage_status="admin",
            intent_classification="CLINIC_HOURS_INQUIRY",
            triage_latency_ms=160,
            call_outcome="inquiry",
            attended_by="Voice AI Tulsi",
            chief_complaint="Inquiry regarding evening consultation hours and consultation fee",
            total_turns=4,
            duration_seconds=58,
            full_transcript="Caller: What are your clinic timings and fee? Tulsi: Our clinic is open Monday through Saturday 9 AM to 1 PM and 5 PM to 8 PM. General consultation fee is 500 rupees.",
            turns=[
                {"speaker": "user", "text": "What are your clinic timings and fee?"},
                {"speaker": "ai", "text": "Our clinic is open Monday through Saturday from 9:00 AM to 1:00 PM and 5:00 PM to 8:00 PM. General consultation is 500 rupees."},
            ],
            sentiment_score="satisfied",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=-2), time(12, 10), tzinfo=tz).astimezone(UTC),
            connected_at=datetime.combine(anchor_date + timedelta(days=-2), time(12, 10, 2), tzinfo=tz).astimezone(UTC),
            end_time=datetime.combine(anchor_date + timedelta(days=-2), time(12, 11, 0), tzinfo=tz).astimezone(UTC),
        )
        db.add(inquiry_call)

        human_transfer_call = CallLog(
            id=uuid.uuid4(),
            org_id=org_id,
            caller_phone="+447700900012",
            caller_name="Vikram Malhotra",
            patient_id=patient_map["Vikram"].id,
            session_type="telephony",
            triage_status="human_takeover",
            intent_classification="STAFF_ESCALATION",
            triage_latency_ms=250,
            call_outcome="transferred_to_staff",
            attended_by="Front Desk Receptionist",
            chief_complaint="Complex insurance pre-authorization inquiry transferred to front desk",
            total_turns=6,
            duration_seconds=145,
            full_transcript="Caller: I need help verifying cashless TPA insurance for my MRI scan. Tulsi: Connecting you to our front desk billing officer right away.",
            turns=[
                {"speaker": "user", "text": "I need help verifying cashless TPA insurance for my MRI scan."},
                {"speaker": "ai", "text": "Connecting you to our front desk billing officer right away."},
            ],
            sentiment_score="satisfied",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=-3), time(11, 40), tzinfo=tz).astimezone(UTC),
            connected_at=datetime.combine(anchor_date + timedelta(days=-3), time(11, 40, 2), tzinfo=tz).astimezone(UTC),
            end_time=datetime.combine(anchor_date + timedelta(days=-3), time(11, 42, 27), tzinfo=tz).astimezone(UTC),
        )
        db.add(human_transfer_call)

        missed_call_1 = CallLog(
            id=uuid.uuid4(),
            org_id=org_id,
            caller_phone="+447700900015",
            caller_name="Anonymous Caller",
            patient_id=None,
            session_type="telephony",
            triage_status="missed",
            intent_classification="CALLER_ABANDONED",
            triage_latency_ms=0,
            call_outcome="caller_abandoned",
            attended_by="Unattended / Missed",
            chief_complaint="Caller disconnected before IVR connection",
            total_turns=0,
            duration_seconds=0,
            full_transcript="",
            turns=[],
            sentiment_score="neutral",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=0), time(13, 5), tzinfo=tz).astimezone(UTC),
            connected_at=None,
            end_time=datetime.combine(anchor_date + timedelta(days=0), time(13, 5, 8), tzinfo=tz).astimezone(UTC),
        )
        db.add(missed_call_1)

        missed_call_2 = CallLog(
            id=uuid.uuid4(),
            org_id=org_id,
            caller_phone="+447700900016",
            caller_name="Anonymous Caller",
            patient_id=None,
            session_type="telephony",
            triage_status="missed",
            intent_classification="NO_ANSWER",
            triage_latency_ms=0,
            call_outcome="no_answer",
            attended_by="Unattended / Missed",
            chief_complaint="Call ended while ringing",
            total_turns=0,
            duration_seconds=0,
            full_transcript="",
            turns=[],
            sentiment_score="neutral",
            recording_status="disabled",
            call_status="completed",
            start_time=datetime.combine(anchor_date + timedelta(days=-4), time(14, 30), tzinfo=tz).astimezone(UTC),
            connected_at=None,
            end_time=datetime.combine(anchor_date + timedelta(days=-4), time(14, 30, 15), tzinfo=tz).astimezone(UTC),
        )
        db.add(missed_call_2)

        for day_offset in range(1, 14):
            past_d = base_date - timedelta(days=day_offset)
            sim_call = CallLog(
                id=uuid.uuid4(),
                org_id=org_id,
                caller_phone=f"+447700900{day_offset:03d}",
                caller_name=f"Patient Contact {day_offset}",
                patient_id=None,
                session_type="telephony",
                triage_status="admin",
                intent_classification="INQUIRY",
                triage_latency_ms=180,
                call_outcome="inquiry",
                attended_by="Voice AI Tulsi",
                chief_complaint="General consultation availability inquiry",
                total_turns=2,
                duration_seconds=45,
                full_transcript="Inquiry answered by Tulsi.",
                turns=[],
                sentiment_score="satisfied",
                recording_status="disabled",
                call_status="completed",
                start_time=datetime(past_d.year, past_d.month, past_d.day, 10, 15, tzinfo=tz).astimezone(UTC),
                connected_at=datetime(past_d.year, past_d.month, past_d.day, 10, 15, 2, tzinfo=tz).astimezone(UTC),
                end_time=datetime(past_d.year, past_d.month, past_d.day, 10, 15, 47, tzinfo=tz).astimezone(UTC),
            )
            db.add(sim_call)

        await db.flush()

        appts_to_create = []
        payments_to_create = []
        linked_call_appts = []

        total_settled_amount = Decimal("0.00")

        today_appts = [
            {
                "patient": patient_map["Rajesh"],
                "start": datetime.combine(anchor_date + timedelta(days=0), time(9, 0), tzinfo=tz),
                "end": datetime.combine(anchor_date + timedelta(days=0), time(9, 30), tzinfo=tz),
                "status": "completed",
                "queue_state": "served",
                "encounter_state": "completed",
                "complaint": "Quarterly hypertension and blood sugar review",
                "notes": "BP 132/84 mmHg. Fasting blood sugar 128 mg/dL. Continue Telmisartan 40mg OD and Metformin 500mg BD. Low sodium diet.",
                "fee": 500.0,
                "paid": True,
                "method": "UPI",
                "source": "walk_in",
                "token": "T-1",
            },
            {
                "patient": patient_map["Priya"],
                "start": datetime.combine(anchor_date + timedelta(days=0), time(9, 30), tzinfo=tz),
                "end": datetime.combine(anchor_date + timedelta(days=0), time(10, 0), tzinfo=tz),
                "status": "completed",
                "queue_state": "served",
                "encounter_state": "completed",
                "complaint": "Severe unilateral throbbing headache with photophobia",
                "notes": "Acute migraine attack triggered by irregular sleep. Prescribed Rizatriptan 10mg stat, Naproxen 500mg SOS. Advised sleep hygiene.",
                "fee": 750.0,
                "bill_items": [
                    {"name": "Doctor Consultation", "amount": 500.0, "quantity": 1},
                    {"name": "Acute Migraine Injection (Ketorolac)", "amount": 250.0, "quantity": 1},
                ],
                "paid": True,
                "method": "UPI",
                "source": "ai_voice",
                "token": "T-2",
            },
            {
                "patient": patient_map["Ananya"],
                "start": datetime.combine(anchor_date + timedelta(days=0), time(10, 30), tzinfo=tz),
                "end": datetime.combine(anchor_date + timedelta(days=0), time(11, 0), tzinfo=tz),
                "status": "completed",
                "queue_state": "served",
                "encounter_state": "completed",
                "complaint": "Persistent acid reflux and retrosternal burning",
                "notes": "Epigastric tenderness on palpation. Prescribed Pantoprazole 40mg before breakfast for 4 weeks. Avoid caffeinated beverages.",
                "fee": 500.0,
                "paid": True,
                "method": "Cash",
                "source": "walk_in",
                "token": "T-3",
            },
            {
                "patient": patient_map["Rohan"],
                "start": datetime.combine(anchor_date + timedelta(days=0), time(11, 30), tzinfo=tz),
                "end": datetime.combine(anchor_date + timedelta(days=0), time(12, 0), tzinfo=tz),
                "status": "no_show",
                "queue_state": "not_checked_in",
                "encounter_state": "not_started",
                "complaint": "Lower back pain after heavy weightlifting",
                "notes": "",
                "fee": 500.0,
                "paid": False,
                "method": None,
                "source": "ai_voice",
                "token": "T-4",
            },
            {
                "patient": patient_map["Deepak"],
                "start": datetime.combine(anchor_date + timedelta(days=0), time(12, 0), tzinfo=tz),
                "end": datetime.combine(anchor_date + timedelta(days=0), time(12, 30), tzinfo=tz),
                "status": "cancelled",
                "queue_state": "not_checked_in",
                "encounter_state": "not_started",
                "complaint": "Follow-up for indigestion",
                "notes": "",
                "cancellation_reason": "Patient called voice assistant to cancel after feeling completely recovered",
                "fee": 500.0,
                "paid": False,
                "method": None,
                "source": "ai_voice",
                "token": "T-5",
            },
            {
                "patient": patient_map["Alex"],
                "start": datetime.combine(anchor_date + timedelta(days=0), time(17, 0), tzinfo=tz),
                "end": datetime.combine(anchor_date + timedelta(days=0), time(17, 30), tzinfo=tz),
                "status": "in_progress",
                "queue_state": "called",
                "encounter_state": "in_progress",
                "complaint": "Exercise-induced wheezing and peak flow monitoring check",
                "notes": "Currently undergoing spirometry test in consult room. Chest auscultation shows mild expiratory wheeze in bilateral lower lobes.",
                "fee": 500.0,
                "paid": False,
                "method": None,
                "source": "ai_voice",
                "token": "T-6",
            },
            {
                "patient": patient_map["Deepa"],
                "start": datetime.combine(anchor_date + timedelta(days=0), time(17, 30), tzinfo=tz),
                "end": datetime.combine(anchor_date + timedelta(days=0), time(18, 0), tzinfo=tz),
                "status": "arrived",
                "queue_state": "waiting",
                "encounter_state": "not_started",
                "complaint": "Knee joint stiffness and pain ascending stairs",
                "notes": "",
                "fee": 500.0,
                "paid": False,
                "method": None,
                "source": "walk_in",
                "token": "T-7",
            },
            {
                "patient": patient_map["Vikramaditya"],
                "start": datetime.combine(anchor_date + timedelta(days=0), time(17, 30), tzinfo=tz),
                "end": datetime.combine(anchor_date + timedelta(days=0), time(18, 0), tzinfo=tz),
                "status": "arrived",
                "queue_state": "waiting",
                "encounter_state": "not_started",
                "complaint": "Acute redness and swelling in right big toe",
                "notes": "",
                "fee": 500.0,
                "paid": False,
                "method": None,
                "source": "ai_voice",
                "token": "T-8",
            },
            {
                "patient": patient_map["Sneha"],
                "start": datetime.combine(anchor_date + timedelta(days=0), time(18, 30), tzinfo=tz),
                "end": datetime.combine(anchor_date + timedelta(days=0), time(19, 0), tzinfo=tz),
                "status": "scheduled",
                "queue_state": "not_checked_in",
                "encounter_state": "not_started",
                "complaint": "PCOS metabolic panel and ultrasound review",
                "notes": "",
                "fee": 500.0,
                "paid": False,
                "method": None,
                "source": "ai_voice",
                "token": "T-9",
            },
        ]

        for item in today_appts:
            p = item["patient"]
            start_utc = item["start"].astimezone(UTC)
            end_utc = item["end"].astimezone(UTC)
            appt_id = uuid.uuid4()
            meta = {
                "patient_name": f"{p.first_name} {p.last_name}",
                "caller_phone": p.phone_number,
                "fee": item["fee"],
                "payment_status": "paid" if item["paid"] else "pending",
                "bill_items": item.get("bill_items", [{"name": "Doctor Consultation", "amount": item["fee"], "quantity": 1}]),
            }
            if item["paid"]:
                meta["collected_at"] = item["start"].isoformat()
                meta["payment_method"] = item["method"]

            appt_obj = Appointment(
                id=appt_id,
                org_id=org_id,
                patient_id=p.id,
                doctor_id=doctor_id,
                start_time=start_utc,
                end_time=end_utc,
                appointment_timezone="Asia/Calcutta",
                status=item["status"],
                queue_state=item["queue_state"],
                encounter_state=item["encounter_state"],
                chief_complaint=item["complaint"],
                doctor_notes=item["notes"],
                source=item["source"],
                cancellation_reason=item.get("cancellation_reason"),
                display_token=item["token"],
                token_number=int(item["token"].replace("T-", "")),
                booking_metadata=meta,
                consultation_started_at=start_utc if item["status"] in ("in_progress", "completed") else None,
                consultation_ended_at=end_utc if item["status"] == "completed" else None,
                actual_duration_seconds=1800 if item["status"] == "completed" else None,
            )
            db.add(appt_obj)

            if item["paid"]:
                receipt_amount = Decimal(str(item["fee"]))
                receipt = PaymentReceipt(
                    id=uuid.uuid4(),
                    org_id=org_id,
                    visit_id=appt_id,
                    amount=receipt_amount,
                    status="paid",
                    method=item["method"],
                    reference=f"TXN-TODAY-{appt_id.hex[:6].upper()}",
                    received_by=doctor_id,
                    received_at=start_utc,
                )
                db.add(receipt)
                total_settled_amount += receipt_amount

        future_scheduled = [
            {
                "patient": patient_map["Amitabh"],
                "date_offset": 1,
                "hour": 10,
                "minute": 0,
                "complaint": "Orthopaedic knee joint post-op physiotherapy assessment",
                "call_id": booking_call_id,
                "token": "T-1",
            },
            {
                "patient": patient_map["Maya"],
                "date_offset": 1,
                "hour": 11,
                "minute": 30,
                "complaint": "Seasonal allergic rhinitis checkup and allergy testing",
                "call_id": None,
                "token": "T-2",
            },
            {
                "patient": patient_map["Aarav"],
                "date_offset": 2,
                "hour": 9,
                "minute": 30,
                "complaint": "Pediatric throat review and tonsil examination",
                "call_id": None,
                "token": "T-1",
            },
            {
                "patient": patient_map["Arjun"],
                "date_offset": 3,
                "hour": 10,
                "minute": 0,
                "complaint": "Annual preventive sports fitness health checkup",
                "call_id": None,
                "token": "T-1",
            },
            {
                "patient": patient_map["Pooja"],
                "date_offset": 4,
                "hour": 17,
                "minute": 0,
                "complaint": "Follow-up evaluation for skin contact dermatitis",
                "call_id": None,
                "token": "T-1",
            },
            {
                "patient": patient_map["Vikram"],
                "date_offset": 5,
                "hour": 18,
                "minute": 0,
                "complaint": "Physiotherapy neck exercise review for cervical spondylosis",
                "call_id": None,
                "token": "T-1",
            },
            {
                "patient": patient_map["Rajesh"],
                "date_offset": 6,
                "hour": 9,
                "minute": 0,
                "complaint": "Follow-up blood glucose fasting test result review",
                "call_id": None,
                "token": "T-1",
            },
        ]

        for fut in future_scheduled:
            p = fut["patient"]
            fut_date = base_date + timedelta(days=fut["date_offset"])
            start_local = datetime(fut_date.year, fut_date.month, fut_date.day, fut["hour"], fut["minute"], tzinfo=tz)
            end_local = start_local + timedelta(minutes=30)
            appt_id = uuid.uuid4()
            fut_appt = Appointment(
                id=appt_id,
                org_id=org_id,
                patient_id=p.id,
                doctor_id=doctor_id,
                start_time=start_local.astimezone(UTC),
                end_time=end_local.astimezone(UTC),
                appointment_timezone="Asia/Calcutta",
                status="scheduled",
                queue_state="not_checked_in",
                encounter_state="not_started",
                chief_complaint=fut["complaint"],
                source="ai_voice" if fut["call_id"] else "walk_in",
                call_session_id=None,
                display_token=fut["token"],
                token_number=int(fut["token"].replace("T-", "")),
                booking_metadata={
                    "patient_name": f"{p.first_name} {p.last_name}",
                    "caller_phone": p.phone_number,
                    "fee": 500.0,
                    "payment_status": "pending",
                    "bill_items": [{"name": "Doctor Consultation", "amount": 500.0, "quantity": 1}],
                },
            )
            db.add(fut_appt)
            if fut["call_id"]:
                linked_call_appts.append((appt_id, fut["call_id"]))

        past_patients_pool = [
            patient_map["Alex"],
            patient_map["Maya"],
            patient_map["Rajesh"],
            patient_map["Aarav"],
            patient_map["Priya"],
            patient_map["Ananya"],
            patient_map["Rohan"],
            patient_map["Deepa"],
            patient_map["Vikramaditya"],
            patient_map["Sneha"],
            patient_map["Arjun"],
            patient_map["Deepak"],
            patient_map["Pooja"],
            patient_map["Vikram"],
        ]

        past_complaints_pool = [
            ("Acute Bronchitis with productive cough", "Chest clear bilaterally, prescribed Azithromycin 500mg OD for 3 days and ambroxol syrup."),
            ("Type 2 Diabetes Routine Fasting Check", "Fasting blood sugar 114 mg/dL. HbA1c 6.8%. Continue current dosage."),
            ("Seasonal Allergic Conjunctivitis", "Prescribed Olopatadine eye drops BD and oral levocetirizine."),
            ("Acute Lumbar Strain following workout", "Advised hot fomentation, lumbar support belt, and Paracetamol 650mg TDS."),
            ("Migraine Prophylaxis Review", "Attacks reduced from 4 to 1 per month with Propranolol 40mg OD. Continue therapy."),
            ("Gastroenteritis with mild dehydration", "ORS hydration therapy, probiotic sachet twice daily, light bland diet for 48 hours."),
            ("Routine Annual Preventive Checkup", "Normal BMI, BP 120/80 mmHg, lipid profile within normal limits."),
            ("Knee Osteoarthritis follow-up", "Advised quadriceps strengthening exercises, glucosamine sulphate supplement."),
            ("Cervical Spondylosis evaluation", "Cervical collar recommended during computer desk work. Physiotherapy stretches taught."),
            ("Viral Upper Respiratory Tract Infection", "Steam inhalation, saline nasal spray, Paracetamol for body ache."),
        ]

        for day_back in range(1, 14):
            hist_date = base_date - timedelta(days=day_back)
            if hist_date.weekday() == 6 and day_back != 4:
                continue

            num_appts = 4 if hist_date.weekday() in (0, 1, 4) else 3
            for appt_idx in range(num_appts):
                p_selected = past_patients_pool[(day_back * 3 + appt_idx) % len(past_patients_pool)]
                complaint_data = past_complaints_pool[(day_back * 2 + appt_idx) % len(past_complaints_pool)]
                hour = 9 + (appt_idx * 1) if appt_idx < 2 else 17 + (appt_idx - 2)
                minute = 0 if appt_idx % 2 == 0 else 30
                start_hist = datetime(hist_date.year, hist_date.month, hist_date.day, hour, minute, tzinfo=tz)
                end_hist = start_hist + timedelta(minutes=30)
                start_utc = start_hist.astimezone(UTC)
                end_utc = end_hist.astimezone(UTC)

                status_val = "completed"
                if appt_idx == 3 and day_back % 3 == 0:
                    status_val = "no_show"
                elif appt_idx == 2 and day_back % 5 == 0:
                    status_val = "cancelled"

                fee_val = 500.0 if appt_idx % 2 == 0 else 750.0
                bill_items = [{"name": "Doctor Consultation", "amount": 500.0, "quantity": 1}]
                if fee_val > 500:
                    bill_items.append({"name": "Laboratory Panel / ECG", "amount": 250.0, "quantity": 1})

                is_paid = status_val == "completed"
                pay_method = "UPI" if (day_back + appt_idx) % 2 == 0 else "Cash"

                meta = {
                    "patient_name": f"{p_selected.first_name} {p_selected.last_name}",
                    "caller_phone": p_selected.phone_number,
                    "fee": fee_val,
                    "payment_status": "paid" if is_paid else "pending",
                    "bill_items": bill_items,
                }
                if is_paid:
                    meta["collected_at"] = start_hist.isoformat()
                    meta["payment_method"] = pay_method

                appt_id = uuid.uuid4()
                appt_obj = Appointment(
                    id=appt_id,
                    org_id=org_id,
                    patient_id=p_selected.id,
                    doctor_id=doctor_id,
                    start_time=start_utc,
                    end_time=end_utc,
                    appointment_timezone="Asia/Calcutta",
                    status=status_val,
                    queue_state="served" if status_val == "completed" else "not_checked_in",
                    encounter_state="completed" if status_val == "completed" else "not_started",
                    chief_complaint=complaint_data[0],
                    doctor_notes=complaint_data[1] if status_val == "completed" else "",
                    cancellation_reason="Work schedule conflict" if status_val == "cancelled" else None,
                    source="ai_voice" if (day_back + appt_idx) % 3 != 0 else "walk_in",
                    display_token=f"T-{appt_idx + 1}",
                    token_number=appt_idx + 1,
                    booking_metadata=meta,
                )
                db.add(appt_obj)

                if is_paid:
                    rec_amount = Decimal(str(fee_val))
                    receipt = PaymentReceipt(
                        id=uuid.uuid4(),
                        org_id=org_id,
                        visit_id=appt_id,
                        amount=rec_amount,
                        status="paid",
                        method=pay_method,
                        reference=f"TXN-{hist_date.strftime('%Y%m%d')}-{appt_idx + 1}",
                        received_by=doctor_id,
                        received_at=start_utc,
                    )
                    db.add(receipt)
                    total_settled_amount += rec_amount

        await db.flush()

        for a_id, c_id in linked_call_appts:
            await db.execute(
                update(Appointment).where(Appointment.id == a_id).values(call_session_id=c_id)
            )

        override_past = ScheduleOverride(
            id=uuid.uuid4(),
            org_id=org_id,
            doctor_id=doctor_id,
            title="Special Sunday OPD",
            override_type="special_hours",
            is_available=True,
            start_date=anchor_date - timedelta(days=4),
            end_date=anchor_date - timedelta(days=4),
            custom_hours=[{"start": "10:00", "end": "14:00"}],
            reason="Dedicated morning camp for chronic diabetes and hypertension screening",
            emergency_phone="+447700900013",
        )
        db.add(override_past)

        override_extended = ScheduleOverride(
            id=uuid.uuid4(),
            org_id=org_id,
            doctor_id=doctor_id,
            title="Evening Fever & Flu Extended Clinic",
            override_type="special_hours",
            is_available=True,
            start_date=anchor_date + timedelta(days=3),
            end_date=anchor_date + timedelta(days=3),
            custom_hours=[{"start": "17:00", "end": "22:00"}],
            reason="Extended operating hours for seasonal respiratory and dengue surge",
            emergency_phone="+447700900013",
        )
        db.add(override_extended)

        override_vacation = ScheduleOverride(
            id=uuid.uuid4(),
            org_id=org_id,
            doctor_id=doctor_id,
            title="Demo holiday closure",
            override_type="vacation",
            is_available=False,
            start_date=anchor_date + timedelta(days=9),
            end_date=anchor_date + timedelta(days=11),
            custom_hours=None,
            reason="Fictional holiday schedule for demonstration",
            emergency_phone="+447700900000",
        )
        db.add(override_vacation)

        if doctor_id:
            membership = await db.scalar(
                select(ClinicMembership).where(
                    ClinicMembership.org_id == org_id,
                    ClinicMembership.user_id == doctor_id,
                )
            )
            if membership:
                membership.total_revenue_collected = total_settled_amount

        await db.commit()
        print("SEED_COMPLETED_SUCCESSFULLY")
        print(f"Total Settled Revenue Seeded: Rs. {total_settled_amount}")

def main():
    parser = argparse.ArgumentParser(description="Replace a disposable clinic's activity with fictional demo records.")
    parser.add_argument("--org-id", type=uuid.UUID, required=True)
    parser.add_argument("--confirm-org-id", type=uuid.UUID, required=True)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    if settings.ENVIRONMENT.lower() not in {"development", "test", "staging"}:
        parser.error("Demo seeding is allowed only in development, test, or staging")
    if args.confirm_org_id != args.org_id:
        parser.error("--confirm-org-id must match --org-id; this replaces clinic activity")

    async def run():
        try:
            await run_seed(args.org_id, args.date)
        finally:
            await engine.dispose()
    asyncio.run(run())


if __name__ == "__main__":
    main()

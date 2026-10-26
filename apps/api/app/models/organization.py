import uuid
from typing import Any
from sqlalchemy import Column, String, DateTime, Index, Integer, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm.attributes import flag_modified
from app.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        Index(
            "idx_organizations_phone_unique",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    city = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    voice_seconds_used = Column(Integer, nullable=False, default=0)
    # Provisioned routing destination; never writable through clinic settings.
    inbound_voice_number = Column(String, nullable=True, unique=True)
    timezone = Column(String, nullable=True)
    country = Column(String, nullable=True)
    country_code = Column(String, nullable=True)
    currency_code = Column(String, nullable=True)
    currency_symbol = Column(String, nullable=True)
    booking_settings = Column(JSONB, nullable=True, default=dict)
    voice_ai_settings = Column(JSONB, nullable=True, default=dict)
    slug = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def subscription_tier(self) -> str:
        return "FREE"

    @subscription_tier.setter
    def subscription_tier(self, value: Any):
        pass

    @property
    def subscription_status(self) -> str:
        return "ACTIVE"

    @subscription_status.setter
    def subscription_status(self, value: Any):
        pass

    @property
    def consultation_fee(self) -> int | None:
        return (self.booking_settings or {}).get("consultation_fee")

    @consultation_fee.setter
    def consultation_fee(self, value: int):
        settings = dict(self.booking_settings or {})
        settings["consultation_fee"] = value
        self.booking_settings = settings
        flag_modified(self, "booking_settings")

    @property
    def visit_charge_types(self):
        return (self.booking_settings or {}).get("visit_charge_types", [])

    @property
    def billing_catalog(self):
        return (self.booking_settings or {}).get("billing_catalog", [])

    @property
    def default_slot_duration_minutes(self) -> int | None:
        return (self.booking_settings or {}).get("default_slot_duration_minutes")

    @default_slot_duration_minutes.setter
    def default_slot_duration_minutes(self, value: int):
        settings = dict(self.booking_settings or {})
        settings["default_slot_duration_minutes"] = value
        self.booking_settings = settings
        flag_modified(self, "booking_settings")

    @property
    def slot_buffer_minutes(self) -> int | None:
        return (self.booking_settings or {}).get("slot_buffer_minutes")

    @slot_buffer_minutes.setter
    def slot_buffer_minutes(self, value: int):
        settings = dict(self.booking_settings or {})
        settings["slot_buffer_minutes"] = value
        self.booking_settings = settings
        flag_modified(self, "booking_settings")

    @property
    def appointment_priority_window_minutes(self) -> int:
        return (self.booking_settings or {}).get("appointment_priority_window_minutes", 15)

    @appointment_priority_window_minutes.setter
    def appointment_priority_window_minutes(self, value: int):
        settings = dict(self.booking_settings or {})
        settings["appointment_priority_window_minutes"] = value
        self.booking_settings = settings
        flag_modified(self, "booking_settings")

    @property
    def max_daily_patients(self) -> int | None:
        return (self.booking_settings or {}).get("max_daily_patients")

    @max_daily_patients.setter
    def max_daily_patients(self, value: int):
        settings = dict(self.booking_settings or {})
        settings["max_daily_patients"] = value
        self.booking_settings = settings
        flag_modified(self, "booking_settings")

    @property
    def authorized_staff(self) -> list[dict[str, Any]]:
        return list((self.booking_settings or {}).get("authorized_staff", []))

    @authorized_staff.setter
    def authorized_staff(self, value: list[dict[str, Any]]):
        settings = dict(self.booking_settings or {})
        settings["authorized_staff"] = value
        self.booking_settings = settings
        flag_modified(self, "booking_settings")

    @property
    def weekly_schedule(self) -> dict[str, Any]:
        return (self.booking_settings or {}).get("weekly_schedule", {})

    @weekly_schedule.setter
    def weekly_schedule(self, value: dict[str, Any]):
        settings = dict(self.booking_settings or {})
        settings["weekly_schedule"] = value
        self.booking_settings = settings
        flag_modified(self, "booking_settings")

    @property
    def clinic_specialty(self) -> str | None:
        return (self.voice_ai_settings or {}).get("clinic_specialty")

    @clinic_specialty.setter
    def clinic_specialty(self, value: str):
        settings = dict(self.voice_ai_settings or {})
        settings["clinic_specialty"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def lead_doctor_name(self) -> str | None:
        return (self.voice_ai_settings or {}).get("lead_doctor_name")

    @lead_doctor_name.setter
    def lead_doctor_name(self, value: str | None):
        settings = dict(self.voice_ai_settings or {})
        settings["lead_doctor_name"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def emergency_deflection_phone(self) -> str | None:
        return (self.voice_ai_settings or {}).get("emergency_deflection_phone")

    @emergency_deflection_phone.setter
    def emergency_deflection_phone(self, value: str):
        settings = dict(self.voice_ai_settings or {})
        settings["emergency_deflection_phone"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def ai_greeting_prompt(self) -> str | None:
        return (self.voice_ai_settings or {}).get("ai_greeting_prompt")

    @ai_greeting_prompt.setter
    def ai_greeting_prompt(self, value: str):
        settings = dict(self.voice_ai_settings or {})
        settings["ai_greeting_prompt"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def ai_voice_name(self) -> str:
        return (self.voice_ai_settings or {}).get("ai_voice_name", "priya")

    @ai_voice_name.setter
    def ai_voice_name(self, value: str):
        settings = dict(self.voice_ai_settings or {})
        settings["ai_voice_name"] = value
        settings["voice_id"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def voice_id(self) -> str:
        return (self.voice_ai_settings or {}).get("voice_id") or self.ai_voice_name

    @voice_id.setter
    def voice_id(self, value: str):
        settings = dict(self.voice_ai_settings or {})
        settings["voice_id"] = value
        settings["ai_voice_name"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def ai_language_mode(self) -> str:
        return (self.voice_ai_settings or {}).get("ai_language_mode", "en_hi_bilingual")

    @ai_language_mode.setter
    def ai_language_mode(self, value: str):
        settings = dict(self.voice_ai_settings or {})
        settings["ai_language_mode"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def ai_voice_role(self) -> str:
        return (self.voice_ai_settings or {}).get("ai_voice_role", "receptionist")

    @ai_voice_role.setter
    def ai_voice_role(self, value: str):
        settings = dict(self.voice_ai_settings or {})
        settings["ai_voice_role"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def custom_greeting(self) -> str | None:
        return (self.voice_ai_settings or {}).get("custom_greeting")

    @custom_greeting.setter
    def custom_greeting(self, value: str | None):
        settings = dict(self.voice_ai_settings or {})
        settings["custom_greeting"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def closure_notice(self) -> str | None:
        return (self.voice_ai_settings or {}).get("closure_notice")

    @closure_notice.setter
    def closure_notice(self, value: str | None):
        settings = dict(self.voice_ai_settings or {})
        settings["closure_notice"] = value
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

    @property
    def hotline(self) -> str | None:
        return (self.voice_ai_settings or {}).get("hotline") or self.phone

    @hotline.setter
    def hotline(self, value: str | None):
        settings = dict(self.voice_ai_settings or {})
        if value:
            settings["hotline"] = str(value).strip()
        else:
            settings.pop("hotline", None)
        self.voice_ai_settings = settings
        flag_modified(self, "voice_ai_settings")

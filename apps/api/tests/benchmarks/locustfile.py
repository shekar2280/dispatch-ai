import json
import random
import uuid
from datetime import date
from locust import HttpUser, between, task


class ClinicPatientUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.org_id = str(uuid.uuid4())
        self.test_phone = f"+9198765{random.randint(10000, 99999)}"

    @task(3)
    def test_health_check(self):
        self.client.get("/health", name="/health")

    @task(2)
    def test_clinic_public_schedule(self):
        self.client.get(
            f"/api/v1/clinic/schedule?org_id={self.org_id}",
            name="/api/v1/clinic/schedule"
        )

    @task(1)
    def test_appointment_booking_admission(self):
        payload = {
            "patient_name": f"LoadTest User {random.randint(1, 1000)}",
            "patient_phone": self.test_phone,
            "appointment_date": str(date.today()),
            "chief_complaint": "Load testing throughput evaluation",
            "fee": 500.0,
            "is_walkin": True
        }
        headers = {
            "Content-Type": "application/json",
            "x-org-id": self.org_id
        }
        self.client.post(
            "/api/v1/appointments/walkin",
            json=payload,
            headers=headers,
            name="/api/v1/appointments/walkin"
        )

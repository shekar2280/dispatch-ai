from typing import List
from fastapi import Request, HTTPException
from twilio.request_validator import RequestValidator
from app.core.config import settings


async def validate_twilio_request(request: Request) -> bool:
    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing X-Twilio-Signature header")

    auth_token = settings.TWILIO_AUTH_TOKEN
    if not auth_token:
        raise HTTPException(status_code=500, detail="Twilio authentication token not configured")

    validator = RequestValidator(auth_token)
    form = await request.form()
    form_params = {k: str(v) for k, v in form.items()}

    path = request.url.path
    query = request.url.query
    query_suffix = f"?{query}" if query else ""

    candidate_urls: List[str] = []

    webhook_base = getattr(settings, "TWILIO_WEBHOOK_URL_BASE", None)
    if webhook_base:
        candidate_urls.append(f"{webhook_base.rstrip('/')}{path}{query_suffix}")

    if settings.NGROK_DOMAIN:
        clean_domain = settings.NGROK_DOMAIN.strip().replace("https://", "").replace("http://", "").rstrip("/")
        candidate_urls.append(f"https://{clean_domain}{path}{query_suffix}")

    candidate_urls.append(str(request.url))

    forwarded_host = request.headers.get("x-forwarded-host")
    forwarded_proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    if forwarded_host:
        trusted_hosts = {request.url.netloc, request.headers.get("host")}
        if settings.NGROK_DOMAIN:
            trusted_hosts.add(settings.NGROK_DOMAIN.strip().replace("https://", "").replace("http://", "").rstrip("/"))
        if forwarded_host in trusted_hosts:
            candidate_urls.append(f"{forwarded_proto}://{forwarded_host}{path}{query_suffix}")

    for candidate in candidate_urls:
        if validator.validate(candidate, form_params, signature):
            return True

    raise HTTPException(status_code=403, detail="Invalid Twilio signature")

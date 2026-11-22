import os
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

PROVIDER_BASE_URL = "https://solocatalog.com/api/v1"
API_KEY = os.getenv("SOLOCATALOG_API_KEY", "").strip()
TIMEOUT_SECONDS = float(os.getenv("CATALOG_TIMEOUT_SECONDS", "25"))

app = FastAPI(
    title="AI Manager Catalog Adapter",
    version="0.1.0",
    description="Server-side adapter for SoloCatalog. Provider credentials never belong in the browser.",
)

allowed_origins = [
    item.strip()
    for item in os.getenv("CORS_ORIGINS", "https://a0934600088-glitch.github.io,http://localhost:3000,http://127.0.0.1:3000").split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


class DecodeRequest(BaseModel):
    vin: str = Field(min_length=5, max_length=40)
    lang: Literal["en", "az", "ru"] = "en"


class LookupRequest(BaseModel):
    mode: Literal["models", "diagrams", "diagram"] | None = None
    vin: str | None = Field(default=None, min_length=5, max_length=40)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    diagram: str | None = Field(default=None, max_length=200)
    q: str | None = Field(default=None, max_length=80)
    lang: Literal["en", "az", "ru"] = "en"


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "provider": "solocatalog",
        "provider_key_configured": bool(API_KEY),
        "note": "This endpoint checks adapter configuration, not provider availability.",
    }


async def provider_request(method: str, path: str, *, json_body: dict | None = None):
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Catalog provider is not configured. Set SOLOCATALOG_API_KEY on the server.",
        )

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.request(
                method,
                f"{PROVIDER_BASE_URL}{path}",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=json_body,
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Catalog provider timed out.")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach catalog provider.")

    if response.status_code >= 400:
        # Do not return upstream bodies: they may contain provider diagnostics.
        status = response.status_code if response.status_code in (400, 401, 402, 404, 429) else 502
        raise HTTPException(
            status_code=status,
            detail=f"Catalog provider returned HTTP {response.status_code}.",
            headers={"Retry-After": response.headers.get("Retry-After", "")}
            if response.headers.get("Retry-After")
            else None,
        )

    try:
        return response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Catalog provider returned a non-JSON response.")


@app.post("/api/catalog/v1/vehicles/decode")
async def decode_vehicle(payload: DecodeRequest):
    return await provider_request(
        "POST",
        "/vin/decode",
        json_body={"vin": payload.vin.strip().upper(), "lang": payload.lang},
    )


@app.post("/api/catalog/v1/lookup")
async def catalogue_lookup(payload: LookupRequest):
    body = payload.model_dump(exclude_none=True)
    mode = body.get("mode")

    if mode == "models" and not (body.get("brand") and body.get("q")):
        raise HTTPException(status_code=422, detail="mode=models requires brand and q.")
    if mode == "diagrams" and not body.get("vin"):
        raise HTTPException(status_code=422, detail="mode=diagrams requires vin.")
    if mode == "diagram" and not (body.get("model") and body.get("diagram")):
        raise HTTPException(status_code=422, detail="mode=diagram requires model and diagram.")
    if not mode and not (body.get("vin") or (body.get("model") and body.get("q"))):
        raise HTTPException(
            status_code=422,
            detail="Provide vin and q, or model and q, or one of the documented lookup modes.",
        )

    return await provider_request("POST", "/lookup", json_body=body)

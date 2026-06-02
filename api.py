from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import motor.motor_asyncio
import os
import hashlib

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGO_URI")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client.lightpanel
licenses = db.licenses

class VerifyRequest(BaseModel):
    license_key: str
    hwid: str

@app.get("/")
async def root():
    return {"status": "LightPanel API Online"}

@app.post("/api/verify")
async def verify(request: VerifyRequest):
    license_data = await licenses.find_one({"key": request.license_key.upper()})
    
    if not license_data:
        return {"valid": False, "message": "Invalid key"}
    
    if license_data.get("revoked"):
        return {"valid": False, "message": "Key revoked"}
    
    if license_data["expiry"] < datetime.now():
        return {"valid": False, "message": "Key expired"}
    
    if license_data.get("used_by") and license_data["used_by"] != request.hwid:
        return {"valid": False, "message": "Key in use on another device"}
    
    if not license_data.get("used_by"):
        await licenses.update_one(
            {"key": request.license_key.upper()},
            {"$set": {"used_by": request.hwid, "used_at": datetime.now()}}
        )
    
    return {
        "valid": True,
        "expiry": license_data["expiry"].isoformat(),
        "message": f"Valid until {license_data['expiry'].strftime('%Y-%m-%d')}"
    }
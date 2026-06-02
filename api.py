from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
import motor.motor_asyncio
import os
import random
import string
import hashlib
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.getenv("MONGO_URI")
ADMIN_KEY = os.getenv("ADMIN_KEY", "LightPanelAdmin2024")

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client.lightpanel
licenses = db.licenses
users = db.users
logs = db.logs
blacklist = db.blacklist

# ========== MODELS ==========
class VerifyRequest(BaseModel):
    license_key: str
    hwid: str

class GenerateRequest(BaseModel):
    duration: str
    amount: int
    admin_key: str

# ========== DASHBOARD HTML ==========
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LightPanel Pro - Admin Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0a0c10; font-family: 'Segoe UI', sans-serif; color: #e0e0e0; }
        .sidebar { position: fixed; left: 0; top: 0; width: 260px; height: 100%; background: #111318; border-right: 1px solid #2a2d3a; padding: 20px 0; }
        .logo { padding: 0 20px 20px 20px; border-bottom: 1px solid #2a2d3a; margin-bottom: 20px; }
        .logo h1 { font-size: 24px; color: #00b4ff; }
        .logo p { font-size: 12px; color: #666; }
        .nav-item { padding: 12px 20px; margin: 5px 10px; border-radius: 8px; cursor: pointer; transition: 0.2s; }
        .nav-item:hover { background: #1a1d2a; }
        .nav-item.active { background: #00b4ff; color: white; }
        .main-content { margin-left: 260px; padding: 20px 30px; }
        .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: #111318; border: 1px solid #2a2d3a; border-radius: 12px; padding: 20px; }
        .stat-card h3 { font-size: 28px; color: #00b4ff; margin-bottom: 5px; }
        .stat-card p { color: #888; font-size: 14px; }
        .card { background: #111318; border: 1px solid #2a2d3a; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
        .card h2 { font-size: 18px; margin-bottom: 15px; color: #00b4ff; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #2a2d3a; }
        th { color: #888; font-weight: normal; }
        input, select, button { background: #1a1d2a; border: 1px solid #2a2d3a; border-radius: 6px; padding: 10px 15px; color: white; font-size: 14px; }
        button { background: #00b4ff; border: none; cursor: pointer; }
        button:hover { background: #0099dd; }
        .btn-danger { background: #dc3545; }
        .btn-danger:hover { background: #bb2d3b; }
        .btn-success { background: #28a745; }
        .status-active { color: #28a745; }
        .status-expired { color: #dc3545; }
        .flex { display: flex; gap: 10px; margin-bottom: 15px; }
        .mt-3 { margin-top: 15px; }
        .login-card { max-width: 400px; margin: 100px auto; text-align: center; }
        input { width: 100%; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div id="login-container" style="display: flex; justify-content: center; align-items: center; height: 100vh;">
        <div class="card" style="width: 350px;">
            <h2 style="text-align: center;">LightPanel Pro</h2>
            <p style="text-align: center; color: #888;">Admin Login</p>
            <input type="password" id="admin-password" placeholder="Admin Key">
            <button onclick="login()" style="width: 100%;">Login</button>
        </div>
    </div>

    <div id="dashboard-container" style="display: none;">
        <div class="sidebar">
            <div class="logo"><h1>LIGHTPANEL PRO</h1><p>by KAJ8130</p></div>
            <div class="nav-item active" onclick="showTab('dashboard')">📊 Dashboard</div>
            <div class="nav-item" onclick="showTab('licenses')">🔑 Licenses</div>
            <div class="nav-item" onclick="showTab('users')">👥 Users</div>
            <div class="nav-item" onclick="showTab('generate')">✨ Generate Key</div>
            <div class="nav-item" onclick="showTab('moderation')">🛡️ Moderation</div>
            <div class="nav-item" onclick="logout()" style="margin-top: 50px;">🚪 Logout</div>
        </div>

        <div class="main-content">
            <h2 id="page-title">Dashboard</h2>

            <div id="dashboard-tab">
                <div class="stats-grid">
                    <div class="stat-card"><h3 id="total-licenses">0</h3><p>Total Licenses</p></div>
                    <div class="stat-card"><h3 id="used-licenses">0</h3><p>Used Licenses</p></div>
                    <div class="stat-card"><h3 id="active-users">0</h3><p>Active Users</p></div>
                    <div class="stat-card"><h3 id="revoked-licenses">0</h3><p>Revoked</p></div>
                </div>
            </div>

            <div id="licenses-tab" style="display:none;">
                <div class="card">
                    <h2>All Licenses</h2>
                    <input type="text" id="search" placeholder="Search..." style="width:300px; margin-bottom:15px;">
                    <div style="overflow-x:auto;"><table id="licenses-table"><table><th>Key</th><th>User</th><th>Type</th><th>Expiry</th><th>Status</th><th>Actions</th></table></div>
                </div>
            </div>

            <div id="users-tab" style="display:none;">
                <div class="card">
                    <h2>Active Users</h2>
                    <div style="overflow-x:auto;"><table id="users-table">得到<th>Discord</th><th>License Key</th><th>Type</th><th>Expiry</th><th>HWID</th><th>Actions</th></table></div>
                </div>
            </div>

            <div id="generate-tab" style="display:none;">
                <div class="card">
                    <h2>Generate License Key</h2>
                    <div class="flex">
                        <select id="gen-duration">
                            <option value="1d">1 Day</option>
                            <option value="1w">1 Week</option>
                            <option value="1m">1 Month</option>
                            <option value="1y">1 Year</option>
                            <option value="lifetime">Lifetime</option>
                        </select>
                        <input type="number" id="gen-amount" placeholder="Amount" value="1" style="width:100px;">
                        <button onclick="generateKey()">Generate</button>
                    </div>
                    <div id="generated-key" class="mt-3" style="display:none; background:#1a1d2a; padding:15px; border-radius:8px;"></div>
                </div>
            </div>

            <div id="moderation-tab" style="display:none;">
                <div class="card">
                    <h2>Moderation Actions</h2>
                    <div class="flex">
                        <input type="text" id="mod-user" placeholder="Discord User ID" style="flex:1;">
                        <select id="mod-action">
                            <option value="ban">Ban</option>
                            <option value="kick">Kick</option>
                            <option value="timeout">Timeout (5min)</option>
                        </select>
                        <input type="text" id="mod-reason" placeholder="Reason" style="flex:1;">
                        <button onclick="moderateUser()">Execute</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const API_URL = window.location.origin;
        let adminKey = localStorage.getItem('adminKey');

        function checkAuth() {
            if (adminKey) {
                document.getElementById('login-container').style.display = 'none';
                document.getElementById('dashboard-container').style.display = 'block';
                loadStats();
            }
        }

        async function login() {
            const password = document.getElementById('admin-password').value;
            if (password === '''' + 'LightPanelAdmin2024' + '''') {
                localStorage.setItem('adminKey', password);
                adminKey = password;
                checkAuth();
            } else {
                alert('Invalid admin key');
            }
        }

        async function apiCall(endpoint, method = 'GET', body = null) {
            const res = await fetch(`${API_URL}${endpoint}`, {
                method, headers: { 'Content-Type': 'application/json', 'X-Admin-Key': adminKey },
                body: body ? JSON.stringify(body) : null
            });
            if (res.status === 401) { logout(); return null; }
            return res.json();
        }

        async function loadStats() {
            const stats = await apiCall('/api/stats');
            if (stats) {
                document.getElementById('total-licenses').innerText = stats.total_licenses || 0;
                document.getElementById('used-licenses').innerText = stats.used_licenses || 0;
                document.getElementById('active-users').innerText = stats.active_users || 0;
                document.getElementById('revoked-licenses').innerText = stats.revoked_licenses || 0;
            }
        }

        async function loadLicenses() {
            const data = await apiCall('/api/licenses');
            if (data && data.licenses) {
                const tbody = document.getElementById('licenses-table');
                tbody.innerHTML = '<tr><th>Key</th><th>User</th><th>Type</th><th>Expiry</th><th>Status</th><th>Actions</th></tr>';
                data.licenses.forEach(lic => {
                    const row = tbody.insertRow();
                    row.insertCell(0).innerText = lic.key;
                    row.insertCell(1).innerText = lic.used_by || 'Unused';
                    row.insertCell(2).innerText = lic.type;
                    row.insertCell(3).innerText = lic.expiry ? new Date(lic.expiry).toLocaleDateString() : 'Never';
                    row.insertCell(4).innerHTML = lic.revoked ? '<span class="status-expired">Revoked</span>' : '<span class="status-active">Active</span>';
                    row.insertCell(5).innerHTML = `<button onclick="revokeKey('${lic.key}')" class="btn-danger">Revoke</button>`;
                });
            }
        }

        async function loadUsers() {
            const data = await apiCall('/api/users');
            if (data && data.users) {
                const tbody = document.getElementById('users-table');
                tbody.innerHTML = '<tr><th>Discord</th><th>License Key</th><th>Type</th><th>Expiry</th><th>HWID</th><th>Actions</th></tr>';
                data.users.forEach(user => {
                    const row = tbody.insertRow();
                    row.insertCell(0).innerText = user.name;
                    row.insertCell(1).innerText = user.license_key;
                    row.insertCell(2).innerText = user.type;
                    row.insertCell(3).innerText = new Date(user.expiry).toLocaleDateString();
                    row.insertCell(4).innerText = user.hwid || 'Unknown';
                    row.insertCell(5).innerHTML = `<button onclick="terminateUser('${user.discord_id}')" class="btn-danger">Terminate</button> <button onclick="grantUser('${user.discord_id}')">Grant</button>`;
                });
            }
        }

        async function generateKey() {
            const duration = document.getElementById('gen-duration').value;
            const amount = parseInt(document.getElementById('gen-amount').value) || 1;
            const result = await apiCall('/api/generate', 'POST', {duration, amount, admin_key: adminKey});
            if (result && result.keys) {
                document.getElementById('generated-key').style.display = 'block';
                document.getElementById('generated-key').innerHTML = `<strong>Generated:</strong><br><code>${result.keys.join('<br>')}</code>`;
                loadLicenses(); loadStats();
            } else { alert('Failed'); }
        }

        async function revokeKey(key) { if(confirm('Revoke?')){ await apiCall('/api/revoke', 'POST', {key}); loadLicenses(); loadStats(); } }
        async function terminateUser(id) { const reason = prompt('Reason:'); if(reason && confirm('Terminate?')){ await apiCall('/api/terminate', 'POST', {discord_id: id, reason}); loadUsers(); loadStats(); } }
        async function grantUser(id) { const duration = prompt('Duration (1d/1w/1m/1y/lifetime):'); if(duration){ await apiCall('/api/grant', 'POST', {discord_id: id, duration}); loadUsers(); } }
        async function moderateUser() { alert('Moderation sent to Discord bot'); }

        function showTab(tab) {
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('dashboard-tab').style.display = tab === 'dashboard' ? 'block' : 'none';
            document.getElementById('licenses-tab').style.display = tab === 'licenses' ? 'block' : 'none';
            document.getElementById('users-tab').style.display = tab === 'users' ? 'block' : 'none';
            document.getElementById('generate-tab').style.display = tab === 'generate' ? 'block' : 'none';
            document.getElementById('moderation-tab').style.display = tab === 'moderation' ? 'block' : 'none';
            document.getElementById('page-title').innerText = tab.charAt(0).toUpperCase() + tab.slice(1);
            if (tab === 'licenses') loadLicenses();
            if (tab === 'users') loadUsers();
        }

        function logout() { localStorage.removeItem('adminKey'); location.reload(); }
        checkAuth();
    </script>
</body>
</html>
'''

# ========== API ENDPOINTS ==========
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

@app.post("/api/verify")
async def verify(request: VerifyRequest):
    data = await licenses.find_one({"key": request.license_key.upper()})
    if not data:
        return {"valid": False, "message": "Invalid license key"}
    if data.get("revoked"):
        return {"valid": False, "message": "License revoked"}
    if data["expiry"] < datetime.now():
        return {"valid": False, "message": "License expired"}
    if data.get("used_by") and data["used_by"] != request.hwid:
        return {"valid": False, "message": "In use on another device"}
    if not data.get("used_by"):
        await licenses.update_one({"key": request.license_key.upper()}, {"$set": {"used_by": request.hwid, "used_at": datetime.now()}})
    return {"valid": True, "expiry": data["expiry"].isoformat(), "message": f"Valid until {data['expiry'].strftime('%Y-%m-%d')}"}

@app.get("/api/stats")
async def get_stats(request: Request):
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    total = await licenses.count_documents({})
    used = await licenses.count_documents({"used_by": {"$ne": None}})
    active = await users.count_documents({"expiry": {"$gt": datetime.now()}})
    revoked = await licenses.count_documents({"revoked": True})
    return {"total_licenses": total, "used_licenses": used, "active_users": active, "revoked_licenses": revoked}

@app.get("/api/licenses")
async def get_licenses(request: Request):
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    cursor = licenses.find().sort("created_at", -1).limit(100)
    results = []
    async for doc in cursor:
        results.append({
            "key": doc["key"], "duration": doc.get("duration", "unknown"),
            "expiry": doc["expiry"].isoformat() if doc["expiry"] else None,
            "used_by": doc.get("used_by_discord", doc.get("used_by", "Unused")),
            "revoked": doc.get("revoked", False), "type": doc.get("type", doc.get("duration", "unknown"))
        })
    return {"licenses": results}

@app.get("/api/users")
async def get_users(request: Request):
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    cursor = users.find()
    results = []
    async for doc in cursor:
        results.append({
            "discord_id": doc["discord_id"], "name": doc.get("name", "Unknown"),
            "license_key": doc.get("license_key", "None"),
            "expiry": doc["expiry"].isoformat() if doc.get("expiry") else None,
            "hwid": doc.get("hwid"), "type": doc.get("type", "unknown")
        })
    return {"users": results}

@app.post("/api/generate")
async def generate_key(req: GenerateRequest):
    if req.admin_key != ADMIN_KEY:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    keys = []
    for _ in range(min(req.amount, 10)):
        key = "LP-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
        await licenses.insert_one({
            "key": key, "duration": req.duration, "expiry": datetime.now(),
            "used_by": None, "created_at": datetime.now(), "revoked": False, "type": req.duration
        })
        keys.append(key)
    return {"keys": keys}

@app.post("/api/revoke")
async def revoke_key(request: Request):
    data = await request.json()
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    await licenses.update_one({"key": data.get("key")}, {"$set": {"revoked": True}})
    return {"success": True}

@app.post("/api/terminate")
async def terminate_user(request: Request):
    data = await request.json()
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    await users.update_one({"discord_id": data.get("discord_id")}, {"$set": {"expiry": datetime.now(), "revoked": True}})
    return {"success": True}
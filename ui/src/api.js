import axios from 'axios';

// Defaults to uvicorn's default port for local dev (docs/setup.md has no
// documented alternative yet); override with VITE_API_BASE_URL for any
// other deployment.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const client = axios.create({ baseURL: API_BASE_URL });

function authHeader(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// api/main.py's http_exception_handler returns {"error": detail, "status_code"}
// instead of FastAPI's default {"detail": ...} -- unwrap that shape here so
// every caller gets one consistent message string, not two different ones
// depending on whether FastAPI or that handler produced the error.
function unwrap(err) {
  const detail = err.response?.data?.error || err.response?.data?.detail;
  throw new Error(detail || err.message);
}

export async function login(username, password) {
  try {
    const res = await client.post('/auth/login', { username, password });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

export async function getMe(token) {
  try {
    const res = await client.get('/me', { headers: authHeader(token) });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

export async function listZones(token) {
  try {
    const res = await client.get('/zones', { headers: authHeader(token) });
    return res.data.zones;
  } catch (err) {
    unwrap(err);
  }
}

export async function submitZoneTelemetry(token, zoneId, reading) {
  try {
    const res = await client.post(`/zones/${zoneId}/telemetry`, reading, {
      headers: authHeader(token),
    });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

export async function queryChemical(token, chemicalName, zoneId) {
  try {
    const res = await client.post(
      '/query',
      { chemical_name: chemicalName, zone_id: zoneId },
      { headers: authHeader(token) }
    );
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

export async function listAlerts(token) {
  try {
    const res = await client.get('/alerts', { headers: authHeader(token) });
    return res.data.alerts;
  } catch (err) {
    unwrap(err);
  }
}

export async function signOffAlert(token, alertId, approved, notes) {
  try {
    const res = await client.post('/admin/sign-off', null, {
      params: { alert_id: alertId, approved, notes },
      headers: authHeader(token),
    });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

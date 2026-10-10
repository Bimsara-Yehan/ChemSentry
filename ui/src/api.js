import axios from 'axios';

// Defaults to uvicorn's default port for local dev (docs/setup.md has no
// documented alternative yet); override with VITE_API_BASE_URL for any
// other deployment.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const client = axios.create({ baseURL: API_BASE_URL });

// A 401 on any authenticated call means the stored session is no longer valid
// (expired, or the server's signing key changed). App registers a handler that
// signs the user out cleanly instead of leaving every panel showing errors.
let unauthorizedHandler = null;

export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

client.interceptors.response.use(
  (res) => res,
  (err) => {
    const isLogin = err.config?.url === '/auth/login';
    if (err.response?.status === 401 && !isLogin && unauthorizedHandler) {
      unauthorizedHandler();
    }
    return Promise.reject(err);
  }
);

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

export async function createUser(token, username, password, role) {
  try {
    const res = await client.post(
      '/users',
      { username, password, role },
      { headers: authHeader(token) }
    );
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

export async function listUsers(token) {
  try {
    const res = await client.get('/users', { headers: authHeader(token) });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

export async function createZone(token, zoneId, chemicals = []) {
  try {
    const res = await client.post(
      '/zones',
      { zone_id: zoneId, chemicals },
      { headers: authHeader(token) }
    );
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

export async function addChemicalToZone(token, zoneId, chemicalName) {
  try {
    const res = await client.post(
      `/zones/${zoneId}/chemicals`,
      { chemical_name: chemicalName },
      { headers: authHeader(token) }
    );
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

export async function removeChemicalFromZone(token, zoneId, chemicalName) {
  try {
    const res = await client.delete(`/zones/${zoneId}/chemicals/${chemicalName}`, {
      headers: authHeader(token),
    });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

// No auth header -- GET /health takes no `user` dependency in api/main.py,
// matching its job as an unauthenticated liveness check.
export async function getHealth() {
  const res = await client.get('/health');
  return res.data;
}

export async function getAuditLog(token, limit = 50, offset = 0) {
  try {
    const res = await client.get('/audit-log', {
      params: { limit, offset },
      headers: authHeader(token),
    });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

export async function uploadSdsDocument(token, file, chemicalName = '', supplier = '') {
  try {
    const formData = new FormData();
    formData.append('file', file);
    if (chemicalName) formData.append('chemical_name', chemicalName);
    if (supplier) formData.append('supplier', supplier);

    const res = await client.post('/corpus/documents', formData, {
      headers: {
        ...authHeader(token),
        'Content-Type': 'multipart/form-data',
      },
    });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}



// Agent B (M3): Apriori co-storage patterns for a zone, each cross-checked
// against the CAMEO reactivity lookup. Informational -- not a safety verdict.
export async function getCoStorageCheck(token, zoneId) {
  try {
    const res = await client.get(`/zones/${zoneId}/co-storage-check`, {
      headers: authHeader(token),
    });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

// Agent B (M3): plain-language explanation of an already-decided alert, with
// an optional Sinhala ('si') or Tamil ('ta') safety card. The verdict in the
// response is always the stored deterministic one, never the LLM's.
export async function narrateAlert(token, alertId, language) {
  try {
    const res = await client.post(`/alerts/${alertId}/narrate`, null, {
      params: language ? { language } : {},
      headers: authHeader(token),
    });
    return res.data;
  } catch (err) {
    unwrap(err);
  }
}

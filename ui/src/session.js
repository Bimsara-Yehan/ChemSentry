// Session persistence so a page refresh doesn't drop a logged-in user back to
// the login screen. The JWT used to live only in React state, which a reload
// wipes.
//
// sessionStorage rather than localStorage: the session survives refreshes
// and in-tab navigation, but closing the tab signs the operator out. For a
// safety console that holds sign-off authority, that's the safer default --
// an unattended shared workstation doesn't stay logged in indefinitely.
//
// The stored token is never trusted on its own: App re-validates it with
// GET /me on load, and an expired token (checked locally via its `exp` claim)
// is discarded before any request is made.

const TOKEN_KEY = 'chemsentry.token';
const TAB_KEY = 'chemsentry.tab';

function storage() {
  try {
    return window.sessionStorage;
  } catch {
    // Storage can throw in locked-down/private contexts; fall back to an
    // in-memory session (the old behaviour) rather than crashing.
    return null;
  }
}

// Reads the JWT's `exp` claim without verifying the signature -- only to
// avoid sending a token we already know is expired. The backend still does
// the real verification on every request.
function isExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp === 'number' && payload.exp * 1000 <= Date.now();
  } catch {
    return true;
  }
}

export function loadToken() {
  const s = storage();
  const token = s?.getItem(TOKEN_KEY);
  if (!token) return null;
  if (isExpired(token)) {
    s.removeItem(TOKEN_KEY);
    return null;
  }
  return token;
}

export function saveToken(token) {
  try {
    storage()?.setItem(TOKEN_KEY, token);
  } catch {
    /* quota / disabled storage: session just won't survive a refresh */
  }
}

export function clearSession() {
  try {
    storage()?.removeItem(TOKEN_KEY);
    storage()?.removeItem(TAB_KEY);
  } catch {
    /* ignore */
  }
}

export function loadTab(fallback) {
  try {
    return storage()?.getItem(TAB_KEY) || fallback;
  } catch {
    return fallback;
  }
}

export function saveTab(tab) {
  try {
    storage()?.setItem(TAB_KEY, tab);
  } catch {
    /* ignore */
  }
}

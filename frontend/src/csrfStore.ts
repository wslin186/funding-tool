let _token: string | null = null;
let _inflight: Promise<string> | null = null;

const BASE = "/funding/api";

async function fetchToken(): Promise<string> {
  const res = await fetch(`${BASE}/csrf`, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`csrf fetch failed: ${res.status}`);
  const body = await res.json();
  return body.token as string;
}

export const csrfStore = {
  async getToken(): Promise<string> {
    if (_token) return _token;
    if (!_inflight) _inflight = fetchToken().then(t => { _token = t; _inflight = null; return t; });
    return _inflight;
  },
  async refresh(): Promise<void> {
    _token = null;
    _inflight = null;
    _token = await fetchToken();
  },
  _set(t: string) { _token = t; },
};

export function resetCsrf() { _token = null; _inflight = null; }

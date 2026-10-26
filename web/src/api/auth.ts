
const TOKEN_KEY = 'lha_access_token';
const USER_KEY = 'lha_user';
export const AUTH_REQUIRED_EVENT = 'lha:auth-required';

export function requireLogin(requestToken: string = getToken()) {
  // A late response from an old session must not clear a newer login.
  if (getToken() !== requestToken) return;
  clearSession();
  window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
}

export interface AuthUser {
  id: string;
  tenant_id: string;
  nickname: string;
  email?: string;
  role: string;
}

export interface AuthData {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setSession(data: AuthData) {
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(data.user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getToken();
  const base: Record<string, string> = {};
  if (token) base.Authorization = `Bearer ${token}`;
  return { ...base, ...(extra as Record<string, string> | undefined) };
}

export async function apiFetch(input: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers || {});
  const token = getToken();
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const resp = await fetch(input, { ...init, headers });
  if (resp.status === 401) requireLogin(token);
  return resp;
}

export function eventsURL(taskId: string): string {
  const token = getToken();
  const base = `/api/v1/tasks/${taskId}/events`;
  if (!token) return base;
  return `${base}?access_token=${encodeURIComponent(token)}`;
}

export async function login(email: string, password: string): Promise<AuthData> {
  const resp = await fetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const json = await resp.json();
  if (!resp.ok || json.code !== 0) {
    throw new Error(json?.error?.message || '登录失败');
  }
  setSession(json.data);
  return json.data;
}

export async function register(email: string, password: string, nickname?: string): Promise<AuthData> {
  const resp = await fetch('/api/v1/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, nickname }),
  });
  const json = await resp.json();
  if (!resp.ok || json.code !== 0) {
    throw new Error(json?.error?.message || '注册失败');
  }
  setSession(json.data);
  return json.data;
}

export async function fetchMe(): Promise<AuthUser | null> {
  const token = getToken();
  if (!token) return null;
  const resp = await apiFetch('/api/v1/auth/me');
  if (getToken() !== token) return null;
  if (!resp.ok) return null;
  const json = await resp.json();
  if (json.code !== 0) return null;
  const u = json.data as AuthUser & { authenticated?: boolean };
  if (u.authenticated === false) {
    requireLogin(token);
    return null;
  }
  if (u?.id) {
    localStorage.setItem(USER_KEY, JSON.stringify({
      id: u.id, tenant_id: u.tenant_id, nickname: u.nickname,
      email: u.email, role: u.role,
    }));
  }
  return u;
}

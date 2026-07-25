import type { Product, ProductCreate, Session, StockBalance } from "../types";

const SESSION_KEY = "ai-raktar-session";
let refreshPromise: Promise<Session> | null = null;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function readSession(): Session | null {
  const serialized = localStorage.getItem(SESSION_KEY);
  if (!serialized) return null;
  try {
    return JSON.parse(serialized) as Session;
  } catch {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function saveSession(session: Session): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  authenticated = true
): Promise<T> {
  const execute = (session: Session | null) => {
    const headers = new Headers(options.headers);
    headers.set("Content-Type", "application/json");
    headers.set("X-Correlation-ID", crypto.randomUUID());
    if (authenticated && session) {
      headers.set("Authorization", `Bearer ${session.access_token}`);
    }
    return fetch(`/api/v1${path}`, { ...options, headers });
  };

  let session = readSession();
  let response = await execute(session);
  if (response.status === 401 && authenticated && session) {
    try {
      session = await refreshAccessToken(session.refresh_token);
      response = await execute(session);
    } catch {
      clearSession();
      window.dispatchEvent(new Event("session-expired"));
    }
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: { message?: string } | string }
      | null;
    const message =
      typeof payload?.detail === "string"
        ? payload.detail
        : payload?.detail?.message ?? "A kérés nem sikerült.";
    if (response.status === 401 && authenticated) {
      clearSession();
      window.dispatchEvent(new Event("session-expired"));
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function refreshAccessToken(refreshToken: string): Promise<Session> {
  if (!refreshPromise) {
    refreshPromise = fetch("/api/v1/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken })
    })
      .then(async (response) => {
        if (!response.ok) throw new ApiError("A munkamenet lejárt.", response.status);
        const session = (await response.json()) as Session;
        saveSession(session);
        return session;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export function login(
  organizationSlug: string,
  email: string,
  password: string
): Promise<Session> {
  return request<Session>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify({
        organization_slug: organizationSlug,
        email,
        password
      })
    },
    false
  );
}

export async function logout(): Promise<void> {
  const session = readSession();
  if (!session) return;
  await request(
    "/auth/logout",
    {
      method: "POST",
      body: JSON.stringify({ refresh_token: session.refresh_token })
    },
    false
  );
}

export function getProducts(): Promise<Product[]> {
  return request<Product[]>("/products");
}

export function getStock(): Promise<StockBalance[]> {
  return request<StockBalance[]>("/stock");
}

export function createProduct(payload: ProductCreate): Promise<Product> {
  return request<Product>("/products", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function correctStock(
  productId: string,
  countedQuantity: number,
  reason: string
): Promise<unknown> {
  return request("/stock/correct", {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({
      product_id: productId,
      counted_quantity: countedQuantity,
      reason
    })
  });
}

export function receiveStock(
  productId: string,
  quantity: number,
  reason: string
): Promise<unknown> {
  const operationId = crypto.randomUUID();
  return request("/stock/receive", {
    method: "POST",
    headers: { "Idempotency-Key": operationId },
    body: JSON.stringify({
      product_id: productId,
      quantity,
      source_id: `manual:${operationId}`,
      reason
    })
  });
}

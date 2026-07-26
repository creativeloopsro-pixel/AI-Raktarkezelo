import type {
  ApiTokenItem,
  CreatedApiToken,
  DocumentItem,
  EmailInboundSettings,
  EmailInboundSettingsUpdate,
  GoodsReceiptDraft,
  InboundEmail,
  InventoryCountPayload,
  InventorySession,
  IdentityRole,
  IdentityUser,
  MfaChallenge,
  MfaSetup,
  PermissionItem,
  PluginItem,
  PluginJob,
  PluginOverview,
  Product,
  ProductCreate,
  ReviewTask,
  RefreshSessionItem,
  ResumableUpload,
  ResumableUploadResult,
  Session,
  StockBalance,
  VrpImportBatch,
  VrpSchedule,
  VrpScheduleUpdate
} from "../types";

const SESSION_KEY = "ai-raktar-session";
let refreshPromise: Promise<Session> | null = null;

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(message: string, status: number, code = "request_failed") {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function readSession(): Session | null {
  const serialized = localStorage.getItem(SESSION_KEY);
  if (!serialized) return null;
  try {
    const parsed = JSON.parse(serialized) as Session;
    if (!Array.isArray(parsed.user?.permissions)) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return parsed;
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
    if (
      options.body !== undefined &&
      !(options.body instanceof FormData) &&
      !(options.body instanceof Blob) &&
      !(options.body instanceof ArrayBuffer)
    ) {
      headers.set("Content-Type", "application/json");
    }
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
      | { detail?: { message?: string; code?: string } | string }
      | null;
    const message =
      typeof payload?.detail === "string"
        ? payload.detail
        : payload?.detail?.message ?? "A kérés nem sikerült.";
    if (response.status === 401 && authenticated) {
      clearSession();
      window.dispatchEvent(new Event("session-expired"));
    }
    const code =
      typeof payload?.detail === "object"
        ? payload.detail.code ?? "request_failed"
        : "request_failed";
    throw new ApiError(message, response.status, code);
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
): Promise<Session | MfaChallenge> {
  return request<Session | MfaChallenge>(
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

export function verifyMfa(
  challengeToken: string,
  code: string
): Promise<Session> {
  return request<Session>(
    "/auth/mfa/verify",
    {
      method: "POST",
      body: JSON.stringify({
        challenge_token: challengeToken,
        code
      })
    },
    false
  );
}

export function setupMfa(): Promise<MfaSetup> {
  return request<MfaSetup>("/auth/mfa/setup", { method: "POST" });
}

export function confirmMfa(
  code: string
): Promise<{ recovery_codes: string[]; session: Session }> {
  return request("/auth/mfa/confirm", {
    method: "POST",
    body: JSON.stringify({ code })
  });
}

export function getRefreshSessions(): Promise<RefreshSessionItem[]> {
  return request<RefreshSessionItem[]>("/auth/sessions");
}

export function revokeRefreshSession(sessionId: string): Promise<void> {
  return request(`/auth/sessions/${sessionId}`, { method: "DELETE" });
}

export function revokeOtherSessions(): Promise<void> {
  return request("/auth/sessions/revoke-others", { method: "POST" });
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

export function getProductByCode(code: string): Promise<Product> {
  return request<Product>(`/products/by-code/${encodeURIComponent(code)}`);
}

export function getCurrentInventorySession(): Promise<InventorySession | null> {
  return request<InventorySession | null>("/inventory/sessions/current");
}

export function getInventorySessions(): Promise<InventorySession[]> {
  return request<InventorySession[]>("/inventory/sessions?limit=20");
}

export function startInventorySession(
  name: string,
  clientSessionId = crypto.randomUUID()
): Promise<InventorySession> {
  return request<InventorySession>("/inventory/sessions", {
    method: "POST",
    body: JSON.stringify({
      name,
      client_session_id: clientSessionId
    })
  });
}

export function recordInventoryCount(
  sessionId: string,
  payload: InventoryCountPayload
): Promise<InventorySession> {
  return request<InventorySession>(
    `/inventory/sessions/${sessionId}/counts`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function completeInventorySession(
  sessionId: string,
  note: string
): Promise<InventorySession> {
  return request<InventorySession>(
    `/inventory/sessions/${sessionId}/complete`,
    {
      method: "POST",
      body: JSON.stringify({ note: note.trim() || null })
    }
  );
}

export function approveInventorySession(
  sessionId: string,
  note: string
): Promise<InventorySession> {
  return request<InventorySession>(
    `/inventory/sessions/${sessionId}/approve`,
    {
      method: "POST",
      body: JSON.stringify({ note: note.trim() || null })
    }
  );
}

export function cancelInventorySession(
  sessionId: string,
  note: string
): Promise<InventorySession> {
  return request<InventorySession>(
    `/inventory/sessions/${sessionId}/cancel`,
    {
      method: "POST",
      body: JSON.stringify({ note })
    }
  );
}

export function getDocuments(): Promise<DocumentItem[]> {
  return request<DocumentItem[]>("/documents");
}

type DocumentUploadOptions = {
  autoProcess?: boolean;
  autoConfirm?: boolean;
};

export function uploadDocument(
  file: File,
  documentType = "goods_receipt",
  options: DocumentUploadOptions = {}
): Promise<DocumentItem> {
  const form = new FormData();
  form.set("file", file);
  form.set("document_type", documentType);
  form.set("auto_process", String(options.autoProcess ?? false));
  form.set("auto_confirm", String(options.autoConfirm ?? false));
  return request<DocumentItem>("/documents", {
    method: "POST",
    body: form
  });
}

export function queueDocument(documentId: string): Promise<unknown> {
  return request(`/documents/${documentId}/process`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() }
  });
}

export function getReviewTasks(): Promise<ReviewTask[]> {
  return request<ReviewTask[]>("/review-tasks?status=OPEN");
}

export function resolveReviewTask(taskId: string, resolutionNote: string): Promise<ReviewTask> {
  return request<ReviewTask>(`/review-tasks/${taskId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolution_note: resolutionNote })
  });
}

export function getGoodsReceipt(documentId: string): Promise<GoodsReceiptDraft> {
  return request<GoodsReceiptDraft>(`/goods-receipts/by-document/${documentId}`);
}

export function updateGoodsReceiptItem(
  draftId: string,
  itemId: string,
  productId: string,
  packagingUnitId: string | null,
  quantity: number
): Promise<GoodsReceiptDraft> {
  return request<GoodsReceiptDraft>(`/goods-receipts/${draftId}/items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify({
      product_id: productId,
      packaging_unit_id: packagingUnitId,
      quantity
    })
  });
}

export function confirmGoodsReceipt(draftId: string): Promise<GoodsReceiptDraft> {
  return request<GoodsReceiptDraft>(`/goods-receipts/${draftId}/confirm`, {
    method: "POST"
  });
}

export async function downloadDocument(document: DocumentItem): Promise<void> {
  let session = readSession();
  if (!session) throw new ApiError("A munkamenet lejárt.", 401);

  const execute = (currentSession: Session) =>
    fetch(`/api/v1/documents/${document.id}/download`, {
      headers: {
        Authorization: `Bearer ${currentSession.access_token}`,
        "X-Correlation-ID": crypto.randomUUID()
      }
    });

  let response = await execute(session);
  if (response.status === 401) {
    try {
      session = await refreshAccessToken(session.refresh_token);
      response = await execute(session);
    } catch {
      clearSession();
      window.dispatchEvent(new Event("session-expired"));
      throw new ApiError("A munkamenet lejárt.", 401);
    }
  }
  if (!response.ok) {
    throw new ApiError("A dokumentum letöltése sikertelen.", response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = window.document.createElement("a");
  anchor.href = url;
  anchor.download = document.original_filename;
  anchor.click();
  URL.revokeObjectURL(url);
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

export function getVrpImports(): Promise<VrpImportBatch[]> {
  return request<VrpImportBatch[]>("/vrp/imports");
}

export function getVrpImport(batchId: string): Promise<VrpImportBatch> {
  return request<VrpImportBatch>(`/vrp/imports/${batchId}`);
}

export function uploadVrpImport(
  file: File,
  periodStart: string,
  periodEnd: string,
  externalReportId: string
): Promise<VrpImportBatch> {
  const form = new FormData();
  form.set("file", file);
  form.set("period_start", periodStart);
  form.set("period_end", periodEnd);
  if (externalReportId.trim()) {
    form.set("external_report_id", externalReportId.trim());
  }
  return request<VrpImportBatch>("/vrp/imports", {
    method: "POST",
    body: form
  });
}

export function updateVrpItem(
  batchId: string,
  itemId: string,
  productId: string,
  conversionFactor: number
): Promise<VrpImportBatch> {
  return request<VrpImportBatch>(
    `/vrp/imports/${batchId}/items/${itemId}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        product_id: productId,
        conversion_factor: conversionFactor
      })
    }
  );
}

export function processVrpImport(batchId: string): Promise<VrpImportBatch> {
  return request<VrpImportBatch>(`/vrp/imports/${batchId}/process`, {
    method: "POST"
  });
}

export function reverseVrpImport(
  batchId: string,
  reason: string
): Promise<VrpImportBatch> {
  return request<VrpImportBatch>(`/vrp/imports/${batchId}/reverse`, {
    method: "POST",
    body: JSON.stringify({ reason })
  });
}

export function getVrpSchedule(): Promise<VrpSchedule> {
  return request<VrpSchedule>("/vrp/schedule");
}

export function updateVrpSchedule(
  payload: VrpScheduleUpdate
): Promise<VrpSchedule> {
  return request<VrpSchedule>("/vrp/schedule", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function getEmailSettings(): Promise<EmailInboundSettings> {
  return request<EmailInboundSettings>("/email/settings");
}

export function updateEmailSettings(
  payload: EmailInboundSettingsUpdate
): Promise<EmailInboundSettings> {
  return request<EmailInboundSettings>("/email/settings", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function rotateEmailAddress(): Promise<EmailInboundSettings> {
  return request<EmailInboundSettings>("/email/settings/rotate-address", {
    method: "POST"
  });
}

export function getInboundEmails(): Promise<InboundEmail[]> {
  return request<InboundEmail[]>("/email/messages");
}

export function getPlugins(): Promise<PluginOverview> {
  return request<PluginOverview>("/plugins");
}

export function getPluginJobs(): Promise<PluginJob[]> {
  return request<PluginJob[]>("/plugins/jobs");
}

export function enablePlugin(pluginId: string): Promise<PluginItem> {
  return request<PluginItem>(`/plugins/${pluginId}/enable`, {
    method: "POST"
  });
}

export function disablePlugin(pluginId: string): Promise<PluginItem> {
  return request<PluginItem>(`/plugins/${pluginId}/disable`, {
    method: "POST"
  });
}

export function updatePluginPermissions(
  pluginId: string,
  grantedPermissions: string[]
): Promise<PluginItem> {
  return request<PluginItem>(`/plugins/${pluginId}/permissions`, {
    method: "PUT",
    body: JSON.stringify({ granted_permissions: grantedPermissions })
  });
}

export function updatePluginSettings(
  pluginId: string,
  values: Record<string, unknown>
): Promise<PluginItem> {
  return request<PluginItem>(`/plugins/${pluginId}/settings`, {
    method: "PUT",
    body: JSON.stringify({ values })
  });
}

export function installPlugin(
  manifest: Record<string, unknown>
): Promise<PluginItem> {
  return request<PluginItem>("/plugins/install", {
    method: "POST",
    body: JSON.stringify(manifest)
  });
}

export function getIdentityPermissions(): Promise<PermissionItem[]> {
  return request<PermissionItem[]>("/identity/permissions");
}

export function getIdentityRoles(): Promise<IdentityRole[]> {
  return request<IdentityRole[]>("/identity/roles");
}

export function createIdentityRole(payload: {
  name: string;
  slug: string;
  description: string;
  permission_codes: string[];
}): Promise<IdentityRole> {
  return request<IdentityRole>("/identity/roles", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateIdentityRole(
  roleId: string,
  payload: {
    name: string;
    description: string;
    permission_codes: string[];
  }
): Promise<IdentityRole> {
  return request<IdentityRole>(`/identity/roles/${roleId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function deleteIdentityRole(roleId: string): Promise<void> {
  return request(`/identity/roles/${roleId}`, { method: "DELETE" });
}

export function getIdentityUsers(): Promise<IdentityUser[]> {
  return request<IdentityUser[]>("/identity/users");
}

export function createIdentityUser(payload: {
  email: string;
  full_name: string;
  password: string;
  role_ids: string[];
}): Promise<IdentityUser> {
  return request<IdentityUser>("/identity/users", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateIdentityUser(
  userId: string,
  payload: {
    email: string;
    full_name: string;
    role_ids: string[];
    is_active: boolean;
    password: string | null;
  }
): Promise<IdentityUser> {
  return request<IdentityUser>(`/identity/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export function getApiTokens(): Promise<ApiTokenItem[]> {
  return request<ApiTokenItem[]>("/identity/tokens");
}

export function createApiToken(payload: {
  name: string;
  scopes: string[];
  expires_at: string | null;
}): Promise<CreatedApiToken> {
  return request<CreatedApiToken>("/identity/tokens", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function revokeApiToken(tokenId: string): Promise<ApiTokenItem> {
  return request<ApiTokenItem>(`/identity/tokens/${tokenId}`, {
    method: "DELETE"
  });
}

export function createResumableUpload(payload: {
  client_upload_id: string;
  target_type: "DOCUMENT" | "VRP";
  filename: string;
  declared_content_type: string | null;
  total_size: number;
  file_sha256: string | null;
  metadata: Record<string, string | number | boolean | null>;
}): Promise<ResumableUpload> {
  return request<ResumableUpload>("/uploads", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getResumableUploads(
  targetType: "DOCUMENT" | "VRP"
): Promise<ResumableUpload[]> {
  return request<ResumableUpload[]>(
    `/uploads?target_type=${encodeURIComponent(targetType)}`
  );
}

export function uploadResumableChunk(
  uploadId: string,
  chunkIndex: number,
  chunk: Blob,
  chunkSha256: string
): Promise<ResumableUpload> {
  return request<ResumableUpload>(
    `/uploads/${uploadId}/chunks/${chunkIndex}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Chunk-SHA256": chunkSha256
      },
      body: chunk
    }
  );
}

export function completeResumableUpload(
  uploadId: string,
  fileSha256: string
): Promise<ResumableUploadResult> {
  return request<ResumableUploadResult>(`/uploads/${uploadId}/complete`, {
    method: "POST",
    body: JSON.stringify({ file_sha256: fileSha256 })
  });
}

export function cancelResumableUpload(
  uploadId: string
): Promise<ResumableUpload> {
  return request<ResumableUpload>(`/uploads/${uploadId}`, {
    method: "DELETE"
  });
}

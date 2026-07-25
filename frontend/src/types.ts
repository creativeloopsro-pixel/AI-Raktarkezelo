export type User = {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: string;
};

export type Session = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
};

export type PackagingUnit = {
  id: string;
  name: string;
  multiplier_to_base_unit: string;
};

export type Barcode = {
  id: string;
  code: string;
  symbology: string;
  is_primary: boolean;
  packaging_unit_id: string | null;
};

export type Product = {
  id: string;
  name: string;
  internal_sku: string;
  base_unit: string;
  status: string;
  min_stock: string;
  version: number;
  packaging_units: PackagingUnit[];
  barcodes: Barcode[];
  created_at: string;
  updated_at: string;
};

export type StockBalance = {
  product_id: string;
  product_name: string;
  internal_sku: string;
  quantity: string;
  min_stock: string;
  updated_at: string | null;
};

export type ProductCreate = {
  name: string;
  internal_sku: string;
  base_unit: string;
  min_stock: number;
  packaging_units: Array<{
    name: string;
    multiplier_to_base_unit: number;
  }>;
  barcodes: Array<{
    code: string;
    symbology: string;
    is_primary: boolean;
    packaging_unit_name: string | null;
  }>;
};

export type DocumentItem = {
  id: string;
  organization_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256_hash: string;
  status: string;
  source_type: string;
  document_type: string;
  page_count: number;
  validation_summary: {
    issues?: string[];
    virus_scan?: string;
    declared_content_type?: string | null;
  };
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
};

export type ReviewTask = {
  id: string;
  organization_id: string;
  task_type: string;
  entity_type: string;
  entity_id: string;
  reason_code: string;
  status: string;
  context: {
    filename?: string;
    issues?: string[];
    document_id?: string;
    draft_id?: string;
    batch_id?: string;
    period_start?: string;
    period_end?: string;
  };
  assigned_to: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  created_at: string;
  resolved_at: string | null;
};

export type AiRequestMetadata = {
  id: string;
  provider: string;
  model_name: string;
  prompt_version: string;
  status: string;
  duration_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  error_code: string | null;
  created_at: string;
  completed_at: string | null;
};

export type GoodsReceiptItem = {
  id: string;
  line_number: number;
  description: string;
  barcode: string | null;
  quantity: string;
  unit: string;
  confidence: string;
  source_page: number;
  matched_product_id: string | null;
  packaging_unit_id: string | null;
  conversion_factor: string | null;
  base_quantity: string | null;
  match_method: string | null;
  status: string;
  validation_issues: string[];
  matched_product: {
    id: string;
    name: string;
    internal_sku: string;
    base_unit: string;
  } | null;
  packaging_unit: PackagingUnit | null;
};

export type GoodsReceiptDraft = {
  id: string;
  organization_id: string;
  document_id: string;
  document_number: string | null;
  document_date: string | null;
  status: string;
  validation_issues: string[];
  confirmed_by: string | null;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
  ai_result: {
    id: string;
    overall_confidence: string;
    model_version: string | null;
    created_at: string;
    request: AiRequestMetadata;
  };
  items: GoodsReceiptItem[];
};

export type VrpImportItem = {
  id: string;
  line_number: number;
  external_product_id: string | null;
  external_name: string;
  quantity: string;
  unit: string;
  matched_product_id: string | null;
  conversion_factor: string | null;
  base_quantity: string | null;
  match_method: string | null;
  status: string;
  validation_issues: string[];
  matched_product: {
    id: string;
    name: string;
    internal_sku: string;
    base_unit: string;
  } | null;
};

export type VrpImportError = {
  id: string;
  line_number: number | null;
  error_code: string;
  message: string;
  raw_row: Record<string, unknown>;
};

export type VrpImportBatch = {
  id: string;
  organization_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  file_hash: string;
  canonical_items_hash: string;
  parser_version: string;
  external_report_id: string | null;
  period_start: string;
  period_end: string;
  status: string;
  scheduled_for: string | null;
  error_summary: Record<string, unknown>;
  uploaded_by: string | null;
  processed_by: string | null;
  reversed_by: string | null;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
  reversed_at: string | null;
  items: VrpImportItem[];
  errors: VrpImportError[];
};

export type VrpSchedule = {
  organization_id: string;
  frequency: "DAILY" | "WEEKLY" | "MONTHLY" | "MANUAL";
  processing_time: string;
  timezone: string;
  weekly_day: string;
  monthly_rule: string;
  auto_process: boolean;
  unknown_product_policy: "STOP" | "PROCESS_KNOWN" | "CREATE_REVIEW";
  negative_stock_policy: "ALLOW_WITH_WARNING" | "STOP";
  overlap_policy: "BLOCK";
  next_run_at: string | null;
  last_run_at: string | null;
  updated_by: string | null;
  updated_at: string;
};

export type VrpScheduleUpdate = Pick<
  VrpSchedule,
  | "frequency"
  | "processing_time"
  | "timezone"
  | "weekly_day"
  | "monthly_rule"
  | "auto_process"
  | "unknown_product_policy"
  | "negative_stock_policy"
  | "overlap_policy"
>;

export type EmailInboundSettings = {
  organization_id: string;
  inbound_address: string;
  enabled: boolean;
  auto_process: boolean;
  allowed_sender_domains: string[];
  webhook_configured: boolean;
  imap_enabled: boolean;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
};

export type EmailInboundSettingsUpdate = Pick<
  EmailInboundSettings,
  "enabled" | "auto_process" | "allowed_sender_domains"
>;

export type InboundEmailAttachment = {
  id: string;
  position: number;
  filename: string;
  declared_content_type: string | null;
  size_bytes: number;
  content_sha256: string;
  status: string;
  document_id: string | null;
  rejection_code: string | null;
  created_at: string;
};

export type InboundEmail = {
  id: string;
  organization_id: string;
  provider: string;
  provider_message_id: string;
  sender: string;
  recipients: string[];
  subject: string;
  status: string;
  attachment_count: number;
  accepted_count: number;
  duplicate_count: number;
  rejected_count: number;
  error_summary: { codes?: string[] };
  received_at: string;
  processed_at: string | null;
  created_at: string;
  updated_at: string;
  attachments: InboundEmailAttachment[];
};

export type PluginPermission = {
  permission: string;
  granted: boolean;
  granted_by: string | null;
  granted_at: string | null;
};

export type PluginSetting = {
  key: string;
  value: unknown;
  is_secret: boolean;
  updated_at: string;
};

export type PluginItem = {
  id: string;
  organization_id: string;
  plugin_key: string;
  name: string;
  description: string;
  status: string;
  active_version: string;
  api_version: string;
  is_builtin: boolean;
  manifest: {
    id: string;
    name: string;
    description: string;
    version: string;
    api_version: string;
    entrypoint: string;
    permissions: string[];
    subscribes: string[];
    emits: string[];
    settings_schema: {
      properties?: Record<
        string,
        { type?: string; default?: unknown; description?: string }
      >;
    };
  };
  permissions: PluginPermission[];
  settings: PluginSetting[];
  installed_at: string;
  updated_at: string;
  enabled_at: string | null;
  disabled_at: string | null;
};

export type PluginJob = {
  id: string;
  organization_id: string;
  plugin_id: string;
  plugin_version: string;
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  status: string;
  attempts: number;
  max_attempts: number;
  result: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  correlation_id: string;
  next_attempt_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PluginOverview = {
  plugins: PluginItem[];
  job_counts: Record<string, number>;
};

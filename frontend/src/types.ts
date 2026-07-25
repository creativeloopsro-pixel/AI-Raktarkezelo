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

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


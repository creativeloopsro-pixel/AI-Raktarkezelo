from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    organization_slug: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class UserSummary(ApiModel):
    id: str
    organization_id: str
    email: str
    full_name: str
    role: str
    role_ids: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    mfa_enabled: bool = False
    mfa_required: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserSummary
    mfa_setup_required: bool = False


class MfaChallengeResponse(BaseModel):
    mfa_required: bool = True
    challenge_token: str
    expires_in: int


class MfaVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=32)
    code: str = Field(min_length=6, max_length=24)


class MfaSetupRead(BaseModel):
    secret: str
    otpauth_uri: str


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class MfaConfirmResponse(BaseModel):
    recovery_codes: list[str]
    session: TokenResponse


class MfaDisableRequest(BaseModel):
    password: str = Field(min_length=8, max_length=200)
    code: str = Field(min_length=6, max_length=24)


class RefreshSessionRead(ApiModel):
    id: str
    user_id: str
    organization_id: str
    mfa_verified: bool
    user_agent: str
    ip_address: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revoke_reason: str | None
    current: bool = False


class PermissionRead(ApiModel):
    id: str
    code: str
    name: str
    description: str
    category: str


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,79}$")
    description: str = Field(default="", max_length=500)
    permission_codes: list[str] = Field(min_length=1, max_length=100)


class RoleUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    permission_codes: list[str] = Field(min_length=1, max_length=100)


class RoleRead(ApiModel):
    id: str
    organization_id: str
    name: str
    slug: str
    description: str
    is_system: bool
    permission_codes: list[str] = Field(default_factory=list)
    user_count: int = 0
    created_at: datetime
    updated_at: datetime


class UserAdminCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=200)
    role_ids: list[str] = Field(min_length=1, max_length=20)


class UserAdminUpdate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role_ids: list[str] = Field(min_length=1, max_length=20)
    is_active: bool
    password: str | None = Field(default=None, min_length=12, max_length=200)


class UserAdminRead(UserSummary):
    is_active: bool
    created_at: datetime


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    scopes: list[str] = Field(min_length=1, max_length=100)
    expires_at: datetime | None = None


class ApiTokenRead(ApiModel):
    id: str
    name: str
    token_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None


class ApiTokenCreated(BaseModel):
    token: ApiTokenRead
    raw_token: str


class ResumableUploadCreate(BaseModel):
    client_upload_id: str = Field(min_length=8, max_length=80)
    target_type: Literal["DOCUMENT", "VRP"]
    filename: str = Field(min_length=1, max_length=255)
    declared_content_type: str | None = Field(default=None, max_length=160)
    total_size: int = Field(gt=0)
    file_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class ResumableUploadRead(ApiModel):
    id: str
    organization_id: str
    created_by: str
    client_upload_id: str
    target_type: str
    filename: str
    declared_content_type: str | None
    total_size: int
    chunk_size: int
    total_chunks: int
    received_chunks: list[int]
    file_sha256: str | None
    upload_metadata: dict
    status: str
    result_entity_type: str | None
    result_entity_id: str | None
    last_error_code: str | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None


class ResumableUploadComplete(BaseModel):
    file_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ResumableUploadResult(BaseModel):
    upload: ResumableUploadRead
    entity_type: str
    entity_id: str


class PackagingUnitInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    multiplier_to_base_unit: Decimal = Field(gt=0, decimal_places=3)


class BarcodeInput(BaseModel):
    code: str = Field(min_length=3, max_length=128)
    symbology: str = Field(default="EAN_13", max_length=32)
    is_primary: bool = False
    packaging_unit_name: str | None = Field(default=None, max_length=80)


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    internal_sku: str = Field(min_length=1, max_length=80)
    base_unit: str = Field(default="piece", max_length=24)
    min_stock: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=3)
    packaging_units: list[PackagingUnitInput] = Field(default_factory=list)
    barcodes: list[BarcodeInput] = Field(default_factory=list)


class PackagingUnitRead(ApiModel):
    id: str
    name: str
    multiplier_to_base_unit: Decimal


class BarcodeRead(ApiModel):
    id: str
    code: str
    symbology: str
    is_primary: bool
    packaging_unit_id: str | None


class ProductRead(ApiModel):
    id: str
    name: str
    internal_sku: str
    base_unit: str
    status: str
    min_stock: Decimal
    version: int
    packaging_units: list[PackagingUnitRead]
    barcodes: list[BarcodeRead]
    created_at: datetime
    updated_at: datetime


class StockOperation(BaseModel):
    product_id: str
    quantity: Decimal = Field(gt=0, decimal_places=3)
    source_id: str = Field(min_length=1, max_length=128)
    reason: str | None = Field(default=None, max_length=500)


class StockCorrection(BaseModel):
    product_id: str
    counted_quantity: Decimal = Field(ge=0, decimal_places=3)
    reason: str = Field(min_length=3, max_length=500)


class ReversalRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class StockMovementRead(ApiModel):
    id: str
    organization_id: str
    product_id: str
    movement_type: str
    quantity_delta: Decimal
    source_type: str
    source_id: str
    idempotency_key: str
    correlation_id: str
    created_by: str | None
    reverses_movement_id: str | None
    details: dict
    created_at: datetime


class StockBalanceRead(BaseModel):
    product_id: str
    product_name: str
    internal_sku: str
    quantity: Decimal
    min_stock: Decimal
    updated_at: datetime | None


class StockProductDetail(BaseModel):
    balance: StockBalanceRead
    movements: list[StockMovementRead]


class InventorySessionCreate(BaseModel):
    client_session_id: str = Field(min_length=8, max_length=80)
    name: str = Field(default="Kézi leltár", min_length=2, max_length=160)


class InventoryCountCreate(BaseModel):
    product_id: str
    counted_quantity: Decimal = Field(ge=0, decimal_places=3)
    client_operation_id: str = Field(min_length=8, max_length=80)
    client_recorded_at: datetime
    client_expected_quantity: Decimal | None = Field(
        default=None, decimal_places=3
    )
    scanned_code: str | None = Field(default=None, max_length=128)
    reason_code: Literal[
        "PHYSICAL_COUNT",
        "DAMAGE",
        "SHRINKAGE",
        "DATA_ERROR",
        "OTHER",
    ] | None = None
    reason_note: str | None = Field(default=None, max_length=500)


class InventoryCompleteRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class InventoryCancelRequest(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


class InventoryRecentMovementRead(ApiModel):
    id: str
    movement_type: str
    quantity_delta: Decimal
    source_type: str
    created_at: datetime


class InventoryCountRead(ApiModel):
    id: str
    organization_id: str
    session_id: str
    product_id: str
    product_name: str
    internal_sku: str
    base_unit: str
    client_operation_id: str
    expected_quantity: Decimal
    client_expected_quantity: Decimal | None
    counted_quantity: Decimal
    quantity_difference: Decimal
    scanned_code: str | None
    reason_code: str | None
    reason_note: str | None
    recorded_by: str | None
    client_recorded_at: datetime
    created_at: datetime
    recent_movements: list[InventoryRecentMovementRead]


class InventoryCorrectionRead(ApiModel):
    id: str
    organization_id: str
    session_id: str
    count_id: str
    product_id: str
    product_name: str
    movement_id: str
    expected_quantity: Decimal
    counted_quantity: Decimal
    quantity_delta: Decimal
    reason_code: str
    reason_note: str | None
    created_by: str | None
    approved_by: str | None
    created_at: datetime


class InventorySessionRead(ApiModel):
    id: str
    organization_id: str
    client_session_id: str
    name: str
    status: str
    approval_required: bool
    started_by: str | None
    completed_by: str | None
    approved_by: str | None
    review_task_id: str | None
    completion_note: str | None
    started_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    updated_at: datetime
    counts: list[InventoryCountRead]
    corrections: list[InventoryCorrectionRead]


class VersionResponse(BaseModel):
    name: str
    version: str
    environment: str


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str


class DocumentRead(ApiModel):
    id: str
    organization_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256_hash: str
    status: str
    source_type: str
    document_type: str
    page_count: int
    validation_summary: dict
    uploaded_by: str | None
    created_at: datetime
    updated_at: datetime


class DocumentProcessingJobRead(ApiModel):
    id: str
    organization_id: str
    document_id: str
    job_type: str
    status: str
    attempts: int
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    next_attempt_at: datetime | None
    completed_at: datetime | None


class ReviewTaskRead(ApiModel):
    id: str
    organization_id: str
    task_type: str
    entity_type: str
    entity_id: str
    reason_code: str
    status: str
    context: dict
    assigned_to: str | None
    resolved_by: str | None
    resolution_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class ReviewTaskResolve(BaseModel):
    resolution_note: str = Field(min_length=3, max_length=1000)


class AiRequestRead(ApiModel):
    id: str
    provider: str
    model_name: str
    prompt_version: str
    status: str
    duration_ms: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class AiResultRead(ApiModel):
    id: str
    overall_confidence: Decimal
    model_version: str | None
    created_at: datetime
    request: AiRequestRead


class ReceiptProductSummary(ApiModel):
    id: str
    name: str
    internal_sku: str
    base_unit: str


class ReceiptPackagingSummary(ApiModel):
    id: str
    name: str
    multiplier_to_base_unit: Decimal


class GoodsReceiptItemRead(ApiModel):
    id: str
    line_number: int
    description: str
    barcode: str | None
    quantity: Decimal
    unit: str
    confidence: Decimal
    source_page: int
    matched_product_id: str | None
    packaging_unit_id: str | None
    conversion_factor: Decimal | None
    base_quantity: Decimal | None
    match_method: str | None
    status: str
    validation_issues: list[str]
    matched_product: ReceiptProductSummary | None
    packaging_unit: ReceiptPackagingSummary | None


class GoodsReceiptDraftRead(ApiModel):
    id: str
    organization_id: str
    document_id: str
    document_number: str | None
    document_date: date | None
    status: str
    validation_issues: list[str]
    confirmed_by: str | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    ai_result: AiResultRead
    items: list[GoodsReceiptItemRead]


class GoodsReceiptItemUpdate(BaseModel):
    product_id: str
    packaging_unit_id: str | None = None
    quantity: Decimal = Field(gt=0, decimal_places=3)


class GoodsReceiptReverse(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class VrpImportItemRead(ApiModel):
    id: str
    line_number: int
    external_product_id: str | None
    external_name: str
    quantity: Decimal
    unit: str
    matched_product_id: str | None
    conversion_factor: Decimal | None
    base_quantity: Decimal | None
    match_method: str | None
    status: str
    validation_issues: list[str]
    matched_product: ReceiptProductSummary | None


class VrpImportErrorRead(ApiModel):
    id: str
    line_number: int | None
    error_code: str
    message: str
    raw_row: dict


class VrpImportBatchRead(ApiModel):
    id: str
    organization_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    file_hash: str
    canonical_items_hash: str
    parser_version: str
    external_report_id: str | None
    period_start: date
    period_end: date
    status: str
    scheduled_for: datetime | None
    error_summary: dict
    uploaded_by: str | None
    processed_by: str | None
    reversed_by: str | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None
    reversed_at: datetime | None
    items: list[VrpImportItemRead]
    errors: list[VrpImportErrorRead]


class VrpImportItemUpdate(BaseModel):
    product_id: str
    conversion_factor: Decimal = Field(gt=0, max_digits=18, decimal_places=3)


class VrpImportReverse(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class VrpScheduleUpdate(BaseModel):
    frequency: Literal["DAILY", "WEEKLY", "MONTHLY", "MANUAL"]
    processing_time: time
    timezone: str = Field(min_length=1, max_length=80)
    weekly_day: Literal[
        "MONDAY",
        "TUESDAY",
        "WEDNESDAY",
        "THURSDAY",
        "FRIDAY",
        "SATURDAY",
        "SUNDAY",
    ] = "SUNDAY"
    monthly_rule: str = Field(default="LAST_DAY", pattern=r"^(LAST_DAY|[1-9]|1\d|2[0-8])$")
    auto_process: bool = False
    unknown_product_policy: Literal[
        "STOP", "PROCESS_KNOWN", "CREATE_REVIEW"
    ] = "STOP"
    negative_stock_policy: Literal["ALLOW_WITH_WARNING", "STOP"] = (
        "ALLOW_WITH_WARNING"
    )
    overlap_policy: Literal["BLOCK"] = "BLOCK"


class VrpScheduleRead(ApiModel):
    organization_id: str
    frequency: str
    processing_time: time
    timezone: str
    weekly_day: str
    monthly_rule: str
    auto_process: bool
    unknown_product_policy: str
    negative_stock_policy: str
    overlap_policy: str
    next_run_at: datetime | None
    last_run_at: datetime | None
    updated_by: str | None
    updated_at: datetime


class InventoryReportScheduleUpdate(BaseModel):
    enabled: bool = False
    frequency: Literal["DAILY", "WEEKLY", "MONTHLY"] = "WEEKLY"
    generation_time: time
    timezone: str = Field(min_length=1, max_length=80)
    weekly_day: Literal[
        "MONDAY",
        "TUESDAY",
        "WEDNESDAY",
        "THURSDAY",
        "FRIDAY",
        "SATURDAY",
        "SUNDAY",
    ] = "MONDAY"
    monthly_rule: str = Field(
        default="LAST_DAY",
        pattern=r"^(LAST_DAY|[1-9]|1\d|2[0-8])$",
    )


class InventoryReportScheduleRead(ApiModel):
    organization_id: str
    enabled: bool
    frequency: str
    generation_time: time
    timezone: str
    weekly_day: str
    monthly_rule: str
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_document_id: str | None
    last_error_message: str | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


class EmailInboundSettingsUpdate(BaseModel):
    enabled: bool = True
    auto_process: bool = True
    allowed_sender_domains: list[str] = Field(default_factory=list, max_length=100)


class EmailInboundSettingsRead(ApiModel):
    organization_id: str
    inbound_address: str
    enabled: bool
    auto_process: bool
    allowed_sender_domains: list[str]
    webhook_configured: bool
    imap_enabled: bool
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


class AiSettingsUpdate(BaseModel):
    api_key: str = Field(min_length=8, max_length=2048)

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError("Az API-kulcs legalább 8 karakter legyen.")
        if any(character.isspace() for character in normalized):
            raise ValueError("Az API-kulcs nem tartalmazhat szóközt.")
        return normalized


class AiSettingsRead(BaseModel):
    organization_id: str
    provider: str
    base_url: str
    model: str
    api_key_configured: bool
    api_key_source: Literal["organization", "environment", "none"]
    api_key_hint: str | None
    provider_enabled: bool
    updated_by: str | None
    updated_at: datetime | None


class InboundEmailAttachmentRead(ApiModel):
    id: str
    position: int
    filename: str
    declared_content_type: str | None
    size_bytes: int
    content_sha256: str
    status: str
    document_id: str | None
    rejection_code: str | None
    created_at: datetime


class InboundEmailRead(ApiModel):
    id: str
    organization_id: str
    provider: str
    provider_message_id: str
    sender: str
    recipients: list[str]
    subject: str
    status: str
    attachment_count: int
    accepted_count: int
    duplicate_count: int
    rejected_count: int
    error_summary: dict
    received_at: datetime
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    attachments: list[InboundEmailAttachmentRead]


class InboundEmailReceipt(BaseModel):
    message: InboundEmailRead
    duplicate: bool
    queued_job_count: int


class PluginPermissionRead(ApiModel):
    permission: str
    granted: bool
    granted_by: str | None
    granted_at: datetime | None


class PluginSettingRead(BaseModel):
    key: str
    value: object
    is_secret: bool
    updated_at: datetime


class PluginRead(BaseModel):
    id: str
    organization_id: str
    plugin_key: str
    name: str
    description: str
    status: str
    active_version: str
    api_version: str
    is_builtin: bool
    manifest: dict
    permissions: list[PluginPermissionRead]
    settings: list[PluginSettingRead]
    installed_at: datetime
    updated_at: datetime
    enabled_at: datetime | None
    disabled_at: datetime | None


class PluginPermissionUpdate(BaseModel):
    granted_permissions: list[str] = Field(default_factory=list, max_length=50)


class PluginSettingsUpdate(BaseModel):
    values: dict[str, object] = Field(default_factory=dict)


class PluginJobRead(ApiModel):
    id: str
    organization_id: str
    plugin_id: str
    plugin_version: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    status: str
    attempts: int
    max_attempts: int
    result: dict
    error_code: str | None
    error_message: str | None
    correlation_id: str
    next_attempt_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PluginOverview(BaseModel):
    plugins: list[PluginRead]
    job_counts: dict[str, int]

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    DocumentProcessingJob,
    OutboxEvent,
    PluginJob,
    ReviewTask,
    User,
)
from app.plugins.manifest import PluginManifest
from app.plugins.registry import PluginRegistry
from app.services.documents import DocumentService
from app.services.plugin_runtime import PluginRuntime
from app.services.plugins import PluginEnableError, PluginService
from app.storage import LocalObjectStorage
from app.virus_scan import DisabledVirusScanner


def pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(output)
    return output.getvalue()


def plugin_settings(tmp_path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        object_store_backend="local",
        object_store_local_path=str(tmp_path / "objects"),
        plugin_dispatch_batch_size=100,
        plugin_rate_limit_per_minute=120,
        **overrides,
    )


def test_manifest_rejects_unknown_permission_and_invalid_event() -> None:
    with pytest.raises(ValueError):
        PluginManifest(
            id="invalid-permission",
            name="Invalid",
            version="1.0.0",
            permissions=["database.superuser"],
        )
    with pytest.raises(ValueError):
        PluginManifest(
            id="invalid-event",
            name="Invalid",
            version="1.0.0",
            subscribes=["Not An Event"],
        )


def test_builtin_plugins_get_inactive_service_accounts_and_declared_permissions(
    session: Session, seeded, tmp_path
) -> None:
    organization, _, _ = seeded
    service = PluginService(session, settings=plugin_settings(tmp_path))

    plugins = service.ensure_builtin_plugins(organization.id)

    assert {plugin.plugin_key for plugin in plugins} == {
        "ai-goods-receipt",
        "vrp-import",
        "email-intake",
        "sample-stock-audit",
    }
    enabled = {
        plugin.plugin_key for plugin in plugins if plugin.status == "ENABLED"
    }
    assert enabled == {"ai-goods-receipt", "vrp-import", "email-intake"}
    for plugin in service.list_plugins(organization.id):
        assert plugin.service_user.role == "plugin_service"
        assert plugin.service_user.is_active is False
        assert {item.permission for item in plugin.permissions} == set(
            service.manifest_for(plugin).permissions
        )
        assert all(item.granted for item in plugin.permissions)


def test_custom_plugin_requires_explicit_permissions_before_enable(
    session: Session, seeded, tmp_path
) -> None:
    _, admin, _ = seeded
    registry = PluginRegistry()

    @registry.handler("custom-observer", "stock.changed")
    def handler(_context, _event):
        return {"ok": True}

    service = PluginService(
        session,
        settings=plugin_settings(tmp_path),
        registry=registry,
    )
    plugin = service.install_manifest(
        user=admin,
        manifest_payload={
            "id": "custom-observer",
            "name": "Custom observer",
            "version": "1.0.0",
            "api_version": "1",
            "permissions": ["products.read"],
            "subscribes": ["stock.changed"],
            "emits": [],
        },
        correlation_id="plugin-install-1",
    )

    assert plugin.status == "DISABLED"
    assert plugin.permissions[0].granted is False
    with pytest.raises(PluginEnableError):
        service.enable(
            user=admin,
            plugin_id=plugin.id,
            correlation_id="plugin-enable-blocked",
        )

    plugin = service.set_permissions(
        user=admin,
        plugin_id=plugin.id,
        granted_permissions=["products.read"],
        correlation_id="plugin-permissions-1",
    )
    assert plugin.permissions[0].granted is True
    plugin = service.enable(
        user=admin,
        plugin_id=plugin.id,
        correlation_id="plugin-enable-1",
    )
    assert plugin.status == "ENABLED"


def test_outbox_dispatch_is_idempotent_and_sample_handler_is_permission_scoped(
    session: Session, seeded, tmp_path
) -> None:
    organization, admin, product = seeded
    settings = plugin_settings(tmp_path)
    service = PluginService(session, settings=settings)
    service.ensure_builtin_plugins(organization.id)
    sample = service.get_by_key(organization.id, "sample-stock-audit")
    service.enable(
        user=admin,
        plugin_id=sample.id,
        correlation_id="sample-enable",
    )
    event = OutboxEvent(
        organization_id=organization.id,
        event_type="stock.changed",
        aggregate_type="product",
        aggregate_id=product.id,
        payload={
            "movement_id": "movement-1",
            "quantity_delta": "3",
            "resulting_quantity": "3",
            "correlation_id": "stock-event-1",
        },
    )
    session.add(event)
    session.commit()
    runtime = PluginRuntime(session, settings=settings)

    job_ids = runtime.create_jobs_from_outbox()

    assert len(job_ids) == 1
    session.refresh(event)
    assert event.published_at is not None
    job = runtime.run_job(job_ids[0])
    assert job is not None
    assert job.status == "COMPLETED"
    assert job.result["status"] == "OBSERVED"
    emitted = session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.event_type == "sample.stock.observed"
        )
    )
    assert emitted is not None
    assert emitted.payload["product_name"] == product.name

    runtime.create_jobs_from_outbox()
    assert session.scalar(select(func.count()).select_from(PluginJob)) == 1


def test_ai_goods_receipt_plugin_queues_only_assigned_automatic_document(
    session: Session, seeded, tmp_path, monkeypatch
) -> None:
    organization, _, _ = seeded
    settings = plugin_settings(tmp_path)
    service = PluginService(session, settings=settings)
    service.ensure_builtin_plugins(organization.id)
    monkeypatch.setattr(
        "app.plugins.sdk.dispatch_document_job", lambda _job_id: True
    )
    document_service = DocumentService(
        session,
        storage=LocalObjectStorage(tmp_path / "documents"),
        scanner=DisabledVirusScanner(),
        settings=settings,
    )
    document = document_service.ingest(
        organization_id=organization.id,
        stream=BytesIO(pdf_bytes()),
        filename="email-receipt.pdf",
        declared_content_type="application/pdf",
        source_type="EMAIL_ATTACHMENT",
        correlation_id="email-plugin-1",
        source_metadata={"auto_process_requested": True},
    )
    runtime = PluginRuntime(session, settings=settings)

    job_ids = runtime.create_jobs_from_outbox()
    ai_job = session.scalar(
        select(PluginJob).where(
            PluginJob.id.in_(job_ids),
            PluginJob.event_type == "document.uploaded",
        )
    )
    assert ai_job is not None
    completed = runtime.run_job(ai_job.id)

    assert completed is not None
    assert completed.status == "COMPLETED"
    assert completed.result["status"] == "QUEUED"
    session.refresh(document)
    assert document.status == "QUEUED"
    assert session.scalar(select(func.count()).select_from(DocumentProcessingJob)) == 1


def test_plugin_failure_is_isolated_and_creates_review_after_last_attempt(
    session: Session, seeded, tmp_path
) -> None:
    organization, admin, product = seeded
    registry = PluginRegistry()

    @registry.handler("failing-plugin", "stock.changed")
    def failing_handler(_context, _event):
        raise RuntimeError("controlled test failure")

    settings = plugin_settings(tmp_path, plugin_max_retries=1)
    service = PluginService(session, settings=settings, registry=registry)
    plugin = service.install_manifest(
        user=admin,
        manifest_payload={
            "id": "failing-plugin",
            "name": "Failing plugin",
            "version": "1.0.0",
            "api_version": "1",
            "permissions": [],
            "subscribes": ["stock.changed"],
            "emits": [],
        },
        correlation_id="failing-install",
    )
    plugin = service.enable(
        user=admin,
        plugin_id=plugin.id,
        correlation_id="failing-enable",
    )
    event = OutboxEvent(
        organization_id=organization.id,
        event_type="stock.changed",
        aggregate_type="product",
        aggregate_id=product.id,
        payload={"correlation_id": "failing-event"},
    )
    session.add(event)
    session.commit()
    runtime = PluginRuntime(session, settings=settings, registry=registry)
    job_id = next(
        job_id
        for job_id in runtime.create_jobs_from_outbox()
        if session.get(PluginJob, job_id).plugin_id == plugin.id
    )

    failed = runtime.run_job(job_id)

    assert failed is not None
    assert failed.status == "FAILED"
    assert failed.error_code == "plugin_handler_failed"
    review = session.scalar(
        select(ReviewTask).where(
            ReviewTask.entity_type == "plugin_job",
            ReviewTask.entity_id == failed.id,
        )
    )
    assert review is not None
    failure_event = session.scalar(
        select(OutboxEvent).where(OutboxEvent.event_type == "plugin.failed")
    )
    assert failure_event is not None


def test_plugin_api_lists_builtins_and_admin_can_toggle_sample(
    client, session: Session, seeded
) -> None:
    organization, _, _ = seeded
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.get("/api/v1/plugins", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["plugins"]) == 4
    sample = next(
        plugin
        for plugin in body["plugins"]
        if plugin["plugin_key"] == "sample-stock-audit"
    )
    assert sample["status"] == "DISABLED"
    enabled = client.post(
        f"/api/v1/plugins/{sample['id']}/enable", headers=headers
    )
    assert enabled.status_code == 200
    assert enabled.json()["status"] == "ENABLED"
    disabled = client.post(
        f"/api/v1/plugins/{sample['id']}/disable", headers=headers
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"
    assert session.scalar(
        select(func.count())
        .select_from(User)
        .where(
            User.organization_id == organization.id,
            User.role == "plugin_service",
        )
    ) == 4


def test_plugin_api_masks_secret_settings(client, seeded) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    installed = client.post(
        "/api/v1/plugins/install",
        headers=headers,
        json={
            "id": "secret-settings",
            "name": "Secret settings",
            "version": "1.0.0",
            "api_version": "1",
            "permissions": [],
            "subscribes": [],
            "emits": [],
            "settings_schema": {
                "type": "object",
                "properties": {
                    "api_key": {"type": "string", "writeOnly": True}
                },
                "additionalProperties": False,
            },
        },
    )
    assert installed.status_code == 201
    plugin_id = installed.json()["id"]

    updated = client.put(
        f"/api/v1/plugins/{plugin_id}/settings",
        headers=headers,
        json={"values": {"api_key": "do-not-return-this"}},
    )

    assert updated.status_code == 200
    assert updated.json()["settings"] == [
        {
            "key": "api_key",
            "value": "********",
            "is_secret": True,
            "updated_at": updated.json()["settings"][0]["updated_at"],
        }
    ]


def test_disabled_vrp_plugin_blocks_mutating_vrp_api(client, seeded) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    overview = client.get("/api/v1/plugins", headers=headers).json()
    vrp = next(
        plugin
        for plugin in overview["plugins"]
        if plugin["plugin_key"] == "vrp-import"
    )
    disabled = client.post(
        f"/api/v1/plugins/{vrp['id']}/disable",
        headers=headers,
    )
    assert disabled.status_code == 200

    upload = client.post(
        "/api/v1/vrp/imports",
        headers=headers,
        files={"file": ("blocked.csv", b"name;quantity", "text/csv")},
        data={"period_start": "2026-07-01", "period_end": "2026-07-01"},
    )

    assert upload.status_code == 409
    assert upload.json()["detail"]["code"] == "vrp_plugin_disabled"

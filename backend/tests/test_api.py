def test_version_endpoint(client) -> None:
    response = client.get("/api/v1/system/version")
    assert response.status_code == 200
    assert response.json()["version"] == "0.10.0"


def test_login_product_creation_and_stock_correction(client) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["mfa_setup_required"] is False
    assert login_payload["user"]["mfa_required"] is False
    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    assert refresh_response.json()["refresh_token"] != login_payload["refresh_token"]

    reused_refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"]},
    )
    assert reused_refresh_response.status_code == 401

    replacement_login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "tesztbolt",
            "email": "admin@teszt.hu",
            "password": "Secret-1234!",
        },
    )
    assert replacement_login.status_code == 200
    token = replacement_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    product_response = client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "name": "Új termék",
            "internal_sku": "NEW-001",
            "base_unit": "piece",
            "min_stock": 3,
            "packaging_units": [{"name": "karton", "multiplier_to_base_unit": 12}],
            "barcodes": [
                {
                    "code": "5990000000001",
                    "symbology": "EAN_13",
                    "is_primary": True,
                    "packaging_unit_name": None,
                }
            ],
        },
    )
    assert product_response.status_code == 201
    product_id = product_response.json()["id"]

    correction_response = client.post(
        "/api/v1/stock/correct",
        headers={
            **headers,
            "Idempotency-Key": "api-correction-0001",
        },
        json={
            "product_id": product_id,
            "counted_quantity": 8,
            "reason": "Nyitókészlet",
        },
    )
    assert correction_response.status_code == 201
    assert correction_response.json()["quantity_delta"] == "8.000"

    stock_response = client.get("/api/v1/stock", headers=headers)
    assert stock_response.status_code == 200
    created_stock = next(item for item in stock_response.json() if item["product_id"] == product_id)
    assert created_stock["quantity"] == "8.000"

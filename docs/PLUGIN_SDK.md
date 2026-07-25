# Plugin SDK v1

Az AI Raktárkezelő pluginrendszere szervezetenként telepített, verziózott
manifestet, külön szolgáltatásfelhasználót, explicit jogosultságokat és tartós
eseményfuttatást használ. A plugin nem kap közvetlen adatbázis- vagy
fájlrendszer-hozzáférést; az üzleti műveleteket kizárólag a jogosultságot
ellenőrző `PluginContext` host API-n keresztül végezheti.

## Csomagszerkezet

```text
my-plugin/
├── manifest.json
├── README.md
├── backend/
│   ├── plugin.py
│   ├── handlers.py
│   ├── schemas.py
│   └── migrations/
├── frontend/
│   └── settings-panel/
└── tests/
```

A jelenlegi host a megbízható backend-csomaggal együtt telepített és a
`PluginRegistry` objektumban regisztrált handlereket futtatja. A manifest
adminisztrátori telepítése önmagában nem tölt be tetszőleges Python-kódot. Ez
szándékos biztonsági határ: a szerveroldali csomag kiadási és kódellenőrzési
folyamaton keresztül kerül a rendszerbe.

## Manifest

```json
{
  "id": "product-observer",
  "name": "Product observer",
  "description": "Készletváltozást figyelő mintaplugin.",
  "version": "1.0.0",
  "api_version": "1",
  "entrypoint": "product_observer.plugin:register",
  "permissions": ["products.read", "settings.read"],
  "subscribes": ["stock.changed"],
  "emits": ["sample.stock.observed"],
  "settings_schema": {
    "type": "object",
    "properties": {
      "include_product_name": {
        "type": "boolean",
        "default": true
      }
    },
    "additionalProperties": false
  }
}
```

Az `id` kisbetűs, kötőjeles azonosító, a `version` SemVer, az `api_version`
jelenleg `1`. Ismeretlen mező, jogosultság vagy hibás eseménynév esetén a host
elutasítja a manifestet. Verziófrissítéskor az új jogosultságok nincsenek
automatikusan megadva, a plugin pedig letiltott állapotba kerül.

## Jogosultságok

| Jogosultság | Host API / cél |
| --- | --- |
| `products.read` | `list_products()`, `get_product()` |
| `products.mapping.write` | külső termékpárosítás |
| `documents.read` | az eseményhez rendelt dokumentum metaadata |
| `documents.process` | a rendelt dokumentum AI-sorba állítása |
| `stock.movements.create` | készletmozgás a központi `StockService` rétegen át |
| `reports.generate` | riport-előállítási bővítési pont |
| `notifications.create` | értesítési bővítési pont |
| `settings.read` | saját pluginbeállítás olvasása |
| `settings.write` | saját pluginbeállítás módosítása |

Egy művelethez a manifest deklarációja és az adminisztrátor által megadott
engedély egyaránt szükséges. A dokumentumolvasás ezen felül az aktuális
eseményben hozzárendelt dokumentumra korlátozott. A szervezetazonosítót a host
adja, a plugin nem választhat másik tenantot.

## Handler és esemény

```python
from app.plugins.registry import plugin_registry
from app.plugins.sdk import PluginContext, PluginEvent


@plugin_registry.handler("product-observer", "stock.changed")
def handle_stock_changed(
    context: PluginContext,
    event: PluginEvent,
) -> dict:
    product = context.get_product(event.aggregate_id)
    if product is None:
        return {"status": "SKIPPED"}
    emitted_id = context.emit(
        "sample.stock.observed",
        {"product_id": product["id"], "product_name": product["name"]},
    )
    return {"status": "OBSERVED", "emitted_event_id": emitted_id}
```

A handler szinkron függvény, amely JSON-képes szótárat ad vissza. Az esemény
mezői: `id`, `type`, `aggregate_type`, `aggregate_id`, `payload` és
`correlation_id`. A kibocsátott eseményt a manifest `emits` listájában előre
deklarálni kell.

Az architektúra közös eseményei:

- `document.uploaded`
- `goods_receipt.confirmed`
- `vrp.import.ready`
- `vrp.import.completed`
- `stock.changed`
- `inventory.corrected`
- `schedule.triggered`
- `plugin.failed`

## Tartós futtatás

Az üzleti tranzakció outbox eseményt ír. A dispatcher az engedélyezett
előfizetőknek egyedi `plugin_jobs` rekordot készít, majd Redis/Dramatiq soron
futtatja. Az `(plugin_id, outbox_event_id)` adatbázis-egyediség és az
idempotenciakulcs megakadályozza a kettős feldolgozást.

A host konfigurálható timeoutot, percenkénti futási korlátot és exponenciális
újrapróbálást alkalmaz. A végleg hibás futás `PLUGIN_FAILURE` review feladatot,
auditbejegyzést és `plugin.failed` eseményt hoz létre. Egy plugin hibája nem
állítja le a többi előfizetőt.

## Telepítés és engedélyezés

1. A szervercsomag regisztrálja a handlereket.
2. Az adminisztrátor a **Pluginok** oldalon vagy a
   `POST /api/v1/plugins/install` végponton telepíti a manifestet.
3. Az adminisztrátor külön megadja a deklarált jogosultságokat.
4. A plugin csak minden szükséges jogosultság és minden handler meglétekor
   engedélyezhető.
5. A futások és hibák a **Pluginok** oldalon követhetők.

A teljes minta az `examples/plugins/product-observer` könyvtárban található. A
beépített `sample-stock-audit` ugyanezt a szerződést ténylegesen futtatja, de
alapértelmezetten letiltott.

## Konfiguráció

| Környezeti változó | Alapérték |
| --- | --- |
| `APP_PLUGIN_API_VERSION` | `1` |
| `APP_PLUGIN_JOB_TIMEOUT_SECONDS` | `60` |
| `APP_PLUGIN_MAX_RETRIES` | `3` |
| `APP_PLUGIN_DISPATCHER_POLL_SECONDS` | `5` |
| `APP_PLUGIN_DISPATCH_BATCH_SIZE` | `100` |
| `APP_PLUGIN_RATE_LIMIT_PER_MINUTE` | `120` |

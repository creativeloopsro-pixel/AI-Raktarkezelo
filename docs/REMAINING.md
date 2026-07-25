# Hátralévő architektúra-feladatok

Ez az élő lista kizárólag a PDF/DOCX architektúrából még hiányzó vagy részleges
tételeket tartalmazza. Egy tétel csak akkor kerül le a listáról, ha a
megvalósítás, az adatbázis-migráció, a szükséges API és felület, valamint az
automatizált ellenőrzés is elkészült.

## Riportok és értesítések

- Napi nem pénzügyi készlet-PDF létrehozása és archiválása.
- Riportlista, jogosultságvédett letöltés és kézi újragenerálás.
- Import-, készlet- és rendszerállapot-értesítések.

## Üzemeltetés és platformbiztonság

- Production reverse proxy HTTPS/TLS-sel, HSTS-sel és rate limitinggel.
- Prometheus metrikák, strukturált naplózás, Sentry/Grafana és riasztások.
- PostgreSQL/MinIO mentés, WAL stratégia, visszaállító parancsok és restore runbook.
- Redis hitelesítés és production secret-kezelési útmutató.
- GitHub Actions alapú lint-, teszt-, build- és migrációellenőrzés.

## Hátralévő minőségbiztosítás

- PostgreSQL-, Redis- és MinIO-integrációs tesztek.
- Teljes mobil E2E kódolvasási tesztek.
- Jogosultsági, webhook-replay, fájlfeltöltési és tenant-isolation biztonsági tesztek.
- Terheléses, worker-helyreállítási, backup- és restore-próbák.

## Pilot és finomhangolás

- Valós bizonylat- és VRP-mintákon végzett pilot.
- Confidence- és termékpárosítási küszöbök mérésalapú hangolása.
- Operátori visszajelzések alapján véglegesített mobil/desktop UX.

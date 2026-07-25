# Megvalósítási térkép

## 0.2.0 hatókör

Ez a kiadás az architektúra 23. fejezetének első fázisát és a második fázis
felületi alapjait, valamint a harmadik fázis dokumentumbeérkeztetési alapjait
fedi le.

| Architektúra-terület | Megvalósítás |
| --- | --- |
| Identity | Szervezethez kötött felhasználó, RBAC-alap, JWT és refresh session |
| Catalog | Termék, csomagolási egység, EAN/QR hozzárendelés |
| Inventory | Egyenleg, append-only mozgás, idempotencia, korrekció, visszavonás |
| Audit | Érzékeny műveletek append-only naplója correlation ID-val |
| Events | Tranzakcióban létrehozott outbox esemény |
| PWA | Reszponzív operátori felület, offline shell és telepíthető manifest |
| Documents | PDF- és képfeltöltés, oldalak, állapotok és idempotens feldolgozási feladat |
| Object storage | Helyi fejlesztői tároló és S3/MinIO adapter, backend-proxyzott letöltés |
| File security | Magic-byte MIME-ellenőrzés, méret- és oldallimit, SHA-256 duplikációvédelem, opcionális ClamAV |
| Review | Sérült vagy bizonytalan dokumentumok manuális felülvizsgálati sora |

## Modulhatárok

- Az API-réteg validálja a HTTP-bemenetet és ellenőrzi a jogosultságot.
- Készletet kizárólag a `StockService` módosíthat.
- A `StockService` ugyanabban a tranzakcióban írja a mozgást, az egyenleget,
  az auditbejegyzést és az outbox eseményt.
- Az AI és a későbbi pluginok nem kapnak közvetlen adatbázis-módosítási jogot.
- Minden üzleti lekérdezés kötelezően szervezetazonosítóval szűr.

## Következő tervezett kiadás

`0.3.0`: háttér-feldolgozó worker, OCR és a dokumentumokból kinyert mezők
AI-támogatott javaslatai, kötelező emberi jóváhagyással.

# Megvalósítási térkép

## 0.4.0 hatókör

Ez a kiadás az architektúra 23. fejezetének első fázisát és a második fázis
felületi alapjait, valamint a harmadik fázis dokumentumbeérkeztetési alapjait
és a negyedik fázis Ollama AI-folyamatát, továbbá az ötödik fázis
VRP-importját fedi le.

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
| AI Gateway | Ollama Cloud/helyi Ollama provider, timeout, circuit breaker, multimodális előfeldolgozás és szigorú Pydantic kimeneti séma |
| Worker | Dramatiq + Redis dispatch, adatbázisban tartós job, retry és stale-job helyreállítás |
| AI audit | Modell-, prompt-, token-, idő- és tool-call metaadat minden kinyeréshez |
| Product matching | Vonalkód, pontos név, lexikai egyezés és csomagolási konverzió |
| Goods receipt | Ember által javítható tervezet és tranzakciós, idempotens készletkönyvelés |
| VRP parser | CSV, XLSX és géppel olvasható PDF, verziózott többnyelvű oszlopfelismerés |
| VRP deduplikáció | Fájlhash, külső riportazonosító, kanonikus tételhash és adatbázis-egyediség |
| VRP időszakvédelem | Szervezeten belüli időszakátfedés blokkolása és review feladat |
| External mapping | Megerősített külső termékazonosító + konverziós faktor tartós tárolása |
| VRP scheduling | Kézi/napi/heti/havi időzónás futás, Dramatiq dispatch és stale recovery |
| VRP inventory | Közös batch source ID, tételenkénti idempotencia, tranzakciós könyvelés |
| VRP reversal | Adminisztrátori ellenmozgások, audit és nettó nulla készlethatás |
| VRP PWA | Feltöltés, importlista, tételes megfeleltetés, ütemezés és visszafordítás |

## Modulhatárok

- Az API-réteg validálja a HTTP-bemenetet és ellenőrzi a jogosultságot.
- Készletet kizárólag a `StockService` módosíthat.
- A `StockService` ugyanabban a tranzakcióban írja a mozgást, az egyenleget,
  az auditbejegyzést és az outbox eseményt.
- Az AI és a későbbi pluginok nem kapnak közvetlen adatbázis-módosítási jogot.
- Minden üzleti lekérdezés kötelezően szervezetazonosítóval szűr.

## Következő tervezett kiadás

`0.5.0`: dokumentáció szerinti e-mailes beérkeztetési csatorna, biztonságos
csatolmányfeldolgozás és a meglévő dokumentum/VRP folyamatokhoz irányítás.

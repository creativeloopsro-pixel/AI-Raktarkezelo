# Megvalósítási térkép

## 0.7.0 hatókör

Ez a kiadás az architektúra 23. fejezetének első fázisát és a második fázis
felületi alapjait, valamint a harmadik fázis dokumentumbeérkeztetési alapjait
és a negyedik fázis Ollama AI-folyamatát, továbbá az ötödik fázis
VRP-importját és a hatodik fázis e-mailes beérkeztetési csatornáját fedi le.
Ezen felül megvalósítja a hetedik fázis Plugin SDK-ját, közös
eseményszerződését és adminisztrációs felületét.
Megvalósítja továbbá a második fázis kamerás kódolvasását, dedikált
leltármenetét és offline számlálási sorát.

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
| E-mail routing | Szervezetenkénti titkos plus-címzés, engedélyezés és címrotáció |
| Inbound webhook | Nyers RFC 822 fogadás, HMAC-aláírás, időablakos replay-védelem |
| IMAP intake | Opcionális SSL/TLS worker, tartós átvétel előtti olvasatlanság |
| Attachment extraction | MIME-részek kinyerése, darab-/méretlimit és feladó-domain szabály |
| E-mail deduplikáció | Provider üzenetazonosító és dokumentum SHA-256 szerinti idempotencia |
| E-mail automation | Ellenőrzött melléklet automatikus dokumentum- és AI-sorba állítása |
| E-mail audit/PWA | Üzenet- és mellékletnapló, review feladat, reszponzív kezelőfelület |
| Plugin manifest | Szervezetenként telepített és verziózott, szigorúan validált SDK v1 szerződés |
| Plugin permissions | Explicit, adminisztrátor által kezelt engedélyek és külön szolgáltatásfelhasználó |
| Plugin host API | Tenant-határolt termék-, dokumentum-, készlet-, beállítás- és eseményfelület |
| Plugin runtime | Tartós outbox dispatcher, Redis worker, idempotens job, timeout, rate limit és retry |
| Plugin failure isolation | Végleges hibánál review feladat, audit és `plugin.failed` esemény |
| Plugin admin PWA | Manifesttelepítés, engedélyezés, jogosultságok, beállítások és futásnapló |
| Beépített pluginok | AI, VRP és e-mail közös szerződésre vezetve, működő készletfigyelő mintával |
| Kamerás kódolvasás | Natív `BarcodeDetector` EAN/UPC/Code 128/Data Matrix/QR támogatással és ZXing fallbackkel |
| Kézi leltár | Megszakítható leltármenet, tételes abszolút számlálás, okkód és korrekciós főkönyv |
| Offline számlálás | IndexedDB műveleti sor egyedi `client_operation_id` értékkel, szünettel és automatikus újraküldéssel |
| Leltárjóváhagyás | Konfigurálható eltérésküszöb, review feladat és admin/manager jóváhagyás |
| Mobil leltár PWA | Nagy számláló, +1/−1, kartonkód-szorzó, Bluetooth/kézi bevitel és offline állapot |

## Modulhatárok

- Az API-réteg validálja a HTTP-bemenetet és ellenőrzi a jogosultságot.
- Készletet kizárólag a `StockService` módosíthat.
- A `StockService` ugyanabban a tranzakcióban írja a mozgást, az egyenleget,
  az auditbejegyzést és az outbox eseményt.
- Az AI és a pluginok nem kapnak közvetlen adatbázis-módosítási jogot.
- A plugin üzleti hozzáférése a manifestben deklarált és külön megadott
  engedélyekre, a saját szervezetre és az eseményhez rendelt erőforrásra
  korlátozott.
- Minden üzleti lekérdezés kötelezően szervezetazonosítóval szűr.

## Következő tervezett kiadás

`0.8.0`: részletes szerepkör- és jogosultságmodell, felhasználó-adminisztráció,
adminisztrátori MFA és visszavonható API-tokenek.

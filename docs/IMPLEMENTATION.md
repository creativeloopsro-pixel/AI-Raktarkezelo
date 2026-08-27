# Megvalósítási térkép

## 0.17.3 hatókör

Ez a kiadás az architektúra 23. fejezetének első fázisát és a második fázis
felületi alapjait, valamint a harmadik fázis dokumentumbeérkeztetési alapjait
és a negyedik fázis Ollama AI-folyamatát, továbbá az ötödik fázis
VRP-importját és a hatodik fázis e-mailes beérkeztetési csatornáját fedi le.
Ezen felül megvalósítja a hetedik fázis Plugin SDK-ját, közös
eseményszerződését és adminisztrációs felületét.
Megvalósítja továbbá a második fázis kamerás kódolvasását, dedikált
leltármenetét és offline számlálási sorát.
Az identity réteg ebben a kiadásban részletes, szervezetenként kezelhető
szerepkör- és engedélymodellre bővült, opcionálisan kötelezővé tehető
adminisztrátori MFA-val, védett
munkamenetekkel és hatókörhöz kötött API-tokenekkel. A dokumentum- és
VRP-feltöltések IndexedDB-várólistát és darabolt, folytatható szerveroldali
feltöltési munkamenetet kaptak.
A Beállítások menüpont önálló, jogosultságtudatos konfigurációs központot kapott,
amely a fiók-, MFA-, kapcsolat- és verzióállapot mellett a ténylegesen elérhető
modulbeállításokhoz vezet.
Az áruátvétel mobilkamerás vonalkódolvasással, a folytatható
bizonylatfeltöltés pedig kérhető automatikus AI-feldolgozással és szigorúan
feltételes, idempotens készletkönyveléssel bővült.
A terméktörzs elsődleges EAN-mezője kamerás beolvasást, ellenőrzőszám-validációt
és azonnali, szkennelhető SVG-előnézetet kapott; a készletlistában minden termék
numerikus és vizuális elsődleges EAN-ja megjelenik.
Az önálló Termékek munkafelület közvetlen újtermék- és készlet-hozzáadást,
vonalkód alapján megjelenő mennyiség-megerősítést, valamint PDF-ből vagy
mobilkamerás szállítólevél-fotóból indítható automatikus AI-bevételezést biztosít.
A Beállítások oldalon az arra jogosult felhasználó szervezetenként külön Ollama
API-kulcsot adhat meg, cserélhet vagy törölhet. A kulcs titkosítva tárolódik,
soha nem olvasható vissza, és az AI-worker futás közben a feladathoz tartozó
szervezet beállítását használja.
A kiadás a kritikus és magas UX-kockázatokat is lezárja: valódi URL-útvonalakat,
ötcélú mobil navigációt, összevont dokumentummunkateret, kereshető és
mobilbarát jogosultságszerkesztést, kötelezőmező-validációt, valamint
készletkönyvelés előtti AI-összegzést és teljes bevételezés-visszavonást ad.
Az üzemeltetési réteg szervezetenként egyetlen, letölthető ZIP biztonsági
mentést tart fenn. A mentés kézzel indítható vagy napi, heti, illetve havi
rendben automatikusan futtatható. Az új sikeres archívum felülírja a korábbit,
a biztonsági hitelesítő adatok és titkos integrációs értékek pedig szándékosan
kimaradnak a felhasználó által letölthető exportból.
A letöltött ZIP adminisztrátori, interaktív munkamenetből visszaállítható.
A művelet formátum-, szervezet-, méret-, útvonal- és tömörítési ellenőrzést
végez, majd tranzakciósan lecseréli az üzleti adatokat és új objektumkulcsokra
állítja vissza a fájlokat. A jelenlegi identitás-, hitelesítési és titkos
integrációs adatok megmaradnak, a művelet előtt pedig automatikus biztonsági
pillanatkép készül.

| Architektúra-terület | Megvalósítás |
| --- | --- |
| Beállítási központ | Önálló, reszponzív, jogosultság alapján szűrt fiók-, biztonsági és modulnavigáció |
| Biztonsági mentés | Kézi és napi/heti/havi automatikus, szervezetenként felülírt ZIP, manifest, SHA-256, közvetlen letöltés és megerősített visszaállítás |
| AI hitelesítő adat | Szervezetszintű, titkosított Ollama API-kulcs, maszkolt állapot, auditált csere és törlés |
| Identity | Szervezethez kötött felhasználó, egyedi és rendszer-szerepkörök, finom engedélyek |
| MFA | Adminisztrátori TOTP, egyszer használható helyreállító kódok és MFA-val védett munkamenet |
| Sessions | Forgó refresh token, token-család újrahasználatának felismerése, eszközlista és visszavonás |
| API token | Egyszer megjelenített titok, hash-elt tárolás, felhasználói engedélyekre szűkített scope és visszavonás |
| Catalog | Termék, csomagolási egység, EAN/QR hozzárendelés |
| Termékek PWA | Kereshető termékkatalógus, vizuális és numerikus EAN, közvetlen termék- és készlet-hozzáadás |
| Segített bevételezés | Vonalkódos termékazonosítás aktuális/hozzáadott/eredmény készlettel, valamint fotózható szállítólevél AI-feldolgozással |
| UX navigáció | Mélylinkelhető böngészőútvonalak, előzménykezelés, ötcélú mobil alsó sáv és „Több” panel |
| Jogosultság UX | Kereshető harmonikák, kijelölésszámláló, scope-sablonok és rögzített mentési művelet |
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
| Goods receipt | Ember által javítható tervezet, könyvelés előtti AI-összegzés, tranzakciós/idempotens készletkönyvelés és teljes ellenmozgásos visszavonás |
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
| Kamerás kódolvasás | Natív `BarcodeDetector` EAN/UPC/Code 128/Data Matrix/QR támogatással, ZXing fallbackkel a leltárban és a kézi bevételezésben |
| Kézi leltár | Megszakítható leltármenet, tételes abszolút számlálás, okkód és korrekciós főkönyv |
| Offline számlálás | IndexedDB műveleti sor egyedi `client_operation_id` értékkel, szünettel és automatikus újraküldéssel |
| Offline fájlfeltöltés | IndexedDB Blob-várólista, kliens- és darabhash, szünet/folytatás és automatikus újraküldés |
| Resumable upload API | Tenant-, felhasználó- és célhatárolt munkamenet, idempotens darabok, végső SHA-256 és objektumtár |
| Leltárjóváhagyás | Konfigurálható eltérésküszöb, review feladat és admin/manager jóváhagyás |
| Mobil leltár PWA | Nagy számláló, +1/−1, kartonkód-szorzó, Bluetooth/kézi bevitel és offline állapot |
| Automatikus leltárriport | Szervezeti napi/heti/havi ütemezés, tartós retry feladat, többoldalas PDF, dokumentumtári archiválás és letöltés |

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

`0.15.0`: import-, készlet- és rendszerállapot-értesítések, valamint
riportértesítési csatornák.

# Változásnapló

A projekt minden kiadása a [Semantic Versioning](https://semver.org/) szabályait
követi. A fejlesztés alapdokumentuma az
`AI_Raktarkezelo_Teljes_Architektura.pdf` és annak DOCX-változata.

## [0.12.0] - 2026-07-26

### Hozzáadva

- Új **AI-kapcsolat** rész a Beállítások oldalon az Ollama API-kulcs
  megadásához, cseréjéhez és eltávolításához.
- Jogosultságtudatos `GET`, `PUT` és `DELETE /api/v1/ai/settings` végpontok
  szervezetszintű AI-hitelesítő adatok kezeléséhez.
- A dokumentumfeldolgozó worker feladatonként az adott szervezet AI-kulcsát
  használja, és szervezeti kulcs mentésekor automatikusan aktiválja az
  Ollama-szolgáltatót.

### Biztonság

- Az API-kulcs Fernet-titkosítással kerül az adatbázisba; a nyers érték sem
  válaszban, sem auditnaplóban, sem outbox-eseményben nem jelenik meg.
- A felület csak a kulcs maszkolt utolsó négy karakterét mutatja, és a mentett
  kulcsot soha nem tölti vissza a böngészőbe.
- Megtekintéshez `settings.read`, módosításhoz `settings.write` engedély
  szükséges; minden csere és törlés auditált.

## [0.11.0] - 2026-07-26

### Hozzáadva

- Önálló, kereshető **Termékek** munkafelület termék-, készlet-, minimum- és
  EAN-áttekintéssel, közvetlen **Új termék**, **Készlet hozzáadása** és
  **Szállítólevélről** műveletekkel.
- Kamera-, Bluetooth-olvasó- és kézi EAN-alapú készlet-hozzáadás. Találat után
  külön megerősítő ablak mutatja a jelenlegi, a hozzáadandó és az eredményként
  létrejövő készletet.
- A csomagolási egységhez rendelt vonalkód mennyisége automatikusan
  alapegységre váltódik a bevételezés előtt.
- PDF- vagy képfájlként feltölthető, telefonról közvetlenül fotózható
  szállítólevél, automatikusan kért AI-feldolgozással és készletkönyveléssel.
- Folyamatállapot a szállítólevél-felismeréshez; a legalább 98%-os, pontos
  termékegyezések automatikusan készletre kerülnek, a bizonytalan tételek
  ellenőrzési sorba jutnak.

### Módosítva

- A dokumentumfeltöltési kliens már külön továbbítja az automatikus feldolgozás
  és automatikus jóváhagyás kérését a backendnek.

## [0.10.0] - 2026-07-26

### Hozzáadva

- Kis kameraikon az **Elsődleges EAN-kód** mezőben; a mobilkamerával vagy
  Bluetooth-olvasóval érzékelt EAN automatikusan bekerül a mezőbe.
- Szabványos EAN-13 és EAN-8 vonalszerkezetből felépített, szkennelhető SVG
  előnézet a termék létrehozásakor.
- Minden készletlistában szereplő termék mellett megjelenik az elsődleges EAN
  vizuális vonalkódja és numerikus értéke.
- EAN-hossz- és ellenőrzőszám-validáció az új termékek elsődleges kódjánál,
  valamint EAN-alapú keresés a készletáttekintésben.

### Teljesítmény

- A termék- és készletműveleti dialógusok igény szerinti JavaScript-betöltést
  kaptak, így az új funkciók mellett is csökkent a kezdő alkalmazáscsomag mérete.

## [0.9.1] - 2026-07-26

### Javítva

- A mobilos feltöltési nézet rejtett fájl- és kameramezői már nem öröklik a
  látható űrlapmezők teljes szélességét, ezért megszűnt a vízszintes túlnyúlás.

## [0.9.0] - 2026-07-26

### Hozzáadva

- Mobilkamerás, natív `BarcodeDetector` és ZXing fallback alapú termékazonosítás
  az **Áru érkezett** bevételezési ablakban, Bluetooth- és kézi kódbevitellel.
- A termékvonalkódhoz rendelt karton- vagy más csomagolási egység automatikus
  alapegység-konverziója a kézi bevételezéskor.
- Közvetlen mobilos bizonylatfotó-készítés, valamint alapértelmezetten
  bekapcsolt „AI-felismerés és automatikus bevételezés” opció a megszakítható
  feltöltési sorban.
- A feltöltés metaadataival indított automatikus AI-feldolgozás bejövő
  bizonylatnál és szállítólevélnél.
- Magas biztonságú AI automatikus készletkönyvelés a központi `StockService`
  rétegen keresztül, teljes audit- és outbox-eseménnyel.

### Biztonság

- Automatikus könyvelés csak hibamentes tervezetnél, legalább 98%-os
  tételkonfidenciánál, vonalkódos vagy pontos névegyezésnél és megfelelő
  feltöltői jogosultságokkal történik.
- Bizonytalan, lexikai, ismeretlen vagy hibás tételek nem kerülnek automatikusan
  készletre; kézi ellenőrzésre vagy jóváhagyásra várnak.
- A dokumentumtól a készletmozgásig minden automatikus lépés idempotens,
  szervezethez kötött és auditált.
- Az Ollama strukturált JSON-sémás kimenete alapértelmezetten bekapcsolva.

### Konfiguráció

- Új `APP_AI_AUTO_CONFIRM_RECEIPTS` és
  `APP_AI_AUTO_CONFIRM_MIN_CONFIDENCE` beállítás az automatikus
  készletkönyveléshez.
- A helyi multimodális modell hideg betöltéséhez az alapértelmezett
  `APP_AI_TIMEOUT_SECONDS` érték 300 másodpercre emelve.

## [0.8.3] - 2026-07-26

### Javítva

- A Docker Compose alapértelmezett admin MFA-kényszere kikapcsolva, ezért az
  adminisztrátor MFA nélkül is a teljes dashboardot és a jogosultságai szerinti
  menüt kapja meg bejelentkezés után.
- A felhasználó-adminisztráció MFA-követelmény jelzése ugyanazt a szerveroldali
  beállítást követi, mint a belépés és a védett műveletek.
- Az MFA nélküli állapot feliratai az opcionális működést jelzik, nem kötelező
  beállítást.

### Biztonság

- Az MFA beállítása, a helyreállító kódok és a hitelesítő kódos későbbi belépés
  változatlanul elérhető. Az üzemeltető az
  `APP_MFA_ENFORCE_ADMIN=true` beállítással továbbra is kötelezővé teheti az
  admin MFA-t.

## [0.8.2] - 2026-07-26

### Módosítva

- A „Felhasználók és biztonság” oldalról eltávolítva az
  „Adminisztrátori MFA szükséges” figyelmeztető sáv és annak ismétlődő
  magyarázata.
- Az MFA beállítása, helyreállító kódjai és szerveroldali védelme változatlanul
  működik.

## [0.8.1] - 2026-07-26

### Hozzáadva

- Önálló, reszponzív Beállítások munkafelület fiók-, szerepkör-, MFA-,
  kapcsolat-, PWA- és rendszerverzió-állapottal.
- Jogosultság alapján szűrt konfigurációs kártyák a biztonsági, offline
  feltöltési, VRP-, e-mail- és pluginmodulokhoz.
- Közös frontend-verzióforrás, amelyet a belépési képernyő, az oldalsáv és a
  Beállítások oldal egyaránt használ.

### Javítva

- A Beállítások menüpont többé nem a Felhasználók és biztonság nézetre mutató,
  halvány ál-navigáció: saját aktív állapottal és tényleges céloldallal
  rendelkezik.
- A `?view=settings` PWA-mélyhivatkozás közvetlenül a Beállítások felületet
  nyitja meg.
- Mobilnézetben is megjelent a Beállítások gyorsművelet, a gyorsműveleti sáv
  pedig tetszőleges számú jogosultságfüggő gombbal vízszintesen görgethető.

## [0.8.0] - 2026-07-25

### Hozzáadva

- Szervezetenkénti `roles`, `permissions`, `role_permissions` és `user_roles`
  adatmodell öt beépített szerepkörrel, egyedi szerepkörökkel és csoportosított
  engedélykatalógussal.
- Felhasználó-adminisztráció létrehozással, módosítással, aktiválással,
  deaktiválással, jelszócserével és több szerepkör hozzárendelésével.
- Engedélykód-alapú backend- és frontend-hozzáférés minden meglévő üzleti
  modulhoz; a korábbi szerepkör-ellenőrzések finom szemcsézettségű szabályokra
  cserélve.
- Adminisztrátori TOTP MFA beállítási folyamattal, egyszer használható
  helyreállító kódokkal és kétlépcsős bejelentkezési felülettel.
- Eszköz- és munkamenetlista IP- és user-agent metaadattal, egyedi és összes
  többi munkamenet visszavonásával.
- Forgó refresh session token-családokkal és a már felhasznált refresh token
  ismételt használatakor teljes család-visszavonással.
- Csak egyszer megjelenített, szerveren HMAC-hashként tárolt, lejárathoz és
  engedély-scope-hoz kötött, azonnal visszavonható API-tokenek.
- IndexedDB-alapú dokumentum- és VRP-fájlvárólista offline tárolással,
  szüneteltetéssel, folytatással, újrapróbálással és kapcsolat-visszatéréskori
  automatikus szinkronnal.
- Tenant-, felhasználó- és célhatárolt feltöltési munkamenetek idempotens,
  SHA-256-tal ellenőrzött darabfeltöltéssel, teljes fájlhash-ellenőrzéssel és a
  meglévő dokumentum-/VRP-pipeline-ba történő biztonságos átadással.
- Nyolcadik Alembic-migráció, valamint MFA-, refresh-replay-, API-token-scope-,
  jogosultság-, tenant- és folytatható feltöltési automatizált tesztek.

### Biztonság

- Adminisztrátori üzleti művelet csak beállított és az aktuális munkamenetben
  ellenőrzött MFA-val végezhető; az MFA titka alkalmazásszintű titkosítással
  kerül tárolásra.
- A helyreállító kódok egyenként, hash-elve tárolódnak és sikeres használat után
  azonnal érvénytelenné válnak.
- A munkamenet visszavonása és a refresh-token újrahasználatának észlelése az
  adott sessionhöz tartozó access tokent is azonnal érvényteleníti.
- API-token nem kaphat a létrehozó felhasználóénál szélesebb hatókört, és minden
  API-hívásnál a szerepkör-engedély és a token-scope egyaránt érvényesül.
- A korábbi `plugin_service` fiókok migrációja és induláskori javítása
  kizárólag a szűkített `service` szerepkört rendeli hozzájuk.
- A feltöltési munkamenet nem olvasható vagy folytatható másik tenantból, másik
  felhasználóként vagy a szükséges célengedély nélkül.
- A kliens által deklarált fájltípus továbbra sem megbízható: az összeállított
  fájl a meglévő méret-, magic-byte-, vírus-, duplikáció- és üzleti
  validációkon halad át.

## [0.7.0] - 2026-07-25

### Hozzáadva

- Natív `BarcodeDetector` kamerás olvasó EAN-8, EAN-13, UPC-A, Code 128,
  Data Matrix és QR formátumokhoz, automatikus ZXing böngészős fallbackkel.
- Bluetooth olvasós és kézi kódbevitel, termékkeresés, valamint csomagolási
  egységhez tartozó vonalkód alapegység-szorzójának automatikus alkalmazása.
- Dedikált leltármenet `OPEN`, `PENDING_APPROVAL`, `COMPLETED` és `CANCELLED`
  állapotokkal, tételes abszolút számlálással és legfrissebb számlálat
  kiválasztásával.
- `inventory_sessions`, `inventory_counts` és `stock_corrections` táblák,
  szervezeti határokkal és kliensművelet-szintű adatbázis-idempotenciával.
- IndexedDB-alapú offline számlálási sor, helyi termék- és készletpillanatkép,
  szüneteltethető/folytatható szinkron és kapcsolat-visszatéréskor automatikus
  újraküldés.
- Mobil számláló nagy számmezővel, gyors +1/−1 műveletekkel, eltérésjelzéssel,
  kötelező okkóddal és utolsó bevételezés/VRP/korrekció előzményekkel.
- Tranzakciós leltárlezárás a központi `StockService` rétegen, külön
  korrekciós rekordokkal, auditnaplóval és `inventory.corrected` eseménnyel.
- Konfigurálható nagyeltérés-küszöb; raktárosi lezárásnál vezetői review
  feladat, admin/manager jóváhagyási és elutasítási folyamat.
- PWA gyorsindító a kézi leltárhoz és lusta kódbetöltés a mobil kezdőcsomag
  méretének védelméhez.
- Hetedik Alembic-migráció, leltár-idempotencia-, korrekció-, jóváhagyás-,
  tenant-isolation- és API-életciklustesztek.

### Biztonság

- A kliens által küldött szervezetazonosító nem használható; minden
  leltármenet, termék, kód, számlálás és korrekció a hitelesített tenanttal
  szűrt.
- A beszkennelt kódnak a kiválasztott termékhez kell tartoznia, a legfeljebb
  harmincnapos offline időbélyeg és az okkód szerveroldali validációt kap.
- Ismételt offline kézbesítés ugyanazzal a `client_operation_id` értékkel nem
  hoz létre új számlálást vagy új készletmozgást.
- Leltárkorrekció kizárólag a mozgásalapú készletfőkönyvön keresztül,
  változtathatatlan előzményekkel történhet.

## [0.6.0] - 2026-07-25

### Hozzáadva

- Szervezetenként telepített és verziózott Plugin SDK v1 manifest, külön
  plugin-szolgáltatásfelhasználóval, telepítési és engedélyezési állapottal.
- Explicit `products`, `documents`, `stock`, `reports`, `notifications` és
  `settings` jogosultságok; minden host API-hívásnál deklaráció- és
  engedélyellenőrzéssel.
- Tenant-határolt `PluginContext` termék-, hozzárendelt dokumentum-,
  készletmozgás-, saját beállítás- és deklarált eseménykibocsátási felülettel.
- Tartós outbox dispatcher, Redis/Dramatiq plugin worker, idempotens
  `plugin_jobs`, timeout, percenkénti futási korlát, újrapróbálás és stale-job
  helyreállítás.
- Hibás pluginfutások elkülönítése, végleges hibánál review feladat,
  auditbejegyzés és `plugin.failed` esemény.
- Adminisztrátori Pluginok munkafelület manifesttelepítéssel, engedélyezéssel,
  jogosultság- és beállításkezeléssel, valamint futásnaplóval.
- Az AI dokumentumfeldolgozás, a VRP-ütemezés és az e-mailes beérkezés
  átvezetése a közös manifest- és eseményszerződésre.
- Alapértelmezetten letiltott, ténylegesen futtatható készletfigyelő mintaplugin,
  teljes SDK-dokumentáció és külön példacsomag.
- Hatodik Alembic-migráció a pluginok, verziók, jogosultságok, beállítások és
  futások tartós tábláihoz; manifest-, jogosultság-, idempotencia-, retry-,
  elkülönítési és API-tesztek.

### Biztonság

- A manifest telepítése nem tölt be tetszőleges Python-kódot; csak a
  szervercsomaggal kiadott, előre regisztrált handler engedélyezhető.
- Új vagy frissítéssel bővült jogosultság nincs automatikusan megadva, és a
  plugin minden szükséges engedély nélkül letiltva marad.
- Plugin készletet kizárólag a központi `StockService` rétegen, elkülönített
  szolgáltatásfelhasználóval és idempotenciakulccsal módosíthat.
- A plugin nem választhat szervezetet, dokumentumból pedig csak az aktuális
  eseményben hozzárendelt erőforrás metaadatait érheti el.
- Titkos beállítás értéke az API-ban maszkolva jelenik meg.

## [0.5.0] - 2026-07-25

### Hozzáadva

- Szervezetenkénti, kriptográfiailag véletlen plus-címzésű dokumentum-postafiók
  engedélyezéssel, címrotációval és feladói domainlistával.
- Nyers RFC 822 levelet fogadó generikus inbound webhook HMAC-SHA256
  aláírás-ellenőrzéssel és konfigurálható replay-időablakkal.
- MIME-alapú csatolmánykinyerés, darab- és teljes levélméret-korlát, biztonságos
  fájlnévkezelés és a meglévő magic-byte/ClamAV dokumentumellenőrzés használata.
- Provider üzenetazonosító szerinti e-mail-idempotencia, valamint a meglévő
  szervezetenkénti dokumentumhash-duplikációvédelem.
- Ellenőrzött PDF/JPG/PNG/TIFF mellékletek automatikus, tartós AI-feldolgozási
  sorba állítása rendszerfolyamatként, hamis felhasználói attribúció nélkül.
- Opcionális SSL/TLS IMAP worker `BODY.PEEK[]` lekéréssel; a levél csak sikeres
  tartós átvétel után kap `Seen` jelölést.
- Üzenet-, melléklet-, elfogadási, duplikációs és elutasítási adatmodell,
  auditnapló, outbox esemény és hibánál manuális review feladat.
- Reszponzív e-mail munkafelület címmásolással, szabálykezeléssel, biztonsági
  állapotokkal, összesítéssel és automatikusan frissülő beérkezési naplóval.
- Ötödik Alembic-migráció, webhook-, idempotencia-, feladóvédelem-, API- és
  IMAP worker tesztek.
- Élő `docs/REMAINING.md` hiánylista, amelyből csak teljesen implementált és
  ellenőrzött architektúra-tételek kerülnek le.

### Biztonság

- Üres webhook-titoknál az inbound végpont zárva marad; hibás vagy lejárt
  aláírású kérés nem jut el a MIME-feldolgozásig.
- A feladó-domain korlátozás a fájl tárolása előtt érvényesül, az elutasítás
  pedig auditálható review feladatot hoz létre.
- Az e-mail törzse nem kerül AI-utasításként feldolgozásra; kizárólag a
  támogatott, tartalom alapján ellenőrzött mellékletek kerülhetnek a
  dokumentumpipeline-ba.
- Ismételt webhook-, IMAP- vagy dokumentumkézbesítés nem hoz létre ismételt
  készletfeldolgozást.

## [0.4.0] - 2026-07-25

### Hozzáadva

- CSV-, XLSX- és táblázatos PDF-alapú, verziózott VRP2 `Report predaja`
  parser szlovák, magyar és angol oszlopnév-felismeréssel.
- Szervezetenkénti fájlhash-, külső riportazonosító- és sorrendfüggetlen
  kanonikus tételhash-duplikációvédelem adatbázis-korlátokkal.
- Riportidőszak-átfedés blokkolása és kézi ellenőrzési feladat létrehozása.
- Külső termékazonosító, vonalkód, SKU, pontos név és lexikai javaslat alapú
  megfeleltetés; az első kézzel jóváhagyott konverzió tartós megjegyzése.
- Ismeretlen termékre `STOP`, `PROCESS_KNOWN` és `CREATE_REVIEW`, negatív
  készletre `STOP` és figyelmeztető engedélyezési szabály.
- Kézi, napi, heti és havi, időzónahelyes VRP-ütemezés Dramatiq workerrel,
  elakadt futások helyreállításával.
- Egy import minden ismert tételét egyetlen tranzakcióban, közös
  forrásazonosítóval és idempotenciakulccsal könyvelő készletfolyamat.
- Adminisztrátori, auditált teljes import-visszafordítás ellenmozgásokkal.
- Reszponzív VRP-munkafelület feltöltéssel, tételes faktorjóváhagyással,
  állapotfolyamattal, ütemezési szabályokkal és ellenőrzési soros navigációval.
- Negyedik Alembic-migráció és parser-, ütemező-, szolgáltatás- és API-tesztek.

### Biztonság

- Készletet a VRP-modul is kizárólag a központi `StockService` rétegen át
  módosít; részleges import nem kerül commitolásra.
- A kliens MIME-értéke nem megbízható: fájlkiterjesztés, magic byte,
  méretkorlát és opcionális ClamAV-vizsgálat előzi meg a tárolást.
- Az átfedési szabály nem kapcsolható ki, ismeretlen termék nem könyvelődik
  csendben, és a visszafordítás nettó készlethatása nulla.
- Minden VRP-lekérdezés, duplikációvizsgálat és termékpárosítás
  szervezetazonosítóval szűrt.

## [0.3.0] - 2026-07-25

### Hozzáadva

- Ollama Cloud és helyi Ollama végponttal használható, timeouttal és
  adatbázis-alapú circuit breakerrel védett szerveroldali AI Gateway.
- Gemma 4 31B multimodális bizonylatkinyerés PDF- és képelőfeldolgozással.
- Dramatiq + Redis worker, tartós adatbázis-job, exponenciális retry és elakadt
  feladatok helyreállítása.
- AI-kérés-, eredmény- és engedélyezett tool-call napló modell-, prompt-,
  token- és időmetrikákkal.
- Szigorú Pydantic AI-kimeneti szerződés bizonylatfejhez és tételsorokhoz.
- Vonalkód-, pontos név- és lexikai termékpárosítás, csomagolási konverzió és
  mennyiségi üzleti validáció.
- Bevételezési tervezet, kézi tételpárosítás és reszponzív AI-előnézeti felület.
- Jóváhagyáskor minden tételt egyetlen tranzakcióban, idempotensen könyvelő
  dokumentumalapú készletmozgások.
- Harmadik Alembic-migráció és AI/golden-contract automatizált tesztek.
- Karcsúsított Docker build context a helyi függőségek és futási
  melléktermékek kizárásával.

### Biztonság

- A dokumentum képe és szövege nem utasítás; a rendszerprompt minden
  dokumentumba ágyazott parancs figyelmen kívül hagyását előírja.
- Az Ollama Cloud natív strukturált kimenetének hiányában minden válasz kötelező
  szerveroldali sémaellenőrzésen megy át.
- A modell nem kap adatbázis-, shell-, fájlrendszer- vagy készletmódosító
  eszközt; készletet továbbra is kizárólag a `StockService` módosít.
- Hibás vagy ismeretlen AI-kimenet nem hoz létre részleges készletmozgást.

## [0.2.0] - 2026-07-25

### Hozzáadva

- PDF-, JPG-, PNG- és TIFF-dokumentumok jogosultsághoz kötött feltöltése.
- Tartalomalapú MIME-ellenőrzés, méret- és oldalszámkorlát.
- Szervezeten belüli SHA-256 duplikációvédelem.
- Helyi fejlesztői és S3/MinIO objektumtár-implementáció.
- Opcionális ClamAV INSTREAM vírusellenőrzés biztonságos hibakezeléssel.
- PDF- és képvalidáció, jelszóvédett vagy sérült fájlok ellenőrzési sora.
- Dokumentumoldalak, feldolgozási jobok és review feladatok adatmodellje.
- Idempotens dokumentum-feldolgozási sorba állítás és outbox események.
- Jogosultsággal védett, backend által közvetített dokumentumletöltés.
- Reszponzív dokumentumlista, drag-and-drop feltöltés és ellenőrzési felület.
- Második Alembic-migráció és dokumentumkezelési automatizált tesztek.

### Biztonság

- A kliens által küldött MIME-típus nem minősül megbízható fájltípusnak.
- Sikertelen vírusellenőrzéskor a dokumentum nem kerül objektumtárba.
- Az objektumkulcs nem tartalmaz felhasználói fájlnevet.

## [0.1.0] - 2026-07-25

### Hozzáadva

- FastAPI-alapú, moduláris backend és verziózott `/api/v1` API.
- Több szervezetet elkülönítő felhasználói és jogosultsági alapok.
- Rövid életű JWT hozzáférési token és forgatható refresh session.
- Terméktörzs, csomagolási egységek és szervezeten belül egyedi vonalkódok.
- Mozgásalapú készlet, tranzakciós készletegyenleg, idempotenciavédelem és
  ellenmozgásos visszavonás.
- Append-only auditnapló és tranzakcióval együtt létrejövő outbox események.
- React + TypeScript PWA operátori kezdőfelület, termékfelvétel és
  készletkorrekció.
- PostgreSQL, Redis és MinIO szolgáltatásokat indító Docker Compose környezet.
- Alembic adatbázis-migráció, bootstrap admin és automatizált backend tesztek.
- Projektindítási, konfigurációs és verziózási dokumentáció.

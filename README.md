# AI Raktárkezelő

Mobilról és laptopról használható, mozgásalapú készletkezelő rendszer. A
megvalósítás forrása az ebben a könyvtárban található teljes PDF/DOCX műszaki
architektúra.

## Aktuális verzió

`0.15.1` - egyenként, kétlépcsős megerősítéssel törölhető dokumentumok és
nulla készletű termékek. A törlés jogosultságvédett és auditált; feldolgozás alatt
álló dokumentum, illetve készlettel rendelkező termék nem törölhető. A soronkénti
törlés mobilnézetben is mindig elérhető.

Az aktuális kiadás tartalmazza a felhasználói hitelesítést, terméktörzset,
vonalkódokat, csomagolási egységeket, tranzakciós készletmozgásokat,
visszavonást és auditot. Ezek mellett PDF- és képdokumentumok feltöltését,
tartalomalapú fájlellenőrzését, szervezetenkénti SHA-256 duplikációvédelmét,
objektumtárolását, feldolgozási sorba állítását és kézi felülvizsgálatát is
biztosítja egy mobilbarát PWA-felületen. Az Ollama/Gemma multimodális pipeline
kinyeri a bizonylattételeket, belső termékhez és csomagolási egységhez párosítja
őket, majd ellenőrzött előnézetből, egyetlen tranzakcióban könyveli a készletet.
Az új VRP-modul CSV-, XLSX- és géppel olvasható PDF-eladási riportokat fogad,
kiszűri a fájl- és tartalmi duplikációkat, blokkolja az átfedő időszakokat,
megjegyzi a jóváhagyott termék- és egységkonverziókat, majd kézzel vagy
napi/heti/havi rendben könyveli az értékesítést. Az adminisztrátor az egész
importot ellenmozgásokkal, auditáltan vissza is fordíthatja.
Az e-mail modul szervezetenként külön, nem kitalálható dokumentumcímet ad,
ellenőrzi az inbound webhook HMAC-aláírását, feladó-domain szabályokat alkalmaz,
majd a PDF- és képmellékleteket ugyanabba a vírus-, MIME-, hash- és AI-folyamatba
irányítja, mint a kézi feltöltés. Az üzenet- és dokumentumszintű
duplikációvédelem, az audit és a kézi ellenőrzési sor e-mailnél is kötelező.
Az új Plugin SDK szervezetenként telepített és verziózott manifestet, külön
szolgáltatásfelhasználót, explicit engedélyeket és idempotens, tartós
eseményfuttatást biztosít. A beépített AI-, VRP- és e-mail-modul ugyanazt a
pluginszerződést használja; a mintaplugin és az adminisztrációs felület a
fejlesztést és az üzemeltetést is támogatja.
Az új kézi leltármenet Android Chrome-ban natív `BarcodeDetector` használatával,
más modern böngészőkben ZXing fallbackkel olvas EAN-, UPC-, Code 128-,
Data Matrix- és QR-kódot. A számlálások egyedi kliensművelet-azonosítóval
IndexedDB offline sorba kerülnek, így megszakíthatók, folytathatók és
idempotensen újraküldhetők. Lezáráskor az eltérések a központi
`StockService` rétegen, auditált korrekcióként könyvelődnek; nagy eltérés
vezetői jóváhagyást kér.
Az Identity munkafelületen a szervezeti adminisztrátor felhasználókat, rendszer-
és egyedi szerepköröket, finom engedélyeket, saját MFA-t és aktív
munkameneteket kezelhet. Az API-tokenek kizárólag a létrehozó aktuális
engedélyeinek részhalmazára adhatók ki, titkuk csak egyszer jelenik meg, és
azonnal visszavonhatók. Az Offline feltöltések munkafelület dokumentum- és
VRP-fájlokat tárol IndexedDB-ben, majd kapcsolat esetén hash-ellenőrzött
darabokban folytatja a megszakított feltöltést.

## Gyors indítás Dockerrel

1. Másold le a `.env.example` fájlt `.env` néven, és módosítsd a titkokat.
2. Indítsd el a szolgáltatásokat:

   ```powershell
   docker compose up --build
   ```

3. Nyisd meg a `http://localhost:8080` címet.
4. Jelentkezz be az `.env` fájlban beállított szervezetazonosítóval, e-maillel
   és jelszóval.
5. Az adminisztrátor a „Felhasználók és biztonság” oldalon igény szerint
   beállíthatja a hitelesítő alkalmazást. Bekapcsoláskor mentse el a csak
   egyszer megjelenő helyreállító kódokat.

Az API dokumentációja: `http://localhost:8080/api/docs`.

## Helyi fejlesztés

### Backend

Python 3.12 vagy újabb szükséges.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:APP_DATABASE_URL = "sqlite:///./ai_raktar_dev.db"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.bootstrap
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

A Vite fejlesztői szerver a `/api` kéréseket a `http://localhost:8000`
címre továbbítja.

Helyi fejlesztéskor a dokumentumok alapértelmezetten a
`backend/data/objects` könyvtárba kerülnek. Docker Compose környezetben a
MinIO S3-kompatibilis objektumtár használható. A ClamAV-vírusellenőrzés
környezeti változóval kapcsolható be; bekapcsolt állapotban sikertelen
ellenőrzés esetén a feltöltés zárt módon elutasításra kerül.

Az AI alapértelmezetten le van tiltva. Ollama Cloud használatához állítsd be az
`APP_AI_PROVIDER=ollama` és `APP_OLLAMA_API_KEY` változókat. Helyi Ollama
használatakor az `APP_OLLAMA_BASE_URL` értéke például
`http://host.docker.internal:11434`, az API-kulcs pedig üres lehet. A háttér
worker Docker Compose alatt automatikusan indítja az AI-jobok helyreállítását,
a VRP-ütemezőt és - engedélyezés esetén - az IMAP lekérdezést is. Helyi teljes
worker:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.enqueue_pending
.\.venv\Scripts\dramatiq.exe app.tasks --processes 1 --threads 2
```

Egyetlen esedékes AI-dokumentum helyi feldolgozása:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.worker --once
```

## Vonalkódos és automatikus bevételezés

Az **Áru érkezett** műveletben ugyanaz a mobilkamerás EAN/UPC/Code 128/Data
Matrix/QR olvasó használható, mint a leltárban. A csomagolási egységhez kötött
kartonkód a darabszámot automatikusan alapegységre váltja.

A **Feltöltési sor** mobilról közvetlen bizonylatfotót is készít. Az
„AI-felismerés és automatikus bevételezés” bekapcsolásakor a feltöltés
automatikusan feldolgozásra kerül. Készletkönyvelés csak legalább az
`APP_AI_AUTO_CONFIRM_MIN_CONFIDENCE` küszöböt elérő, hibamentes, vonalkóddal
vagy pontos névvel párosított tételeknél történik; minden más eset kézi
ellenőrzésre marad. A részletes folyamat:
[`docs/AUTOMATIC_GOODS_RECEIPT.md`](docs/AUTOMATIC_GOODS_RECEIPT.md).
Nagy helyi vision modell első betöltéséhez az alapértelmezett
`APP_AI_TIMEOUT_SECONDS` érték `300` másodperc.

## Plugin SDK

Az adminisztrátorok a **Pluginok** munkafelületen tekinthetik meg a telepített
manifesteket, a szükséges engedélyeket, a beállításokat és a tartós futások
állapotát. Egy külső plugin csak a szerverrel együtt telepített, regisztrált
handlerrel, minden deklarált jogosultság külön megadása után engedélyezhető.

A manifest, a host API, az eseményszerződés, a hibakezelés és a mintakód teljes
leírása: [`docs/PLUGIN_SDK.md`](docs/PLUGIN_SDK.md).

## Mobil kézi leltár

A **Kézi leltár** menüpontban indítható számlálási menet. A kamera mellett
Bluetooth olvasó, kézi kódbevitel és termékkeresés is használható. A
csomagolási egységhez rendelt kartonkód automatikusan a megfelelő
alapegység-szorzóval növeli a számlálást.

Eltérésnél kötelező okkódot megadni. A
`APP_INVENTORY_APPROVAL_THRESHOLD` értéknél nagyobb abszolút eltérést
raktáros nem könyvelhet közvetlenül; a rendszer review feladatot hoz létre
admin vagy manager számára. A részletes folyamat és az offline működés:
[`docs/INVENTORY_PWA.md`](docs/INVENTORY_PWA.md).

## Identity és offline feltöltések

A szerepkörök, engedélyek, MFA, munkamenetek, API-tokenek és a folytatható
fájlfeltöltési protokoll leírása:
[`docs/IDENTITY_AND_OFFLINE_UPLOADS.md`](docs/IDENTITY_AND_OFFLINE_UPLOADS.md).

## E-mailes dokumentumbeérkezés

A felületen az **E-mail postafiók** menüpont mutatja az adott szervezet
`documents+<titkos-token>@<domain>` címét, a feladói engedélylistát és a
beérkezési naplót. A cím domainjét az `APP_EMAIL_INBOUND_DOMAIN` adja; ehhez a
telepítésben MX vagy inbound-mail szolgáltatói útvonal szükséges.

A generikus webhook a teljes nyers RFC 822 levelet fogadja:

```text
POST /api/v1/email/inbound
Content-Type: message/rfc822
X-Inbound-Timestamp: <Unix timestamp>
X-Inbound-Signature: sha256=<hex HMAC>
X-Inbound-Provider: <provider név>
X-Provider-Message-ID: <provider oldali egyedi azonosító>
```

Az aláírandó bájtsor a timestamp ASCII alakja, egy pont, majd a változatlan
nyers levél (`<timestamp>.<raw-message>`); a kulcs az
`APP_EMAIL_WEBHOOK_SECRET`. Az alapértelmezett elfogadási időablak 300
másodperc. Üres webhook-titoknál a végpont zárva marad.

Opcionális közös IMAP postafiókhoz állítsd be az
`APP_EMAIL_IMAP_ENABLED=true`, `APP_EMAIL_IMAP_HOST`,
`APP_EMAIL_IMAP_USERNAME` és `APP_EMAIL_IMAP_PASSWORD` értékeket. A worker
`BODY.PEEK[]` lekéréssel dolgozik, és egy levelet csak a tartós adatbázisba
írás után jelöl olvasottnak. A címzett plus-címzési tokenje választja ki a
szervezetet.

## VRP2 riportformátum

A hivatalos VRP2 `Report predaja` riport kiválasztott dátumtartományra készül,
és az eladott tételeket tartalmazza. A gépi export oszlopnevei változhatnak,
ezért az importáló verziózott, többnyelvű oszlopfelismerést használ.

- Kötelező: terméknév (`Označenie tovaru`, `Názov položky`, `Megnevezés`,
  `Product name`) és mennyiség (`Množstvo`, `Predané množstvo`, `Mennyiség`,
  `Quantity`).
- Opcionális: külső termékkód/PLU/EAN és mértékegység.
- A riportidőszak kezdete és vége feltöltéskor kötelező.
- Ár-, áfa- és egyéb pénzügyi mező készletkönyvelésbe nem kerül.
- Támogatott fájl: UTF-8 vagy Windows-1250 CSV, XLSX és géppel olvasható,
  táblázatos PDF; a sor- és méretkorlát környezeti változóval állítható.

Az alapul vett hivatalos források: [VRP2 felhasználói
kézikönyv](https://www.financnasprava.sk/_img/pfsedit/Dokumenty_PFS/Elektronicke_sluzby/Elektronicka_komunikacia/Elektronicka_komunikacia_dane/Prirucky_navody/2025/2025.08.20_VRP_prirucka.pdf)
és [VRP riportok
GYIK](https://podpora.financnasprava.sk/866537-Reporty-v-aplik%C3%A1cii-VRP).

## Minőségellenőrzés

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

cd ..\frontend
npm run lint
npm run build
```

## Verziózási szabály

- Minden átadott fejlesztési kör külön verziót kap.
- A gyökér `VERSION`, a backend és a frontend verziója együtt változik.
- Minden kiadás bekerül a `CHANGELOG.md` fájlba.
- Stabil kiadás után az azonos nevű Git-tag készül, például `v0.8.0`.

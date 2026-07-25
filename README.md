# AI Raktárkezelő

Mobilról és laptopról használható, mozgásalapú készletkezelő rendszer. A
megvalósítás forrása az ebben a könyvtárban található teljes PDF/DOCX műszaki
architektúra.

## Aktuális verzió

`0.4.0` - VRP2 eladási riportok ellenőrzött, ütemezhető
készletkönyvelése.

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

## Gyors indítás Dockerrel

1. Másold le a `.env.example` fájlt `.env` néven, és módosítsd a titkokat.
2. Indítsd el a szolgáltatásokat:

   ```powershell
   docker compose up --build
   ```

3. Nyisd meg a `http://localhost:8080` címet.
4. Jelentkezz be az `.env` fájlban beállított szervezetazonosítóval, e-maillel
   és jelszóval.

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
worker Docker Compose alatt automatikusan indítja az AI-jobok helyreállítását
és a VRP-ütemezőt is. Helyi teljes worker:

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
- Stabil kiadás után az azonos nevű Git-tag készül, például `v0.4.0`.

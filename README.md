# AI Raktárkezelő

Mobilról és laptopról használható, mozgásalapú készletkezelő rendszer. A
megvalósítás forrása az ebben a könyvtárban található teljes PDF/DOCX műszaki
architektúra.

## Aktuális verzió

`0.3.0` - AI-alapú bizonylatkinyerés, termékpárosítás és jóváhagyás.

Az aktuális kiadás tartalmazza a felhasználói hitelesítést, terméktörzset,
vonalkódokat, csomagolási egységeket, tranzakciós készletmozgásokat,
visszavonást és auditot. Ezek mellett PDF- és képdokumentumok feltöltését,
tartalomalapú fájlellenőrzését, szervezetenkénti SHA-256 duplikációvédelmét,
objektumtárolását, feldolgozási sorba állítását és kézi felülvizsgálatát is
biztosítja egy mobilbarát PWA-felületen. Az Ollama/Gemma multimodális pipeline
kinyeri a bizonylattételeket, belső termékhez és csomagolási egységhez párosítja
őket, majd ellenőrzött előnézetből, egyetlen tranzakcióban könyveli a készletet.

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
worker Docker Compose alatt automatikusan indul; helyi egyszeri feldolgozás:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.worker --once
```

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
- Stabil kiadás után az azonos nevű Git-tag készül, például `v0.3.0`.

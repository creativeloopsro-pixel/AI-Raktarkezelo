# AI Raktárkezelő

Mobilról és laptopról használható, mozgásalapú készletkezelő rendszer. A
megvalósítás forrása az ebben a könyvtárban található teljes PDF/DOCX műszaki
architektúra.

## Aktuális verzió

`0.1.0` - domain- és alkalmazásalapok.

Az aktuális kiadás tartalmazza a felhasználói hitelesítést, terméktörzset,
vonalkódokat, csomagolási egységeket, tranzakciós készletmozgásokat,
visszavonást, auditot és egy mobilbarát PWA-kezdőfelületet.

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
- Stabil kiadás után az azonos nevű Git-tag készül, például `v0.1.0`.


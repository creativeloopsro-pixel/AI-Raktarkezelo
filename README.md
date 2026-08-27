# AI Skladové hospodárstvo

> **Projekt je vo vývoji.** Funkcie, rozhranie a integračné možnosti sa môžu počas vývoja rozšíriť alebo zmeniť.

Moderná webová aplikácia pre inteligentnú správu skladu, produktov a príjmu tovaru. Umožňuje mobilné skenovanie EAN kódov, evidenciu zásob a skladových pohybov, spracovanie dodacích listov vo formáte PDF alebo fotografie pomocou AI a bezpečné automatizované zálohovanie.

Systém je určený pre malé a stredné firmy, ktoré chcú mať presný prehľad o sklade bez zložitej manuálnej administratívy. Obsahuje správu používateľov a oprávnení, inventúry, spracovanie VRP reportov o predaji, auditné záznamy, API tokeny, offline nahrávanie dokumentov a obnovenie dát zo zálohy.

Lokálne spustenie: [http://localhost:8080](http://localhost:8080)

Tento odkaz funguje iba na počítači, kde aplikácia beží. Pred nasadením pre zákazníkov použite vlastnú doménu a produkčný VPS alebo PaaS hosting.

## Aktuálna verzia

**0.17.2** – kompletný README je dostupný v slovenčine.

## Hlavné funkcie

- **Produkty a čiarové kódy:** produktový katalóg, číselný EAN a vizuálny čiarový kód pri každom produkte, balené jednotky a rýchle čítanie kódu kamerou mobilného zariadenia.
- **Príjem tovaru:** ručné zaúčtovanie, skenovanie čiarového kódu a automatické prepočítanie kartónových balení na základnú jednotku.
- **AI spracovanie dokladov:** fotografia alebo PDF dodacieho listu sa nahrá, AI vyčíta položky a navrhne priradenie k produktom. Pri dostatočnej istote môže systém tovar automaticky prijať na sklad; neisté položky čakajú na manuálnu kontrolu.
- **Dokumenty a VRP:** import CSV, XLSX a strojovo čitateľných PDF reportov o predaji, kontrola duplicitných súborov a obdobia, následné zaúčtovanie predaja ručne alebo podľa denného, týždenného či mesačného rozvrhu.
- **Inventúra:** mobilné počítanie prostredníctvom EAN, UPC, Code 128, Data Matrix a QR kódov, Bluetooth skenera, ručného zadania alebo vyhľadania produktu.
- **Offline režim:** prerušiteľné a obnoviteľné nahrávanie dokumentov a VRP súborov. Počítania inventúry sa pri výpadku spojenia bezpečne ukladajú v zariadení a po pripojení sa idempotentne synchronizujú.
- **Používatelia a bezpečnosť:** vlastné roly, jemné oprávnenia, MFA správcu, obnovovacie kódy, správa relácií a odvolateľné API tokeny s obmedzeným rozsahom.
- **E-mailový príjem:** samostatná bezpečná adresa dokumentov pre organizáciu, kontrola HMAC podpisu webhooku a filtrovanie povolených odosielateľov.
- **Zálohy a obnova:** manuálne aj automatické denné, týždenné alebo mesačné ZIP zálohy. Najnovšia úspešná záloha je stiahnuteľná a pri obnove sa neprepíšu heslá, API kľúče ani bezpečnostné údaje.
- **Audit a vratné operácie:** všetky dôležité skladové pohyby, importy a bezpečnostné operácie sú auditované; import možno zrušiť vytvorením kontrolovaných proti-pohybov.

## Použité programovacie jazyky a technológie

- **Python 3.12+** – backendové API, obchodná logika, AI integrácie,
  spracovanie dokumentov, background workery, testy a databázové migrácie
  (FastAPI, SQLAlchemy, Alembic, Dramatiq).
- **TypeScript a TSX** – webové používateľské rozhranie v Reacte, PWA funkcie,
  obrazovky správy skladu, kamerové skenovanie čiarových kódov a komunikácia s API.
- **JavaScript** – nástroje a konfigurácia frontendu vo Vite prostredí.
- **HTML a CSS** – štruktúra a štýly používateľského rozhrania; na konzistentný
  responzívny dizajn sa používa aj Tailwind CSS.
- **SQL** – databázová vrstva je navrhnutá pre PostgreSQL a podporuje SQLite pri
  lokálnom vývoji; schéma a migrácie sa riadia cez SQLAlchemy a Alembic.
- **YAML a JSON** – deklaratívna konfigurácia Docker Compose, build nástrojov,
  závislostí a nasadenia. Nejde o aplikačné programovacie jazyky, ale sú
  súčasťou prevádzkovej konfigurácie projektu.

## Ako funguje automatický príjem

1. Pracovník odfotí dodací list alebo nahrá PDF.
2. Súbor prejde kontrolou typu, veľkosti, obsahu, vírusu a duplicity.
3. AI vyčíta produkty, množstvá, jednotky a dostupné čiarové kódy.
4. Systém spáruje položky s produktovým katalógom.
5. Jednoznačné položky s nastavenou úrovňou istoty sa automaticky prijmú na sklad; ostatné sa zobrazia na schválenie.
6. Výsledok sa zapíše ako auditovaný skladový pohyb.

Podrobný postup: [Automatický príjem tovaru](docs/AUTOMATIC_GOODS_RECEIPT.md).

## Rýchle spustenie pomocou Dockeru

1. Skopírujte súbor .env.example ako .env a zmeňte všetky tajné hodnoty.
2. Spustite služby:

~~~powershell
docker compose up --build
~~~

3. Otvorte adresu http://localhost:8080.
4. Prihláste sa pomocou identifikátora organizácie, e-mailu a hesla nastavených v súbore .env.
5. Správca môže na stránke **Používatelia a bezpečnosť** nastaviť autentifikačnú aplikáciu a bezpečne uložiť jednorazové obnovovacie kódy.

Dokumentácia API: http://localhost:8080/api/docs

## Lokálny vývoj

### Backend

Vyžaduje sa Python 3.12 alebo novší.

~~~powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:APP_DATABASE_URL = "sqlite:///./ai_raktar_dev.db"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.bootstrap
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
~~~

### Frontend

~~~powershell
cd frontend
npm install
npm run dev
~~~

Vývojový server Vite presmeruje požiadavky /api na http://localhost:8000.

Pri lokálnom vývoji sa dokumenty štandardne ukladajú do priečinka backend/data/objects. V prostredí Docker Compose možno použiť objektové úložisko MinIO kompatibilné so S3. Antivírusovú kontrolu ClamAV je možné zapnúť premennou prostredia; pri neúspešnej kontrole sa nahrávanie bezpečne odmietne.

AI je predvolene vypnutá. Pre Ollama Cloud nastavte APP_AI_PROVIDER=ollama a APP_OLLAMA_API_KEY. Pri lokálnej Ollama môže byť APP_OLLAMA_BASE_URL napríklad http://host.docker.internal:11434 a API kľúč môže zostať prázdny. Worker v Docker Compose automaticky obnovuje AI úlohy, plánovač VRP a – ak je povolený – IMAP dotazovanie.

~~~powershell
cd backend
.\.venv\Scripts\python.exe -m app.enqueue_pending
.\.venv\Scripts\dramatiq.exe app.tasks --processes 1 --threads 2
~~~

Spracovanie jednej čakajúcej AI úlohy lokálne:

~~~powershell
cd backend
.\.venv\Scripts\python.exe -m app.worker --once
~~~

## Rozšírené moduly

- **Plugin SDK:** správcovia si môžu pozrieť inštalované manifesty, požadované oprávnenia, nastavenia a stav spustení. Externý plugin sa môže povoliť iba s registrovaným serverovým handlerom a výslovne pridelenými oprávneniami. Podrobnosti: [Plugin SDK](docs/PLUGIN_SDK.md).
- **Mobilná inventúra:** pri rozdiele treba uviesť dôvod. Rozdiel presahujúci hodnotu APP_INVENTORY_APPROVAL_THRESHOLD musí schváliť správca alebo manažér. Podrobnosti: [Inventúra PWA](docs/INVENTORY_PWA.md).
- **Identity a offline nahrávanie:** protokol rolí, oprávnení, MFA, relácií, API tokenov a obnoviteľného prenosu súborov: [Identity a offline nahrávanie](docs/IDENTITY_AND_OFFLINE_UPLOADS.md).
- **Príjem dokumentov e-mailom:** adresa organizácie má tvar documents+<tajný-token>@<doména>. Príjem vyžaduje MX záznam alebo službu pre prichádzajúci e-mail a používa podpis APP_EMAIL_WEBHOOK_SECRET.
- **Formát VRP2:** importer rozpoznáva viacjazyčné názvy stĺpcov. Povinný je názov produktu a množstvo; voliteľný je externý kód, PLU, EAN a merná jednotka. Cena, DPH ani iné finančné polia sa do skladového účtovania neprenášajú.

Oficiálne zdroje VRP: [používateľská príručka VRP2](https://www.financnasprava.sk/_img/pfsedit/Dokumenty_PFS/Elektronicke_sluzby/Elektronicka_komunikacia/Elektronicka_komunikacia_dane/Prirucky_navody/2025/2025.08.20_VRP_prirucka.pdf) a [často kladené otázky k VRP reportom](https://podpora.financnasprava.sk/866537-Reporty-v-aplik%C3%A1cii-VRP).

## Kontrola kvality

~~~powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

cd ..\frontend
npm run lint
npm run build
~~~

## Pravidlá verzovania

- Každý odovzdaný vývojový cyklus dostane samostatnú verziu.
- Verzia v koreňovom súbore VERSION, backende a fronte sa mení spoločne.
- Každé vydanie sa zaznamená v súbore CHANGELOG.md.
- Po stabilnom vydaní vznikne Git tag s rovnakým názvom, napríklad v0.8.0.

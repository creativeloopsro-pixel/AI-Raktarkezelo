# Változásnapló

A projekt minden kiadása a [Semantic Versioning](https://semver.org/) szabályait
követi. A fejlesztés alapdokumentuma az
`AI_Raktarkezelo_Teljes_Architektura.pdf` és annak DOCX-változata.

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

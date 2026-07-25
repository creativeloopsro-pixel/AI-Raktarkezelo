# Változásnapló

A projekt minden kiadása a [Semantic Versioning](https://semver.org/) szabályait
követi. A fejlesztés alapdokumentuma az
`AI_Raktarkezelo_Teljes_Architektura.pdf` és annak DOCX-változata.

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

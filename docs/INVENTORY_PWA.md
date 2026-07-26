# Mobil kézi leltár és offline számlálás

## Folyamat

1. A felhasználó online elindít egy leltármenetet.
2. A kliens elmenti az aktív menetet, a terméktörzset és a készletegyenlegeket
   IndexedDB-be.
3. A termék kamerával, Bluetooth olvasóval, kézi kóddal vagy kereséssel
   azonosítható.
4. A felhasználó megadja a tényleges mennyiséget. Eltérésnél okkód kötelező.
5. Minden mentés önálló, egyedi `client_operation_id` értékű offline művelet.
6. Online kapcsolatnál a sor sorrendben, idempotensen szinkronizálódik.
7. Lezáráskor termékenként a legfrissebb számlálás érvényesül.
8. A rendszer az aktuális szerveroldali egyenleghez képest, egyetlen
   tranzakcióban készíti el a korrekciós mozgásokat.

## Kódolvasás

A preferált motor a böngésző natív `BarcodeDetector` API-ja. Támogatott
formátumok:

- EAN-8
- EAN-13
- UPC-A
- Code 128
- Data Matrix
- QR

Ha a natív API nem érhető el, a kliens dinamikusan betölti az
`@zxing/browser` motort. A kamera HTTPS-en vagy `localhost` környezetben,
felhasználói engedéllyel működik. A manuális beviteli mező külső Bluetooth
olvasó Enter billentyűvel lezárt adatát is fogadja.

Termékkód esetén az alap növekmény `1`. Ha a kód csomagolási egységhez
tartozik, a számláló a `multiplier_to_base_unit` értékkel növekszik.

Ugyanez a kódolvasó az **Áru érkezett** bevételezési ablakban is elérhető.
Beolvasáskor kiválasztja a terméket és a kódhoz tartozó csomagolási egységet.
A felhasználó a beérkezett csomagok számát adja meg, a kliens pedig a
`multiplier_to_base_unit` szorzóval számított alapegység-mennyiséget küldi a
tranzakciós készlet API-nak.

## Offline sor

Az IndexedDB `inventory_operations` tára a következőket őrzi:

- szervezet és leltármenet azonosítója;
- egyedi kliensművelet-azonosító;
- termék, mennyiség, kliensoldali elvárt készlet és beolvasott kód;
- okkód és megjegyzés;
- kliensoldali időbélyeg;
- próbálkozásszám és utolsó hiba.

A sor automatikusan folytatódik az `online` eseménynél, de a felhasználó
szüneteltetheti és kézzel is újraküldheti. A leltár csak üres sorral és online
kapcsolatban zárható le. Az adatbázis
`(organization_id, client_operation_id)` egyedisége biztosítja, hogy hálózati
ismétlés ne duplázza a számlálást.

Az `inventory_cache` tárolja a legutóbbi termék-, készlet-, menet- és
előzmény-pillanatképet. Másik tenant gyorsítótára nem jelenhet meg, mert minden
kulcs tartalmazza a szervezetazonosítót.

## Korrekció és jóváhagyás

Okkódok:

- `PHYSICAL_COUNT`
- `DAMAGE`
- `SHRINKAGE`
- `DATA_ERROR`
- `OTHER`

Az `APP_INVENTORY_APPROVAL_THRESHOLD` az abszolút mennyiségi eltérés
alapértelmezett küszöbe, alapértéke `100`. A küszöbnél nagyobb eltérés
raktárosi lezáráskor `PENDING_APPROVAL` állapotot és
`INVENTORY_APPROVAL` review feladatot hoz létre. Admin vagy manager
jegyzettel jóváhagyhatja vagy elutasíthatja.

Jóváhagyáskor minden eltérés:

- `INVENTORY_CORRECTION` készletmozgást;
- kapcsolt `stock_corrections` rekordot;
- auditbejegyzést;
- `stock.changed` és összesített `inventory.corrected` outbox eseményt hoz
  létre.

Az eredeti mozgások és számlálások nem törlődnek.

## API

| Metódus | Útvonal | Funkció |
| --- | --- | --- |
| `GET` | `/api/v1/inventory/sessions/current` | Aktív vagy jóváhagyásra váró menet |
| `GET` | `/api/v1/inventory/sessions` | Leltárelőzmények |
| `POST` | `/api/v1/inventory/sessions` | Menet indítása |
| `POST` | `/api/v1/inventory/sessions/{id}/counts` | Idempotens számlálás |
| `POST` | `/api/v1/inventory/sessions/{id}/complete` | Lezárás vagy jóváhagyáskérés |
| `POST` | `/api/v1/inventory/sessions/{id}/approve` | Vezetői jóváhagyás |
| `POST` | `/api/v1/inventory/sessions/{id}/cancel` | Megszakítás vagy elutasítás |

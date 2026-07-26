# Vonalkódos és AI automatikus bevételezés

## Mobilos vonalkódos bevételezés

Az **Áru érkezett** műveletben a termék az alábbi módokon azonosítható:

- mobil hátlapi kamerájával;
- Bluetooth vagy USB vonalkódolvasóval;
- kézi kódbevitellel;
- a terméklista kézi kiválasztásával.

A böngésző először a natív `BarcodeDetector` API-t használja EAN-8, EAN-13,
UPC-A, Code 128, Data Matrix és QR formátumokra. Ha ez nem érhető el, a ZXing
fallback dinamikusan töltődik be.

Ha a vonalkód csomagolási egységhez tartozik, a felhasználó a csomagok számát
adja meg. A kliens megjeleníti és alkalmazza a
`multiplier_to_base_unit` szorzót, a backend pedig az alapegység-mennyiséget
idempotens `GOODS_RECEIPT` készletmozgásként könyveli.

## Bizonylatfotóból automatikus készlet

1. A felhasználó a **Feltöltési sorban** fájlt választ vagy a mobil hátlapi
   kamerájával lefényképezi a bizonylatot.
2. Az „AI-felismerés és automatikus bevételezés” opció a folytatható feltöltési
   munkamenet metaadataiba kerül.
3. A teljes fájl SHA-256 ellenőrzés, MIME-ellenőrzés, méretkorlát és opcionális
   vírusellenőrzés után kerül az objektumtárba.
4. Az AI plugin automatikusan sorba állítja a bejövő bizonylatot vagy
   szállítólevelet.
5. Az Ollama multimodális modell szigorú JSON-séma szerint kinyeri a tételeket.
6. A termékpárosítás sorrendje: vonalkód, pontos terméknév, majd kézi
   ellenőrzésre alkalmas lexikai egyezés.
7. A rendszer csak a biztonsági feltételeket teljesítő tervezetet könyveli
   automatikusan a központi `StockService` rétegen át.

## Automatikus könyvelési feltételek

Minden feltételnek egyszerre teljesülnie kell:

- `APP_AI_AUTO_CONFIRM_RECEIPTS=true`;
- a feltöltésnél kérték az automatikus bevételezést;
- a tervezet és minden tétele hibamentes, `READY` állapotú;
- minden tétel konfidenciája legalább
  `APP_AI_AUTO_CONFIRM_MIN_CONFIDENCE` — alapértéke `0.98`;
- minden termék vonalkóddal vagy pontos névvel párosult;
- a mennyiség pozitív, a csomagolási egység ismert;
- a feltöltő aktív és rendelkezik `stock.receive`, valamint
  `receipts.confirm` engedéllyel.

Ha bármelyik feltétel hiányzik, készletmozgás nem jön létre. A dokumentum kézi
ellenőrzésre vagy jóváhagyásra vár, az automatikus döntés oka pedig az
auditnaplóba kerül.

Az AI-worker `APP_AI_TIMEOUT_SECONDS` alapértéke `300`, hogy egy nagyobb helyi
vision modell első, hideg betöltése is befejeződhessen.

## Idempotencia és audit

Minden bizonylattétel készletmozgási kulcsa:

```text
goods-receipt:<draft_id>:<item_id>
```

Ismételt worker-futtatás ezért nem növelheti meg másodszor a készletet. A
könyvelés egy tranzakcióban hozza létre a készletmozgást, frissíti az egyenleget,
írja az auditnaplót és létrehozza a `stock.changed`, valamint
`goods_receipt.confirmed` outbox eseményt. Az automatikus megerősítés forrása
`AI_AUTOMATIC`.

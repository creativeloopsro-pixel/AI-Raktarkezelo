# Identity, MFA és offline fájlfeltöltés

## Szerepkörök és engedélyek

Az engedély a backend által ismert, stabil kód, például `products.read`,
`documents.upload`, `vrp.process` vagy `tokens.revoke`. A szerepkör egy
szervezeten belüli engedélykészlet, a felhasználóhoz pedig több szerepkör is
rendelhető. Az effektív hozzáférés a hozzárendelt szerepkörök engedélyeinek
uniója.

Az öt beépített szerepkör:

- `admin`: minden engedély és rendszeradminisztráció;
- `manager`: napi üzletvezetői, jóváhagyási és riportműveletek;
- `warehouse`: termék-, készlet-, dokumentum- és feltöltési operációk;
- `viewer`: csak megtekintési hozzáférés;
- `service`: szűkített plugin-szolgáltatásfiók.

A rendszer-szerepkörök engedélykészlete módosítható, de nem törölhetők. Egyedi
szerepkör létrehozható és törölhető, ha már nincs felhasználóhoz rendelve. A
saját adminisztrátori hozzáférés és a saját aktív fiók véletlen eltávolítását a
backend tiltja.

Az Identity munkafelülethez tartozó fő végpontok:

```text
GET/POST/PATCH/DELETE /api/v1/identity/roles
GET/POST/PATCH        /api/v1/identity/users
GET                   /api/v1/identity/permissions
GET/POST/DELETE       /api/v1/identity/tokens
```

## Adminisztrátori MFA

Docker Compose alatt az `APP_MFA_ENFORCE_ADMIN=false` az alapértelmezett, ezért
az adminisztrátor MFA nélkül is teljes munkamenetet kap. Az üzemeltető az
`APP_MFA_ENFORCE_ADMIN=true` beállítással teheti kötelezővé az admin MFA-t; ekkor
az első belépés rövid életű hozzáférést ad kizárólag az MFA beállításához. A
felhasználó a megjelenített `otpauth://` URI-t vagy kézi titkot hitelesítő
alkalmazásba veszi fel, majd egy hatjegyű kóddal erősíti meg.

Sikeres megerősítéskor a rendszer egyszer használható helyreállító kódokat ad.
Ezek csak egyszer jelennek meg, hash-elve kerülnek adatbázisba, és egy felhasznált
kód többé nem fogadható el. Kötelező admin MFA esetén az adminisztrátor nem
kapcsolhatja ki; opcionális módban a saját MFA kikapcsolható.

```text
POST   /api/v1/auth/mfa/setup
POST   /api/v1/auth/mfa/confirm
POST   /api/v1/auth/mfa/verify
DELETE /api/v1/auth/mfa
```

## Munkamenet-védelem

Az access token rövid életű, a refresh token minden frissítéskor cserélődik.
A refresh sessionök token-családot alkotnak. Egy már lecserélt refresh token
újrahasználata valószínű tokenlopásként kezelődik, ezért a rendszer az egész
családot visszavonja. A munkamenetek user-agentet, IP-címet, létrehozási és
utolsó használati időt tárolnak.

```text
GET    /api/v1/auth/sessions
DELETE /api/v1/auth/sessions/{session_id}
POST   /api/v1/auth/sessions/revoke-others
```

## Hatókörhöz kötött API-token

Az API-token `airk_` előtaggal az Authorization Bearer mezőben használható.
A nyers token csak létrehozáskor jelenik meg; a szerver HMAC-hashként tárolja.
A scope kizárólag a létrehozó aktuális engedélykészletének részhalmaza lehet.
Egy kérés akkor engedélyezett, ha a felhasználó szerepkörei és a token scope-ja
is tartalmazza az összes szükséges engedélyt. A token opcionálisan lejárathoz
köthető és azonnal visszavonható.

## Offline és folytatható feltöltés

A PWA a kiválasztott fájl Blobját, metaadatait és állapotát IndexedDB-ben
tárolja. Dokumentum és VRP-fájl kapcsolat nélkül is várólistára tehető. A
feldolgozás nem fut offline; újrakapcsolódáskor a kliens automatikusan indítja
vagy folytatja a szerveroldali feltöltési munkamenetet.

Folyamat:

1. A kliens egyedi `client_upload_id` értékkel és teljes fájlhash-sel létrehozza
   a munkamenetet.
2. A szerver visszaadja a darabméretet és a már megérkezett darabok listáját.
3. A kliens csak a hiányzó darabokat küldi, mindegyiket külön SHA-256 fejléccel.
4. Megszakításkor a helyi fájl és a szerveroldali darabok megmaradnak; folytatás
   ugyanazzal a kliensazonosítóval idempotens.
5. Lezáráskor a szerver összeállítja a fájlt, ellenőrzi a méretet és a teljes
   hash-t, majd átadja a már meglévő dokumentum- vagy VRP-validációnak.

```text
POST   /api/v1/uploads
GET    /api/v1/uploads?target_type=DOCUMENT|VRP
GET    /api/v1/uploads/{upload_id}
PUT    /api/v1/uploads/{upload_id}/chunks/{chunk_index}
POST   /api/v1/uploads/{upload_id}/complete
DELETE /api/v1/uploads/{upload_id}
```

A munkamenet alapértelmezett lejárata 72 óra, a darabméret 1 MiB. Ezek az
`APP_RESUMABLE_UPLOAD_EXPIRY_HOURS` és `APP_RESUMABLE_UPLOAD_CHUNK_MB`
változókkal állíthatók; a lejárat 1–720 óra, a darabméret 1–16 MiB lehet.

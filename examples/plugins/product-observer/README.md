# Product observer mintaplugin

Ez a minimális SDK-minta a `stock.changed` eseményre feliratkozva kiolvassa az
érintett terméket, majd `sample.stock.observed` eseményt bocsát ki.

A `backend/plugin.py` fájlt egy megbízható szervercsomagnak importálnia kell,
ezután a `manifest.json` az adminisztrátori Pluginok oldalon telepíthető. A
`products.read` és `settings.read` jogokat külön meg kell adni az engedélyezés
előtt.

Production pluginhoz egészítsd ki a dokumentáció szerinti `handlers.py`,
`schemas.py`, `migrations/`, `frontend/settings-panel/` és `tests/`
könyvtárakkal.

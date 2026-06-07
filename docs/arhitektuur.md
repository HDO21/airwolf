# Arhitektuur

## Äriküsimus

Kui tugev on statistiline seos õhukvaliteedi ning ilmastikutegurite (temperatuur, sademed, tuulekiirus) ja liiklussageduse vahel Eesti linnades? Eesmärk on tuvastada, milliste ilmastiku- ja liiklustingimuste koosesinemisel on õhukvaliteet kõige halvem. Õhukvaliteeti hinnatakse saasteainete (SO2, NO2, O3, PM10, PM2.5) kontsentratsiooni alusel — mida madalam kontsentratsioon, seda parem õhukvaliteet, mida kõrgem kontsentratsioon, seda halvem õhukvaliteet. Analüüs hõlmab kolme uurimispiirkonda — Tallinn, Tartu ja Narva — ning katab perioodi jaanuar 2025 kuni käesolev kuu.

## Uurimisküsimused

1. Kui tugev on seos õhusaasteainete kontsentratsiooni ja ilmastikutegurite (temperatuur, sademed, tuulekiirus) vahel Tallinna, Tartu ja Narva piirkonnas?

2. Kui tugev on seos õhusaasteainete kontsentratsiooni ja liiklussageduse vahel kolmes uurimispiirkonnas?

3. Kumb tegur — tuulekiirus või liiklussagedus — näitab tugevamat statistilist seost saasteainete kontsentratsiooniga, ja kas see erineb piirkonniti?

## Mõõdikud dashboardil

Dashboard on jagatud neljaks vahekaardiks: **Tallinn**, **Narva**, **Tartu** ja **Võrdlused**.

**Tallinn, Narva, Tartu** — iga linna vahekaart sisaldab nelja osa:
- Interaktiivne kaart (Leaflet + OpenStreetMap), kus on märgitud ilmavaatlusjaam (sinine), õhukvaliteedi seirejaam (punane) ja liikluse loenduspunkt (roheline) koos uurimisala piiriga.
- Tunnipõhised ilma- ja liiklusgraafikud valitud kuu lõikes: temperatuur ja sademed (kaheteljeliselt), tuulekiirus ning liiklussagedus koos üksikdetektorite vaadetega.
- Tunnipõhine õhukvaliteedi ajagraafik: SO2, O3, NO2, PM10 ja PM25 kontsentratsioonid (µg/m³) korraga ühel graafikul.
- Hajuvusdiagrammid SO2, PM10, PM2.5, NO2 ja O3 tunnikeskmiste kontsentratsioonide seosest liiklussageduse, temperatuuri, sademete ja tuulekiirusega. Iga diagramm sisaldab lineaarset trendjoont ja Pearson **r** korrelatsioonikordajat. Indikaator on kasutaja poolt valitav.

**Võrdlused** — kuukeskmised kontsentratsioonid kolme linna lõikes koos kõrgeima väärtusega kuu ja kontsentratsiooniga (µg/m³). Lisaks Pearson **r** korrelatsioonikordajad tuulekiiruse ja liiklussagedusega iga saasteaine ja linna kohta, koos automaatse järeldusega, kumb näitab tugevamat statistilist seost.

## Andmeallikad

| Allikas | Link | Tüüp | Ajas muutuv? | Roll |
| --- | --- | --- | --- | --- |
| `f_kliima_tund` (ilmavaatlused) | `https://keskkonnaandmed.envir.ee/f_kliima_tund` | Avalik HTTP API | Jah, uueneb iga tund | Tunnipõhised ilmavaatlused: temperatuur, sademed, tuulekiirus ja tuulesuund |
| `f_kliima_jaam_vaatlus` | `https://keskkonnaandmed.envir.ee/f_kliima_jaam_vaatlus` | Avalik HTTP API | Pigem aeglaselt muutuv | Ilmajaamade koordinaadid ja metaandmed |
| `ohuseire.ee` | `https://ohuseire.ee/api/monitoring/et` | Pool-avalik API (kasutusel EKUKi kaardirakenduses) | Jah, uueneb pidevalt | Õhukvaliteedi seireandmed: SO2, NO2, O3, PM10, PM2.5 |
| `traffic_detectors` MapServer | `https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer/0` | Avalik ArcGIS REST teenus | Jah, jooksev snapshot | Liiklusdetektorite tunnipõhised mõõtmised: liiklusvoog, raskeveokid, kiirus |
| Ajalooliste liiklussagedusandmete CSV | `https://andmed.eesti.ee/datasets/liiklusloenduse-andmed` | Kohalik sisendfail (CSV)| Ei | Ajalooline liiklussagedus, mis seotakse detektorite asukohtadega |
| Ajalooliste detektorite asukohtade fail | `https://andmed.eesti.ee/datasets/liiklusloenduse-andmed` | Kohalik sisendfail (CSV) | Ei | Detektorite koordinaadid ja nimed backfilli jaoks |
| OpenStreetMap | `https://www.openstreetmap.org` | Avalik kaardiandmestik | Jah | Aluskaart dashboardi kaardivaates |


### Andmeallikate kasutamise põhimõtted

- Projekti peamine analüüsitase on **tunnipõhine**, sest ilmavaatluste lähteallikas on `f_kliima_tund`.
- Ilmavaatlusandmeid kasutatakse kolmest jaamast: **Tallinn-Harku**, **Tartu-Tõravere** ja **Narva**.
- Õhukvaliteedi, ilmastiku ja liikluse andmed ühtlustatakse ühisele tunnitasemele, et nende omavahelisi seoseid saaks võrrelda samas ajavaates.
- Kui mõni andmeallikas on tunnitasemest detailsem või ebaühtlase ajasammuga, agregeeritakse või joondatakse see lähimale tunnisele vaatlusaknale.
- Projekti sisemine ruumiandmete referentssüsteem on **EPSG:3301**. Kaardivaates teisendatakse geomeetriad **EPSG:4326** formaati OpenStreetMapi jaoks.
- Analüüs teostatakse kolmel uurimisalal, mille piirid (BBOX) on:

| Ala | WGS84 NW nurk | WGS84 SE nurk | EPSG:3301 x_min | EPSG:3301 x_max | EPSG:3301 y_min | EPSG:3301 y_max |
|---|---|---|---:|---:|---:|---:|
| Tallinn | lat_n: 59.554594, lon_w: 24.474231 | lat_s: 59.361424, lon_e: 25.012994 | 526818 | 557609 | 6580812 | 6601992 |
| Narva | lat_n: 59.398837, lon_w: 28.099803 | lat_s: 59.342551, lon_e: 28.211009 | 732765 | 739464 | 6585793 | 6591660 |
| Tartu | lat_n: 58.426894, lon_w: 26.455566 | lat_s: 58.248549, lon_e: 26.780029 | 643432 | 663197 | 6459800 | 6478907 |


## Andmevoog

```mermaid
flowchart LR
    subgraph Sources[Andmeallikad]
        weather_api[f_kliima_tund\nf_kliima_jaam_vaatlus]
        aq_api[ohuseire.ee API]
        traffic_api[Tark Tee ArcGIS]
        traffic_csv[Liikluse CSV\n+ jaamade XLSX]
    end

    subgraph Ingest[1. Ingest — ingestion/]
        ingest_weather[ingest_weather.py\nbackfill + hourly]
        ingest_aq[ingest_air_quality.py\nbackfill + hourly]
        ingest_traffic_live[ingest_traffic.py\nlive/hourly]
        ingest_traffic_backfill[ingest_traffic.py\ncounts/backfill]
    end

    subgraph Staging[2. Staging — PostgreSQL]
        pipeline_runs[(staging.pipeline_runs)]
        stg_weather[(staging.weather_raw)]
        stg_aq[(staging.air_quality_raw)]
        stg_traffic_live[(staging.traffic_live_raw)]
        stg_traffic_counts[(staging.traffic_counts_raw)]
    end

    subgraph DBT[3. Transform + Mart — dbt]
        dbt_seed[dbt seed\nviitetabelid]
        dbt_run[dbt run\nmudelid]
        dbt_test[dbt test\nkvaliteedikontroll]
    end

    subgraph Presentation[4. Visualiseerimine]
        dashboard[streamlit_app.py\nlocalhost:8501]
    end

    subgraph Orchestration[Orkestreerimine]
        airflow[Airflow DAG\nairwolf_pipeline\n@hourly]
    end

    weather_api --> ingest_weather
    aq_api --> ingest_aq
    traffic_api --> ingest_traffic_live
    traffic_csv --> ingest_traffic_backfill

    ingest_weather --> stg_weather
    ingest_weather --> pipeline_runs
    ingest_aq --> stg_aq
    ingest_aq --> pipeline_runs
    ingest_traffic_live --> stg_traffic_live
    ingest_traffic_live --> pipeline_runs
    ingest_traffic_backfill --> stg_traffic_counts
    ingest_traffic_backfill --> pipeline_runs

    stg_weather --> dbt_seed
    stg_aq --> dbt_seed
    stg_traffic_live --> dbt_seed
    stg_traffic_counts --> dbt_seed
    dbt_seed --> dbt_run --> dbt_test

    dbt_run --> dashboard

    airflow --> ingest_weather
    airflow --> ingest_aq
    airflow --> ingest_traffic_live
    airflow --> ingest_traffic_backfill
    airflow --> dbt_seed
```

### Andmevoo selgitus

1. **Airflow DAG** (`dags/airwolf_pipeline.py`) orkestreerib kogu töövoo ja käivitub iga tund (`@hourly`). Iga jooksu staatus (käivitusaeg, allikas, tulemus) salvestatakse `staging.pipeline_runs` tabelisse.

2. **Ingest-skriptid** (`ingestion/`) laevad andmed staging skeemi:
   - `ingest_weather.py` — ilmavaatlused (`staging.weather_raw`); toetab backfilli ja tunnipõhist laadimist
   - `ingest_air_quality.py` — õhukvaliteedi andmed (`staging.air_quality_raw`); toetab backfilli ja tunnipõhist laadimist
   - `ingest_traffic.py` — liiklusdetektorite live-andmed (`staging.traffic_live_raw`) tunnipõhiselt ja ajaloolised CSV andmed (`staging.traffic_counts_raw`) backfillina
   - Kõik ingest-skriptid kasutavad UPSERT-i, seega korduvad käivitused ei tekita duplikaate

3. **dbt** transformeerib staging andmed mart-kihi mudeliteks:
   - `dbt seed` laeb viitetabelid (jaamade koordinaadid jm)
   - `dbt run` ehitab `intermediate` ja `marts` skeemi mudelid
   - `dbt test` jooksutab testid ja kontrollib andmekvaliteeti

4. **Streamlit dashboard** (`streamlit_app.py`) loeb mart-kihi tabeleid ja kuvab tulemused kolme vahekaardiga: **Mõõdistus- ja vaatlusandmed**, **Analüütika**, **Võrdlus**.

## Andmebaasi kihid

| Kiht | Skeem | Haldaja | Roll |
| --- | --- | --- | --- |
| `staging` | `staging` | `ingestion/` + `sql/create_tables.sql` | Hoiab API-dest ja CSV-failidest laetud toorandmeid allikalähedasel kujul koos laadimisaja ja pipeline'i metaandmetega |
| `intermediate` | `intermediate` | dbt | Hoiab standardiseeritud, puhastatud ja ruumiliselt/ajaliselt sobitatud vahetabeleid, mida kasutatakse mart-kihi sisendina |
| `marts` | `marts` | dbt | Hoiab analüüsiks ja dashboardiks vajalikke faktitabeleid ja koondeid |

### Kihtide kasutamise põhimõtted

- Iga pipeline'i käivitus saab unikaalse `run_id`, mis seob kõik sellel käivitusel laetud read `staging.pipeline_runs` tabeli kirjega.
- `staging` kihti ei kirjutata üle — UPSERT loogika tagab, et olemasolevad read uuendatakse ja uued lisatakse, ajalugu säilib.
- `intermediate` ja `marts` kihte haldab dbt — mudelid ehitatakse iga DAG käivitusega uuesti.
- Andmekvaliteedi kontrollid käivitab `dbt test` pärast `dbt run`-i. Tulemused logitakse Airflow task logidesse.
- Dashboard loeb ainult `marts` kihi tabeleid.


## Andmekvaliteedi kontrollid ('ingestion' ajal lokaalse töövoo puhul)

### Ilmaandmed (`weather_raw`)

- nõutud väljad: `jaam_kood`, `obs_time`, `lat`, `lon`
- vähemalt üks mõõteväli peab olema olemas: `temperature_c`, `wind_speed_ms`, `precip_mm`
- koordinaatide vahemikukontroll (`lat`, `lon`)
- temperatuur, tuulekiirus ja sademed peavad jääma mõistlikku vahemikku

### Õhukvaliteedi andmed (`air_quality_raw`)

- nõutud väljad: `station`, `indicator`, `measured`
- vähemalt üks saasteaine veerg peab olema olemas: SO2, O3, NO2, PM10, PM25
- saasteainete väärtused peavad olema mitte-negatiivsed
- koordinaatide vahemikukontroll (`lat`, `lon`)

### Liikluse live-andmed (`traffic_live_raw`)

- nõutud väljad: `traffic_detector_id`, `measurement_time`, `x_3301`, `y_3301`
- liiklusvood peavad olema mitte-negatiivsed
- EPSG:3301 koordinaadid peavad jääma Eesti jaoks mõistlikku vahemikku

### Liikluse backfill (`traffic_counts_raw`)

- nõutud väljad: `id`, `kanal`, `aeg`
- sõidukite loendused peavad olema mitte-negatiivsed
- `area` peab olema üks kolmest: `tallinn`, `tartu`, `narva`


## Andmekvaliteedi kontrollid (dbt testid)

Andmekvaliteedi kontrollid on realiseeritud dbt testidena. Testid käivitatakse Airflow töövoos automaatselt pärast `dbt run` sammu. Tulemused on nähtavad Airflow `dbt_test` taski logides.

Testid on tehtud peamiselt `intermediate` kihi mudelite peale, sest selles kihis on toorandmed juba puhastatud, ühtlustatud ja analüüsiks sobivale kujule viidud.

### Üldised dbt testid

Projektis kasutatakse `schema.yml` failis järgmisi teste:

- `not_null` — kontrollib, et olulised väljad ei oleks tühjad;
- `accepted_values` — kontrollib, et piirkonna (`area`) väärtused oleksid lubatud väärtuste hulgas.

Piirkonna lubatud väärtused on:

```text
tallinn
tartu
narva
```

Need testid aitavad tagada, et dashboardi filtrid ja vaated töötaksid ühtsete piirkonnanimedega ning et olulised identifikaatorid ja ajaväljad ei oleks puudu.

### Ilmaandmed (`int_weather`)

Ilmaandmete puhul kontrollitakse, et sama jaama sama mõõtmisaja kohta ei tekiks duplikaatridu.

Kontrollitav unikaalne kombinatsioon on:

```text
station_id + obs_time
```
Lisaks kontrollitakse väärtuste loogilisust:
- temperatuur vahemiku kontroll;
- tuulekiirus ja sademete hulk ei tohi olla negatiivne;
- koordinaatide vahemikukontroll (`lat`, `lon`)

### Õhukvaliteedi andmed (`int_air_quality`)

Õhukvaliteedi andmete puhul kontrollitakse, et sama jaama sama mõõtmisaja kohta ei tekiks duplikaatridu.

Kontrollitav unikaalne kombinatsioon on:

```text
station_id + obs_time
```
Lisaks kontrollitakse väärtuste loogilisust:
- õhukvaliteedi näitajad ei tohi olla negatiivsed
- koordinaatide vahemikukontroll (`lat`, `lon`)


### Liiklusandmed (`int_traffic`)

Liiklusandmete puhul kontrollitakse, et sama liiklusdetektori sama mõõtmisaja kohta ei tekiks duplikaatridu.

Kontrollitav unikaalne kombinatsioon on:

```text
detector_id + obs_time
```
Lisaks kontrollitakse väärtuste loogilisust:

- `total_flow` ehk liiklusvoog ei tohi olla negatiivne;
- laiuskraad peab jääma vahemikku `57 kuni 60.5`;
- pikkuskraad peab jääma vahemikku `21 kuni 29`.


### Kokkuvõte

Andmekvaliteedi kontrollid hõlmavad nelja põhitüüpi:

1. **Tühjade väärtuste kontroll** — olulised väljad ei tohi olla `NULL`.
2. **Lubatud väärtuste kontroll** — `area` peab olema üks väärtustest `tallinn`, `tartu` või `narva`.
3. **Duplikaatide kontroll** — sama jaama või detektori sama mõõtmisaja kohta ei tohi olla mitu rida.
4. **Väärtusvahemike kontroll** — mõõteväärtused ja koordinaadid peavad jääma loogilistesse piiridesse.

Kui mõni test tagastab ridu, loeb dbt testi ebaõnnestunuks ning Airflow märgib `dbt_test` taski läbikukkunuks. See aitab probleemid andmetes enne dashboardi kasutamist üles leida.

## Tööjaotus

| Vastutusala | Tegevused | Tegija |
| --- | --- | --- |
| Keskkonnaandmed ja liiklusandmed | Ilmavaatluste (`f_kliima_tund`, `f_kliima_jaam_vaatlus`), õhukvaliteedi ja liiklusandmete (`ingest_traffic.py`) päringute ja sissevõtu haldamine | Katrin |
| Transformatsioonid | dbt mudelite (`intermediate` ja `marts`) ehitamine, ruumilise sidumise loogika ja KPI arvutused | Katrin |
| Andmekvaliteet | Andmekvaliteedi testide (`dbt test`) loomine, ebaõnnestumiste jälgimine ja logide kontroll | Hando/ Katrin |
| Analüüs | Andmete analüüs, graafikud, korrelatsioonid | Hele |
| Dashboard | Streamlit rakenduse, kaardivaate ja kasutajaliidese arendamine | Hando |
| Dokumentatsioon | Arhitektuuridokumendi (`docs/arhitektuur.md`) ja README ajakohastamine | Hanna |


## Riskid

| Risk | Maandus |
| --- | --- |
| API muudab vastuse formaati → pipeline katkeb | Versioonikontroll ja alertid |
| `ohuseire.ee` pool-avalik API läheb kinni → andmed puuduvad | Alternatiivne allikas puudub, risk aktsepteeritud |
| Liiklusdetektori andmed on hetktõmmis, mitte ajaline rida → tunnipõhine kogumine võib jätta lünki | Backfill CSV-ga |
| Staging tabelid kasvavad liiga suureks → jõudlusprobleemid | Partitsioneerimine või arhiveerimine |
| Ruumiline sobitamine 5 km raadiuses sobitab vale detektori → vale seos | Visuaalne kontroll kaardil |
| Koordinaadid puuduvad mõnel detektoril → jäetakse analüüsist välja | Käsitsi täiendamine |
| DuckDB/pgDuckDB versioon ei ühildu PostgreSQL versiooniga → installimisviga | Lukustatud versioonid `compose.yml`-is |
| Dashboard näitab valesid tulemusi vaiksetel perioodidel (vähe andmeid) → kasutaja teeb valesid järeldusi | Andmete arvu kuvamine |
| Projekti andmeperiood on liiga lühike korrelatsioonide usaldatavaks hindamiseks | Andmete kogumine jätkub |
| Streamlit Community Cloud piirab mälu ja CPU ressursse → dashboard muutub aeglaseks või katkeb suure andmemahu korral | Jälgida ressursikasutust; kaaluda andmemahu piiramist dashboard tasandil |

## Privaatsus ja turvalisus

- Kõik andmeallikad on avalikud — isikuandmeid ei koguta.
- Andmebaasi paroolid ja ühendusandmed hoitakse `.env` failis, mitte koodis.
- `.env` fail on `.gitignore`-s ja ei tohi repo-sse sattuda.
- `ohuseire.ee` API ei nõua autentimist, kuid on pool-avalik — kasutada mõistlikult ja vältida tarbetuid päringuid.
- Liikluse sisendfailid (`LL jaamad.xlsx`, liikluse CSV-d) on kohalikud failid — hoida väljaspool versioonihallatavat kausta ja mitte lisada repo-sse.

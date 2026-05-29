# Arhitektuur

## Äriküsimus

Kas, kuidas ja millisel määral sõltuvad Eesti asulates (Tallinn, Tartu ja Narva) mõõdetud SO2, PM10, PM2.5, NO2 ja O3 kontsentratsioonid ilmastikunähtustest (nt tuul, sademed, temperatuur) ning liiklussagedusest? Millistes Eesti asulates ja mis aegadel tagab ilmastiku ning liiklussageduse koosmõju kõige puhtama/saastatuma õhukvaliteedi?

Kuna 2026. aasta õhukvaliteedi mõõtmiste andmeid ei ole veel avalikustatud, tehakse esialgne PoC 2025. aasta kohta.

## Mõõdikud

1. **Saasteaine kontsentratsiooni seose tugevus ilmastikuteguritega**  
   SO2, PM10, PM2.5, NO2 ja O3 tunnikeskmiste või päevakeskmiste kontsentratsioonide seos tuulekiiruse, tuulesuuna, temperatuuri ja sademetega. Näidatakse korrelatsiooni, regressioonikordaja või muu mõju suuruse näitajana asula ja perioodi lõikes.

2. **Saasteaine kontsentratsiooni seose tugevus liiklussagedusega**  
   SO2, PM10, PM2.5, NO2 ja O3 kontsentratsiooni muutus liiklusvoo, raskeveokite osakaalu ja võimalusel keskmise kiiruse muutumisel.

3. **Kõrge saastetaseme episoodid ja neid saatvad tingimused**  
   Tundide või päevade arv, mil valitud saasteaine tase ületab kokkulepitud lävendi, ning millised ilma- ja liiklustingimused nende episoodidega kaasnesid.

4. **Piirkondlik riskiskoor või koondnäitaja**  
   Koondnäitaja, mis iseloomustab, millistes piirkondades ja tingimustes on kõrgema saastetaseme risk suurim.

### Võimalikud KPI-d dashboardil

- SO2, PM10, PM2.5, NO2 ja O3 keskmine kontsentratsioon valitud asulas/perioodil (näidata punasega kui on üle lubatud piirnormi)
- Korrelatsioon tuule, temperatuuri, sademete ja liiklussagedusega
- Vähese/kõrge saastetasemega päevade või tundide arv
- Ilma vs liikluse suhteline mõju valitud saasteainele


# Andmeallikad

| Allikas | Link | Tüüp | Ajas muutuv? | Roll |
|---|---|---|---|---|
| `f_kliima_tund` (`Ilmavaatlused`) | `https://keskkonnaandmed.envir.ee/f_kliima_tund` | Avalik HTTP API | Jah, ajas muutuv vaatluste andmestik | Tunnipõhised ilmavaatlused: temperatuur, sademed ja tuul; kasutatakse õhukvaliteedi ja liiklusandmete sidumiseks ühisel tunnitasemel |
| `f_kliima_jaam_vaatlus` | `https://keskkonnaandmed.envir.ee/f_kliima_jaam_vaatlus` | Avalik HTTP API | Pigem aeglaselt muutuv | Ilmajaamade asukohtade allikas |
| `ohuseire.ee` | `https://ohuseire.ee/api/monitoring/et` | Pool-avalik API (kasutusel EKUKi kaardirakenduses) | Jah, uueneb pidevalt | Õhukvaliteedi seireandmed: SO2, PM10, PM2.5, NO2, O3 ja seotud mõõtepunktid |
| `traffic_detectors` MapServer | `https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer` | Avalik ArcGIS REST teenus | Jah, teenus kuvab jooksvaid mõõtmisi | Liiklusdetektorite mõõtmised ja asukohad; kasutatakse liiklusvoo, raskeveokite osakaalu ja kiiruse näitajate jaoks |
| Ajalooliste liiklussagedusandmete CSV backfill | Algallikas: `https://andmed.eesti.ee/datasets/liiklusloenduse-andmed` | Kohalik sisendfail | Ei | Ajalooline info, mis seotakse liiklussagedusdetektorite ruumiandmetega |
| Ajalooliste liiklussagedusandmete mõõdistuspunktide asukohtade backfill | Algallikas: `https://andmed.eesti.ee/datasets/liiklusloendusseadmed` | Kohalik sisendfail | Ei | Ajalooline info, mis seotakse mõõdistusandmetega |
| OpenStreetMap | `https://www.openstreetmap.org` | Avalik kaardiandmestik / aluskaart | Jah | Aluskaart ja kaardiaken Streamlitis |

### Andmeallikate kasutamise põhimõtted

- Kuna 2026. aasta õhukvaliteedi mõõtmiste andmeid ei ole veel avalikustatud, tehakse esialgne PoC 2025. aasta kohta.
- Projekti peamine analüüsitase on **MVP-s tunnipõhine**, sest ilmavaatluste lähteallikas on `f_kliima_tund`.
- Esialgne töövoog kasutab ilmavaatlusandmeid kolmest ilmajaamast: **Tallinn-Harku**, **Tartu-Tõravere** ja **Narva**.
- Õhukvaliteedi, ilmastiku ja liikluse andmed ühtlustatakse võimalusel ühisele tunnitasemele, et nende omavahelisi seoseid saaks võrrelda samas ajavaates.
- Kui mõni andmeallikas on tunnitasemest detailsem või ebaühtlase ajasammuga, agregeeritakse või joondatakse see lähimale sobivale tunnisele vaatlusaknale.
- Projekti sisemine ruumiandmete referentssüsteem on **EPSG:3301**. Streamliti kaardivaates teisendatakse geomeetriad vajadusel **EPSG:4326** formaati, et need kuvataks korrektselt OpenStreetMapi kaardil.
- Projektis teostatakse analüüs kolmel näidisalal, mille BBOX koordinaadid on:

| Ala | WGS84 NW nurk | WGS84 SE nurk | EPSG:3301 x_min | EPSG:3301 x_max | EPSG:3301 y_min | EPSG:3301 y_max |
|---|---|---|---:|---:|---:|---:|
| Tallinn | lat_n: 59.554594, lon_w: 24.474231 | lat_s: 59.361424, lon_e: 25.012994 | 526818 | 557609 | 6580812 | 6601992 |
| Narva | lat_n: 59.398837, lon_w: 28.099803 | lat_s: 59.342551, lon_e: 28.211009 | 732765 | 739464 | 6585793 | 6591660 |
| Tartu | lat_n: 58.426894, lon_w: 26.455566 | lat_s: 58.248549, lon_e: 26.780029 | 643432 | 663197 | 6459800 | 6478907 |

## Andmevoog

```mermaid
flowchart LR
    subgraph Sources[Andmeallikad]
        weather_hourly[f_kliima_tund]
        weather_meta[f_kliima_jaam_vaatlus]
        aq_api[ohuseire.ee API]
        traffic_api[traffic_detectors MapServer/0]
        traffic_csv[Ajalooline liikluse CSV]
        traffic_sites[Ajalooliste mõõdistuspunktide fail]
        osm[OpenStreetMap]
    end

    subgraph Ingest[1. Ingest / staging]
        ingest_weather[ingest_weather.py]
        ingest_aq[ingest_air_quality.py]
        ingest_traffic_live[ingest_traffic.py --mode live]
        ingest_traffic_backfill[ingest_traffic.py --mode backfill]
        stg_weather[(data/staging/weather_raw_YYYY_MM.parquet)]
        stg_weather_meta[(data/staging/weather_stations.parquet)]
        stg_aq[(data/staging/air_quality_raw_YYYY_MM.parquet)]
        stg_traffic_live[(data/staging/traffic_live_TIMESTAMP.parquet)]
        stg_registry[(data/staging/traffic_detector_registry.parquet)]
        stg_traffic_backfill[(data/staging/traffic_backfill.parquet)]
    end

    subgraph Transform[2. Transform / intermediate]
        transform[run_transform.py]
        validate[validate.py]
        int_weather[(data/intermediate/weather_YYYY_MM.parquet)]
        int_aq[(data/intermediate/air_quality_YYYY_MM.parquet)]
        int_traffic[(data/intermediate/traffic.parquet)]
    end

    subgraph Mart[3. Mart]
        build_mart[run_mart.py]
        mart_weather[(data/mart/mart_weather.parquet)]
        mart_aq[(data/mart/mart_aq.parquet)]
        mart_traffic[(data/mart/mart_traffic.parquet)]
        dim_stations[(data/mart/dim_stations.parquet)]
    end

    subgraph Orchestration[Orkestreerimine]
        pipeline[run_pipeline.py]
        stamp[_last_updated.txt]
        airflow["Airflow / scheduler<br>planeeritud / osaliselt seadistatud"]
    end

    subgraph Presentation[4. Visualiseerimine]
        dashboard[streamlit_app.py]
    end

    weather_hourly --> ingest_weather
    weather_meta --> ingest_weather
    aq_api --> ingest_aq
    traffic_api --> ingest_traffic_live
    traffic_csv --> ingest_traffic_backfill
    traffic_sites --> ingest_traffic_backfill

    ingest_weather --> stg_weather
    ingest_weather --> stg_weather_meta
    ingest_aq --> stg_aq
    ingest_traffic_live --> stg_traffic_live
    ingest_traffic_live --> stg_registry
    ingest_traffic_backfill --> stg_traffic_backfill

    stg_weather --> transform
    stg_weather_meta --> transform
    stg_aq --> transform
    stg_traffic_backfill --> transform
    stg_registry --> transform

    transform --> validate
    transform --> int_weather
    transform --> int_aq
    transform --> int_traffic

    int_weather --> build_mart
    int_aq --> build_mart
    int_traffic --> build_mart
    stg_weather_meta --> build_mart
    stg_registry --> build_mart

    build_mart --> mart_weather
    build_mart --> mart_aq
    build_mart --> mart_traffic
    build_mart --> dim_stations

    mart_weather --> dashboard
    mart_aq --> dashboard
    mart_traffic --> dashboard
    dim_stations --> dashboard
    stamp --> dashboard
    osm --> dashboard

    pipeline --> ingest_weather
    pipeline --> ingest_aq
    pipeline --> ingest_traffic_live
    pipeline --> ingest_traffic_backfill
    pipeline --> transform
    pipeline --> build_mart
    pipeline --> stamp
    airflow -. tulevikus .-> pipeline
```

### Andmevoo selgitus

1. `run_pipeline.py` orkestreerib töövoo: ingest → transform → mart → viimase uuenduse ajatempel.  
2. Ingest-skriptid kirjutavad allikalähedased toorandmed `data/staging` kihti:
   - `ingest_weather.py` salvestab ilmavaatlused kuupõhiselt ja ilmajaamade metaandmed eraldi;
   - `ingest_air_quality.py` salvestab õhukvaliteedi toorandmed kuupõhiselt;
   - `ingest_traffic.py --mode live` salvestab live-snapshot'i ja uuendab detektorite registrit;
   - `ingest_traffic.py --mode backfill` salvestab ajaloolise liiklus-CSV backfilli.
3. `run_transform.py` loeb `staging` kihist andmed, normaliseerib need ja kirjutab `data/intermediate` kihti:
   - ilm ja õhukvaliteet kuupõhistesse failidesse;
   - liikluse üksikute sõiduridade backfill ühendatakse detektoriregistriga ja agregeeritakse tunnitasemele faili `traffic.parquet`.
4. `validate.py` käivitatakse transformatsiooni käigus iga allika standardiseeritud väljundi peal. Kvaliteedikontrollide tulemusi praegu eraldi tabelisse ei kirjutata, vaid need logitakse jooksu väljundisse.
5. `run_mart.py` koondab `intermediate` kihi failid dashboardi jaoks sobivatesse `mart` kihtidesse:
   - `mart_weather.parquet`
   - `mart_aq.parquet`
   - `mart_traffic.parquet`
   - `dim_stations.parquet`
6. Streamlit dashboard loeb praegu `mart` kihti, mitte live-API-sid otse. Kaardivaade kasutab `dim_stations.parquet` faili ning ajagraafikud loevad `mart_*` faile.
7. `data/staging/_last_updated.txt` salvestab viimase eduka pipeline-jooksu ajatembli ja kuvatakse dashboardil.
8. Airflow ja andmebaasi konteinerid on projektis ette valmistatud, kuid praegune PoC töötab failipõhise pipeline'ina ning automaatne scheduler ei ole veel töövoo keskne osa.

## Andmebaasi kihid

| Kiht | Roll |
|---|---|
| `staging` | Hoiab API-dest saadud toorandmeid võimalikult allikalähedasel kujul koos laadimisaja ja tehnilise metaandmestikuga. |
| `intermediate` | Hoiab standardiseeritud, ühtlustatud, puhastatud ja ruumiliselt/ajaliselt sobitatud vahetabeleid, mida kasutatakse analüüsi- ja mart-kihi sisendina. |
| `mart` | Hoiab analüüsiks ja dashboardiks vajalikke faktitabeleid, koondeid, episoodide tabeleid ja seoseanalüüsi tulemusi. |
| `quality` | Hoiab andmekvaliteedi kontrollide tulemusi, jooksutuste staatust ja võimalikke vigade logisid. |


### Kihtide kasutamise põhimõtted

- Iga töövoo käivitus saab unikaalse `run_id`.
- `staging` kihti ei kirjutata üle, vaid sinna jäävad alles ajaloo jooksul laetud andmed auditiks ja backfilliks.
- `mart` kihi tabelid võib ehitada igal käivitusel uuesti või inkrementaalselt, sõltuvalt andmemahust.
- Dashboard loeb ainult viimase eduka töövoo tulemusi.

## Andmekvaliteedi kontrollid

Vähemalt järgmised kontrollid tehakse automaatselt:

### Ilmaandmed (`weather`)
- nõutud väljad: `jaam_kood`, `obs_time`, `lat`, `lon`
- vähemalt üks mõõteväli peab olema olemas: `temperature_c`, `wind_speed_ms`, `precip_mm`
- koordinaatide vahemikukontroll (`lat`, `lon`)
- temperatuur, tuulekiirus ja sademed peavad jääma mõistlikku vahemikku

### Õhukvaliteedi andmed (`air_quality`)
- nõutud väljad: `seirekoha_kood`, `obs_time`, `lat`, `lon`, `area`
- vähemalt üks saasteaine veerg peab olema olemas: `SO2`, `O3`, `NO2`, `PM10`, `PM25`
- saasteainete väärtused peavad olema mitte-negatiivsed
- koordinaatide vahemikukontroll (`lat`, `lon`)

### Liikluse live-andmed (`traffic_live`)
- nõutud väljad: `traffic_detector_id`, `measurement_time`, `x_3301`, `y_3301`
- liiklusvood peavad olema mitte-negatiivsed
- EPSG:3301 koordinaadid peavad jääma Eesti jaoks mõistlikku vahemikku

### Liikluse backfill (`traffic_backfill`)
- nõutud väljad: `id`, `aeg`
- `total_flow` peab olema mitte-negatiivne
- `heavy_vehicle_share` peab jääma vahemikku 0…1

## Tööjaotus

| Roll | Vastutus | Omanik |
|---|---|---|
| Keskkonnaandmete omanik | Kontrollib `f_kliima_tund`, `õhukvaliteet` ja `f_kliima_jaam_vaatlus` päringuid, sissevõttu ja ilmavaatluste standardiseerimist | Katrin |
| Liiklusandmete omanik | Vastutab `traffic_detectors` päringute, API-võtme kasutuse ja liiklusandmete normaliseerimise eest | Hanna |
| Transformatsioonide omanik | Ehitab `core` ja `mart` kihi mudelid, ruumilise sidumise loogika ja KPI arvutused | Hele |
| Kvaliteedi omanik | Loob andmekvaliteedi testid (`validate.py`), jälgib ebaõnnestumisi ja kontrollib logisid | Hando | 
| Dashboardi omanik | Arendab Streamlit rakendust, kaardivaadet ja kasutajaliidest | Hando |


## Riskid

| Risk | Mõju | Maandus |
|---|---|---|
| API ei vasta või päring ebaõnnestub | Andmed ei uuene ja dashboard võib kuvada aegunud seisu | Skript logib vea, teeb piiratud arv kordi korduspäringuid ja jätab alles viimase eduka laadimise. Dashboardil kuvatakse viimase eduka uuenduse aeg. |
| Lähteandmete struktuur muutub | Töövoog katkeb või osa välju jääb laadimata | Skeemivalideerimine kontrollib kohustuslike väljade olemasolu enne edasist töötlust. Vigane laadimine märgitakse ebaõnnestunuks. |
| Eri andmestike ruumiline jaotus on väga erinev | Seoseanalüüsi ei saa kõigis piirkondades usaldusväärselt teha | PoC tehakse esmalt suuremate linnade või valitud näidisalade põhjal, kus õhukvaliteedi, ilma ja liikluse kattuvus on parem. |
| Eri andmeallikate ajasamm ei ühti | Analüüs võib anda eksitavaid tulemusi või sidumisel kaob suur osa vaatlustest | Kõik andmed joondatakse ühtsele tunnitasemele. Ebaregulaarse ajasammuga andmete puhul kasutatakse eeldefineeritud joondusreegleid ja salvestatakse sidumise kvaliteedinäitajad. |
| Liiklusallikates puudub piisav ajalooline sügavus | Liikluse mõju ei saa pikema perioodi kohta hinnata | Luua oma ajalugu regulaarse sissevõtuga staging kihti. Kui ajalugu on lühike, sõnastatakse tulemused PoC ja piiratud perioodi analüüsina. |
| Ajastatud toiming ei käivitu | Andmed ei uuene automaatselt | Scheduler kontrollib eelmiste jooksude staatust, toetab backfilli ning logib ebaõnnestumised eraldi. |
| Eri lähteandmestikud uuenevad eri sagedusega | Koondtulemused võivad põhineda eri värskusega andmetel | Iga allika jaoks hoitakse eraldi laadimisajatemplit ja analüüsi tehakse ainult ajaperioodil, kus andmete olemasolu on piisav. |
| Streamlit dashboard lülitub välja või muutub kättesaamatuks | Kasutaja ei näe analüüsi tulemusi | Kuvatakse viimase eduka laadimise aeg, hoitakse rakendus võimalikult kergena ning lisatakse lihtne tervisekontrolli mehhanism. |
| Sisendallikate vahel ei ilmne tugevat seost | Tulemused ei anna oodatud lisateadmist | Projekti fookus on esmalt piiratud saasteainete ja piirkondade valimil. Dashboard peab näitama ka “nõrga seose” tulemust, mitte ainult positiivseid leide. |
| Andmeallikates on palju puuduvaid, vigaseid või ebaloogilisi väärtusi | KPI-d ja analüüsi tulemused võivad olla valed või kallutatud | Rakendatakse kvaliteeditestid: not null, vahemikukontrollid, ajatemplite kontroll, dublikaatide kontroll ja koordinaatide kehtivuse kontroll. Vigased read märgitakse või jäetakse analüüsist välja. |
| Teenuste päringumahud või piirangud takistavad suure mahu laadimist | Kõiki vajalikke andmeid ei saa ühe korraga kätte | Päringud tehakse ajavahemike, piirkondade ja filtrite kaupa. Sissevõtt on inkrementaalne ning suurte perioodide puhul kasutatakse osade kaupa laadimist. |

## Privaatsus ja turve

Projekt kasutab avalikult kättesaadavaid andmeid. Töö käigus isikuandmeid ei koguta ega töödelda. Kõik teenuste võtmed, kasutajanimed ja muud saladused hoitakse `.env` failis ning neid ei lisata Git repositooriumisse. Repos hoitakse ainult `.env.example` faili. DATEX API-võti on käsitletud konfidentsiaalse saladusena, kuigi ülejäänud lähteandmed on avalikud.
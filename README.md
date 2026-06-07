# Õhuhunt — Eesti õhukvaliteedi analüütika

*Andmetoru, mis kõnetab su hingetoru*

## Äriküsimus

Kui tugev on statistiline seos õhukvaliteedi ning ilmastikutegurite (temperatuur, sademed, tuulekiirus) ja liiklussageduse vahel Eesti linnades? Eesmärk on tuvastada, milliste ilmastiku- ja liiklustingimuste koosesinemisel on saasteainete kontsentratsioon õhus kõige madalam või kõige kõrgem. Õhukvaliteeti hinnatakse saasteainete (SO2, NO2, O3, PM10, PM2.5) kontsentratsiooni alusel — mida madalam kontsentratsioon, seda parem õhukvaliteet. Analüüs hõlmab kolme uurimispiirkonda — Tallinn, Tartu ja Narva — ning katab perioodi jaanuar 2025 kuni käesolev kuu.

Tulemused on nähtavad dashboardil: [est-air-quality-monitor.streamlit.app](https://est-air-quality-monitor.streamlit.app)

**Mõõdikud:**

1. Saasteaine kontsentratsiooni seos liiklussageduse ja ilmastikuteguritega — hajuvusdiagrammid Pearson **r** korrelatsioonikordajaga iga linna vahekaardil
2. Kõige saastatum kuu — iga saasteaine ja linna kohta kõrgeima kuukeskmise kontsentratsiooniga kuu (µg/m³)
3. Tuulekiiruse ja liiklussageduse korrelatsioon saasteainetega — automaatne järeldus, kumb näitab tugevamat statistilist seost

## Arhitektuur

```mermaid
flowchart LR
    source[Andmeallikad] --> ingest[ingestion/]
    ingest --> staging[(staging)]
    staging --> dbt[dbt run]
    dbt --> mart[(marts)]
    mart --> dashboard[Streamlit dashboard]
```

## Andmeallikad

| Allikas | Tüüp | Ajas muutuv? | Roll |
| --- | --- | --- | --- |
| [f_kliima_tund](https://keskkonnaandmed.envir.ee/f_kliima_tund) | Avalik HTTP API | Jah, iga tund | Tunnipõhised ilmavaatlused (temperatuur, sademed, tuulekiirus) |
| [ohuseire.ee](https://ohuseire.ee/api/monitoring/et) | Pool-avalik API | Jah, pidevalt | Õhukvaliteedi seireandmed (SO2, NO2, O3, PM10, PM2.5) |
| [Tark Tee](https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer) | Avalik ArcGIS REST | Jah, iga tund | Liiklusdetektorite tunnipõhised mõõtmised |
| [Liikluseloenduste ajaloolised andmed](https://andmed.eesti.ee/datasets/liiklusloenduse-andmed) | Kohalik csv sisendfail | Ei, staatiline | Ajalooline liiklussagedus backfilli jaoks |

## Stack

| Komponent | Tööriist |
| --- | --- |
| Sissevõtt | Python (`ingestion/`) |
| Transformatsioon | dbt |
| Andmehoidla | PostgreSQL + DuckDB |
| Näidikulaud | Streamlit + Altair + Folium |
| Orkestreerimine | Apache Airflow (`@hourly`) |
| Keskkond | Docker Compose |

## Käivitamine

    # 1. Kopeeri keskkonnamuutujad
    cp .env.example .env
    
    # 2. Lae alla liiklusloenduste failid https://andmed.eesti.ee/ keskkonnast ja salvesta õige kausta alla
    * traffic_2025.csv ja traffic_2026.csv      -> data/raw/traffic/counts
    * LL_jaamad.csv                             -> data/raw/traffic/stations
      
    # 3. Käivita kõik teenused
    docker compose up -d --build

    # 4. Ava Airflow UI Airflow UI: http://localhost:8080
    Käivita DAG "airwolf_pipeline" koos backfillidega (andmed sisesta alates 1.jaanuar 2025)

    # 5. Ava Streamlit http://localhost:8501 ja uudista

## Saladused ja konfiguratsioon

Kõik saladused (paroolid, andmebaasi URL-id) on `.env` failis. Repos on ainult `.env.example`, mis näitab vajalike muutujate struktuuri ilma tegelike väärtusteta. Päris `.env` faili ei tohi GitHubi panna — see on `.gitignore`-s.

| Muutuja | Tähendus |
| --- | --- |
| `POSTGRES_PASSWORD` | PostgreSQL parool |
| `TRAFFIC_BACKFILL_CSV` | Liikluse ajalooliste andmete CSV faili tee |
| `TRAFFIC_STATIONS_FILE` | Liiklusdetektorite asukohtade faili tee (CSV või XLSX) |
| `MATCH_RADIUS_METERS` | Jaamade ja detektorite geograafilise sobitamise raadius (vaikimisi 5000) |

## Andmevoog lühidalt

1. **Sissevõtt** — `ingestion/` skriptid laevad tunnipõhised andmed kolmest allikast (ilm, õhukvaliteet, liiklus) PostgreSQL `staging` skeemi. Airflow DAG käivitab sissevõtu automaatselt iga tund.
2. **Laadimine** — Andmed salvestatakse `staging` kihti UPSERT loogikaga — korduvad käivitused ei tekita duplikaate.
3. **Transformatsioon** — dbt mudelid puhastavad, standardiseerivad ja sobitavad andmed ruumiliselt ning ajaliselt `intermediate` ja `marts` skeemidesse.
4. **Testimine** — `dbt test` käivitab andmekvaliteedi kontrollid automaatselt pärast iga transformatsiooni. Tulemused logitakse Airflow task logidesse.
5. **Näidikulaud** — Streamlit rakendus loeb `marts` kihi tabeleid ja kuvab tulemused neljal vahekaardil: Tallinn, Narva, Tartu ja Võrdlused.

## Andmekvaliteedi testid

Testid käivitab `dbt test` automaatselt pärast iga `dbt run`-i. Tulemused logitakse Airflow task logidesse.

1. `station_id` ja `detector_id` ei ole null — kõigis kolmes intermediate mudelis
2. `obs_time` ei ole null — kõigis mudelites
3. `area` on üks kolmest lubatud väärtusest: `tallinn`, `tartu`, `narva` — kõigis intermediate mudelites
4. `mart_joined.area` ja `mart_joined.obs_time` ei ole null — dashboardi peamise sisendtabeli kontroll

## Projekti struktuur

```text
AIRWOLF/
├── archive_old_pipeline/          ← vana lokaalne töövoog Parquet-failide põhjal
│
├── dags/                          ← Airflow DAG-ide kaust
│   └── airwolf_pipeline.py        ← põhitöövoog: loob tabelid, laeb andmed, käivitab dbt mudelid ja testid
│
├── data/                          ← failipõhiste andmete kaust
│   └── raw/                       ← algsed toorandmed failidena
│
├── dbt_project/                   ← dbt projekt andmete transformeerimiseks ja testimiseks
│   ├── macros/                    ← dbt makrod ehk korduvkasutatavad abifunktsioonid
│   ├── models/                    ← dbt SQL-mudelid ehk transformatsioonid
│   ├── seeds/                     ← CSV referentstabelid, nt ilma- ja õhukvaliteedijaamad
│   ├── tests/                     ← aktiivsed dbt andmekvaliteedi testid
│   ├── tests_disabled/            ← testid, mis on olemas, aga mida hetkel ei käivitata
│   ├── dbt_project.yml            ← dbt projekti põhiseadistus
│   └── profiles.yml               ← dbt andmebaasiühenduse seadistus
│
├── docs/                          ← projekti dokumentatsioon
│   ├── arhitektuur.md             ← projekti arhitektuuri kirjeldus
│   └── progress.md                ← projekti edenemise ja tehtud tööde kirjeldus
│
├── ingestion/                     ← andmete laadimise Pythoni skriptid
│   ├── ingest_air_quality.py      ← õhukvaliteedi andmete laadimine
│   ├── ingest_traffic.py          ← liiklusandmete laadimine
│   └── ingest_weather.py          ← ilmaandmete laadimine
│
├── sql/                           ← andmebaasi tabelite loomise SQL-failid
│   └── create_tables.sql          ← staging toortabelite loomine
│
├── .env.example                   ← näidis keskkonnamuutujate fail; kopeeritakse lokaalselt .env failiks
├── .gitignore                     ← määrab, milliseid faile Git ei jälgi
├── compose.yml                    ← Docker Compose seadistus, mis käivitab andmebaasi, Airflow ja dashboardi
├── Dockerfile.airflow             ← Airflow konteineri ehitusfail koos vajalike Python/dbt sõltuvustega
├── Dockerfile.app                 ← Streamlit dashboardi konteineri ehitusfail
└── streamlit_app.py               ← Streamlit dashboardi põhifail
```

## Kokkuvõte, puudused ja võimalikud edasiarendused

Uurisime seost nii liiklussageduse kui ka ilmastikunähtustega. Esialgne analüüs viitab suuremat seost pigem ilmastikuga, eriti tuulekiirusega, kui liiklusega. Nagu kaartidelt nähtub, on eri näitajate mõõdistuspunktid eri asukohtadega ja nende paiknemistihedus varieerub, siis peab arvestama võimalikest ruumilistest variatsioonidest tulenevate tulemuste ebatäpsuse või moonutusega. võimalik, et liiklusest tingitud keskkonnamõjud on loomult liiga lokaalsed, et üldmõõdistusi märkimisväärselt mõjutada.

## Dokumentatsioon

Täpsem ülevaade arhitektuurist, andmevoogudest, mõõdikutest ja tööjaotusest: [docs/arhitektuur.md](docs/arhitektuur.md)

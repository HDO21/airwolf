# Õhuhunt — Eesti õhukvaliteedi analüütika

*Andmetoru, mis kõnetab su hingetoru*

## Mis see on?

Projekt uurib statistilisi seoseid Eesti linnade õhukvaliteedi ning ilmastiku (temperatuur, sademed, tuulekiirus) ja liiklussageduse vahel. Õhukvaliteeti hinnatakse saasteainete (SO2, NO2, O3, PM10, PM2.5) kontsentratsiooni alusel kolmes linnas — Tallinnas, Tartus ja Narvas — alates jaanuarist 2025.

Tulemused on nähtavad dashboardil: [est-air-quality-monitor.streamlit.app](https://est-air-quality-monitor.streamlit.app)

## Andmeallikad

| Allikas | Kirjeldus |
| --- | --- |
| [Keskkonnaandmed](https://keskkonnaandmed.envir.ee/f_kliima_tund) | Tunnipõhised ilmavaatlused (temperatuur, sademed, tuulekiirus) |
| [Ohuseire](https://ohuseire.ee/api/monitoring/et) | Õhukvaliteedi seireandmed (SO2, NO2, O3, PM10, PM2.5) |
| [Tark Tee](https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer) | Liiklusdetektorite mõõtmised live-s|
| [Liiklusloenduste andmed](https://andmed.eesti.ee/datasets/liiklusloenduse-andmed) | Liiklusdetektorite mõõtmiste ajalugu |
| 

## Tehnoloogiad

- **Python** — andmete laadimine ja töötlus
- **Apache Airflow** — igapäevane automatiseerimine
- **PostgreSQL + dbt** — andmebaas ja transformatsioonid
- **Streamlit + Altair + Folium** — dashboard
- **Docker Compose** — kogu keskkond konteinerites

## Projekti struktuur

```text
AIRWOLF/
├── archive_old_pipeline/          ← vana lokaalne töövoog Parquet-failide põhjal
│
├── dags/                          ← Airflow DAG-ide kaust
│   └── airwolf_pipeline.py        ← põhitöövoog: loob tabelid, laeb andmed, käivitab dbt mudelid ja testid
│
├── data/                          ← failipõhiste andmete kaust
│   ├── intermediate/              ← vaheandmed failidena, kui kasutatakse failipõhist töövoogu
│   ├── mart/                      ← dashboardi lõppandmed Parquet-failidena fallbacki jaoks
│   ├── raw/                       ← algsed toorandmed failidena
│   └── staging/                   ← staging-kihi failid, kui andmeid hoitakse ajutiselt failidena
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
├── sql/                           ← andmebaasi skeemide ja tabelite loomise SQL-failid
│   └── create_tables.sql          ← staging, intermediate ja marts skeemide ning toortabelite loomine
│
├── .env.example                   ← näidis keskkonnamuutujate fail; kopeeritakse lokaalselt .env failiks
├── .gitignore                     ← määrab, milliseid faile Git ei jälgi
├── compose.yml                    ← Docker Compose seadistus, mis käivitab andmebaasi, Airflow ja dashboardi
├── Dockerfile.airflow             ← Airflow konteineri ehitusfail koos vajalike Python/dbt sõltuvustega
├── Dockerfile.app                 ← Streamlit dashboardi konteineri ehitusfail
└── streamlit_app.py               ← Streamlit dashboardi põhifail
```

## Käivitamine

    # 1. Kopeeri keskkonnamuutujad
    cp .env.example .env
    
    # 2. Lae alla liiklusloenduste failid https://andmed.eesti.ee/ keskkonnast ja salvesta õige kausta alla
        * traffic_2025.csv ja traffic_2026.csv      -> data/raw/traffic/counts
        * LL_jaamad.csv                             -> data/raw/traffic/stations
      
    # 3. Käivita kõik teenused
    docker compose up -d --build

    # 4. Ava Airflow UI Airflow UI: http://localhost:8080
    Käivita DAG "airwolf_pipeline" koos backfillidega (andmed sisesta alates 2025 a. 1. jaanuar)

    # 5. Ava Streamlit http://localhost:8501 ja uudista


## Dokumentatsioon

Täpsem ülevaade arhitektuurist, andmevoogudest, mõõdikutest ja tööjaotusest: [docs/arhitektuur.md](docs/arhitektuur.md)

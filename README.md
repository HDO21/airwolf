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

| Kaust / fail | Kirjeldus |
|---|---|
| `archive_old_pipeline/` | Vana töövoog, mis töötab lokaalselt Parquet-failide põhjal. |
| `dags/` | Airflow DAG-ide kaust. |
| `dags/airwolf_pipeline.py` | Airflow töövoog, mis loob tabelid, laeb andmed, käivitab dbt mudelid ja testid. |
| `data/` | Andmefailide kaust. |
| `data/raw/` | Toorandmete failide kaust. |
| `data/raw/counts/` | Liiklusloenduste andmed CSV-failidena. |
| `data/raw/stations/` | Liiklusloenduste jaamad CSV-failina. |
| `dbt_project/` | dbt projekti kaust, kus asuvad transformatsioonid, testid ja dbt seadistusfailid. |
| `dbt_project/logs/` | dbt logifailid. |
| `dbt_project/macros/` | dbt makrode kaust. |
| `dbt_project/models/` | dbt transformatsioonimudelid. |
| `dbt_project/seeds/` | Õhukvaliteedi ja ilmavaatlusjaamade CSV-põhised referentstabelid. |
| `dbt_project/target/` | dbt automaatselt loodud väljundkaust, kus asuvad kompileeritud SQL ja jooksutamise tulemused. |
| `dbt_project/tests/` | Aktiivsed dbt andmekvaliteedi testid. |
| `dbt_project/tests_disabled/` | Testid, mis on olemas, aga mida hetkel ei käivitata. |
| `dbt_project/dbt_project.yml` | dbt projekti põhiseadistus. |
| `dbt_project/profiles.yml` | dbt andmebaasiühenduse seadistus. |
| `docs/` | Projekti arhitektuuri ja dokumentatsiooni kaust. |
| `docs/arhitektuur.md` | Projekti arhitektuuri kirjeldus. |
| `docs/progress.md` | Projekti edenemise kirjeldus. |
| `ingestion/` | Andmete laadimise skriptide kaust. |
| `ingestion/ingest_air_quality.py` | Õhukvaliteedi andmete laadimise skript. |
| `ingestion/ingest_traffic.py` | Liiklusandmete laadimise skript. |
| `ingestion/ingest_weather.py` | Ilmaandmete laadimise skript. |
| `sql/` | SQL-failide kaust andmebaasi skeemide ja staging-tabelite loomiseks. |
| `.env.example` | Näidisfail keskkonnamuutujate jaoks; kopeeritakse `.env` failiks. |
| `compose.yml` | Docker Compose seadistus, mis käivitab kogu projekti teenused. |
| `Dockerfile.airflow` | Airflow konteineri ehitusfail. |
| `Dockerfile.app` | Streamlit dashboardi konteineri ehitusfail. |
| `streamlit_app.py` | Streamlit dashboardi rakendusfail. |

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

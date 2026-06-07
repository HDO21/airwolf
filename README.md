# Õhuhunt — Eesti õhukvaliteedi analüütika

*Andmetoru, mis kõnetab su hingetoru*

## Mis see on?

Projekt uurib statistilisi seoseid Eesti linnade õhukvaliteedi ning ilmastiku (temperatuur, sademed, tuulekiirus) ja liiklussageduse vahel. Õhukvaliteeti hinnatakse saasteainete (SO2, NO2, O3, PM10, PM2.5) kontsentratsiooni alusel kolmes linnas — Tallinnas, Tartus ja Narvas — alates jaanuarist 2024.

Tulemused on nähtavad dashboardil: [est-air-quality-monitor.streamlit.app](https://est-air-quality-monitor.streamlit.app)

## Andmeallikad

| Allikas | Kirjeldus |
| --- | --- |
| [Keskkonnaandmed](https://keskkonnaandmed.envir.ee/f_kliima_tund) | Tunnipõhised ilmavaatlused (temperatuur, sademed, tuulekiirus) |
| [Ohuseire](https://ohuseire.ee/api/monitoring/et) | Õhukvaliteedi seireandmed (SO2, NO2, O3, PM10, PM2.5) |
| [Tark Tee](https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer) | Liiklusdetektorite tunnipõhised mõõtmised |

## Tehnoloogiad

- **Python** — andmete laadimine ja töötlus
- **Apache Airflow** — igapäevane automatiseerimine
- **PostgreSQL + dbt** — andmebaas ja transformatsioonid
- **Streamlit + Altair + Folium** — dashboard
- **Docker Compose** — kogu keskkond konteinerites

## Projekti struktuur

.
├── archive_old_pipeline/
│
├── dags/
│   └── airwolf_pipeline.py		-Airflow töövoog: loob tabelid, laeb andmed, käivitab dbt mudelid ja testid
├── data/
│    └── raw
│  		  ├── counts    		-liiklusloenduste andmed csv failidena
│   	  └── stations 			-liiklusloenduste jaamad csv failina 
		 
├── dbt_project/				
│   ├── logs/
│   ├── macros/
│   ├── models/					-transformatsioonid
│   ├── seeds/					-õhukvaliteedi ja ilmavaatluste jaamad (csv)
│   ├── target/
│   ├── tests/					-testid
│   ├── tests_disabled/			-testid, mis pole hetkel kasutusel
│   ├── dbt_project.yml
│   └── profiles.yml
│
├── docs/                       -arhitektuur ja dokumentatsioon
│   ├── arhitektuur.md
│   └── progress.md
│
├── ingestion/					-andmete laadimine (ilm, õhukvaliteet, liiklus)
│   ├── ingest_air_quality.py
│   ├── ingest_traffic.py
│   └── ingest_weather.py
│
├── sql/						-andmebaasi stating tabelite loomine (SQL)
│
├──.env.example					-kopeeri .env failiks
├──compose.yml					-Docker Compose seadistus, mis käivitab kogu projekti teenused
├──Dockerfile.airflow           -Airflow konteineri ehitusfail
├──Dockerfile.app               -Streamlit dashboardi konteineri ehitusfail
└──streamlit_app.py             -dashboard


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

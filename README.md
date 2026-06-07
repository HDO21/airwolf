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

    ingestion/             — andmete laadimine (ilm, õhukvaliteet, liiklus)
    dbt_project/           — transformatsioonid ja mart-kihi mudelid
    dags/                  — Airflow DAG igapäevaseks käivituseks
    sql/                   — andmebaasi skeemid ja tabelite loomine
    data/mart/             — mart-kihi andmefailid (dashboardi sisend)
    docs/                  — arhitektuur ja dokumentatsioon
    streamlit_app.py       — dashboard
    compose.yml            — Docker Compose seadistus
    .env.example           — keskkonnamuutujate näidis

## Käivitamine

    cp .env.example .env
    # Täida .env-is liikluse sisendfailide teed
    docker compose up -d --build

Dashboard: http://localhost:8501  
Airflow UI: http://localhost:8080

## Dokumentatsioon

Täpsem ülevaade arhitektuurist, andmevoogudest, mõõdikutest ja tööjaotusest: [docs/arhitektuur.md](docs/arhitektuur.md)

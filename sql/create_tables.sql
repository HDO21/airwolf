-- Loob skeemid ja Airflow sissevõtu toorandmete tabelid.
-- Selle loogika järgi:
--   staging = skeem, kuhu Airflow kirjutab esmaselt sisse võetud andmed
--   *_raw   = tabelinime lõpp, mis näitab, et tegemist on toorandmetega
--
-- dbt saab hiljem nende staging.*_raw tabelite pealt luua oma staging,
-- intermediate ja marts mudelid.

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS marts;


-- Töövoo käivituste jälgimine.
-- Üks rida = üks Airflow pipeline'i käivitus ühe andmeallika kohta.
CREATE TABLE IF NOT EXISTS staging.pipeline_runs (
    run_id        uuid        PRIMARY KEY,
    fetched_at    timestamptz NOT NULL DEFAULT now(),
    source_name   text        NOT NULL,
    period_start  timestamptz,
    period_end    timestamptz,
    status        text        NOT NULL, -- 'running' | 'success' | 'failed'
    message       text,

    CONSTRAINT chk_pipeline_runs_status
        CHECK (status IN ('running', 'success', 'failed'))
);


-- Toorandmed ilmaandmete API-st.
-- Üks rida = üks ilmajaam × üks vaatlustund × üks pipeline'i käivitus.
CREATE TABLE IF NOT EXISTS staging.weather_raw (
    run_id              uuid             NOT NULL REFERENCES staging.pipeline_runs(run_id),
    jaam_kood           text             NOT NULL,
    obs_time            timestamp        NOT NULL,
    lat                 double precision,
    lon                 double precision,
    temperature_c       double precision,
    wind_speed_ms       double precision,
    wind_direction_deg  double precision,
    precip_mm           double precision,
    loaded_at           timestamptz      NOT NULL DEFAULT now(),

    CONSTRAINT pk_weather_raw
        PRIMARY KEY (run_id, jaam_kood, obs_time)
);


-- Toorandmed õhukvaliteedi API-st.
-- Üks rida = üks seirekoht × üks vaatlustund × üks pipeline'i käivitus.
CREATE TABLE IF NOT EXISTS staging.air_quality_raw (
    run_id          uuid             NOT NULL REFERENCES staging.pipeline_runs(run_id),
    seirekoha_kood  text             NOT NULL,
    obs_time        timestamptz      NOT NULL,
    area            text,
    lat             double precision,
    lon             double precision,
    o3              double precision,
    no2             double precision,
    pm10            double precision,
    pm25            double precision,
    loaded_at       timestamptz      NOT NULL DEFAULT now(),

    CONSTRAINT pk_air_quality_raw
        PRIMARY KEY (run_id, seirekoha_kood, obs_time)
);


-- Toorandmed liiklusdetektorite live API-st.
-- Üks rida = üks liiklusdetektor × üks mõõtmishetk × üks pipeline'i käivitus.
CREATE TABLE IF NOT EXISTS staging.traffic_live_raw (
    run_id                    uuid             NOT NULL REFERENCES staging.pipeline_runs(run_id),
    traffic_detector_id        text             NOT NULL,
    site_name                  text,
    road_name                  text,
    measurement_time           timestamp        NOT NULL,
    total_flow_forwards        double precision,
    total_flow_backwards       double precision,
    heavy_traffic_forwards     double precision,
    heavy_traffic_backwards    double precision,
    average_speed_forwards     double precision,
    average_speed_backwards    double precision,
    relative_speed_forwards    double precision,
    relative_speed_backwards   double precision,
    x_3301                     double precision,
    y_3301                     double precision,
    area                       text,
    loaded_at                  timestamptz      NOT NULL DEFAULT now(),

    CONSTRAINT pk_traffic_live_raw
        PRIMARY KEY (run_id, traffic_detector_id, measurement_time)
);

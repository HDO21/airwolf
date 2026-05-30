CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS marts;

CREATE TABLE IF NOT EXISTS staging.pipeline_runs (
    run_id      uuid PRIMARY KEY,
    loaded_at  timestamptz NOT NULL DEFAULT now(),
    source_name text NOT NULL,
    status      text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    message     text,

    CONSTRAINT chk_pipeline_runs_status
        CHECK (status IN ('running', 'success', 'failed'))
);

-- Õhukvaliteet: ohuseire.ee /api/monitoring/et.
-- Algfail deduplikeeris võtmega station × indicator × measured.
CREATE TABLE IF NOT EXISTS staging.air_quality_raw (
    run_id      uuid REFERENCES staging.pipeline_runs(run_id),
    station     text NOT NULL,
    indicator   text NOT NULL,
    measured    timestamptz NOT NULL,
    value       numeric,
    loaded_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pk_air_quality_raw 
        PRIMARY KEY (station, indicator, measured)
);

-- Ilm: keskkonnaandmed.envir.ee / f_kliima_tund.
-- Algfail deduplikeeris võtmega jaam_kood × aasta × kuu × paev × tund × element_kood.
-- Toorandmed Keskkonnaandmed f_kliima_tund API-st.
-- Üks rida = üks ilmajaam × üks vaatlustund × üks pipeline'i käivitus.
--
-- API element_kood teisendus:
--   TA     -> temperature_c
--   WS10M  -> wind_speed_ms
--   WD10M  -> wind_direction_deg
--   PR1H   -> precip_mm
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
        PRIMARY KEY (jaam_kood, obs_time)
);


-- Liiklus live: Tark Tee ArcGIS snapshot.
CREATE TABLE IF NOT EXISTS staging.traffic_live_raw (
    traffic_detector_id text NOT NULL,
    measurement_time    bigint NOT NULL,
    area                text NOT NULL,
    site_name           text,
    road_name           text,
    x_3301              double precision,
    y_3301              double precision,
    payload             jsonb NOT NULL,
    run_id              uuid REFERENCES staging.pipeline_runs(run_id),
    _loaded_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_traffic_live_raw PRIMARY KEY (traffic_detector_id, measurement_time, area)
);

-- Liiklus backfill CSV: algfail deduplikeeris võtmega id × kanal × aeg.
CREATE TABLE IF NOT EXISTS staging.traffic_backfill_raw (
    id         text NOT NULL,
    kanal      text NOT NULL,
    aeg        timestamptz NOT NULL,
    payload    jsonb NOT NULL,
    run_id     uuid REFERENCES staging.pipeline_runs(run_id),
    _loaded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_traffic_backfill_raw PRIMARY KEY (id, kanal, aeg)
);

-- Liiklusandurite register, mida live/backfill laadimine uuendab.
CREATE TABLE IF NOT EXISTS staging.traffic_detector_registry_raw (
    traffic_detector_id text PRIMARY KEY,
    site_name           text,
    road_name           text,
    area                text,
    lat                 double precision,
    lon                 double precision,
    x_3301              double precision,
    y_3301              double precision,
    payload             jsonb NOT NULL,
    run_id              uuid,
    _loaded_at          timestamptz NOT NULL DEFAULT now()
);



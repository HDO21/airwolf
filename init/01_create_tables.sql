-- Airwolf analytics-db bootstrap script.
-- Executed automatically by pgDuckDB on the very first container start
-- (via docker-entrypoint-initdb.d). Subsequent starts skip this file.
-- Content is kept in sync with sql/create_tables.sql.

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS marts;

CREATE TABLE IF NOT EXISTS staging.pipeline_runs (
    run_id      uuid        PRIMARY KEY,
    source_name text        NOT NULL,
    status      text        NOT NULL,
    message     text,
    loaded_at   timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,

    CONSTRAINT chk_pipeline_runs_status
        CHECK (status IN ('running', 'success', 'failed'))
);

CREATE TABLE IF NOT EXISTS staging.air_quality_raw (
    run_id    uuid REFERENCES staging.pipeline_runs(run_id),
    station   text        NOT NULL,
    indicator text        NOT NULL,
    measured  timestamptz NOT NULL,
    value     numeric,
    loaded_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pk_air_quality_raw
        PRIMARY KEY (station, indicator, measured)
);

CREATE TABLE IF NOT EXISTS staging.weather_raw (
    run_id             uuid             NOT NULL REFERENCES staging.pipeline_runs(run_id),
    jaam_kood          text             NOT NULL,
    obs_time           timestamptz      NOT NULL,
    lat                double precision,
    lon                double precision,
    temperature_c      double precision,
    wind_speed_ms      double precision,
    wind_direction_deg double precision,
    precip_mm          double precision,
    loaded_at          timestamptz      NOT NULL DEFAULT now(),

    CONSTRAINT pk_weather_raw
        PRIMARY KEY (jaam_kood, obs_time)
);

CREATE TABLE IF NOT EXISTS staging.traffic_counts_raw (
    run_id                      uuid REFERENCES staging.pipeline_runs(run_id),
    id                          text        NOT NULL,
    kanal                       integer     NOT NULL,
    aeg                         timestamptz NOT NULL,
    site_name                   text,
    road_name                   text,
    area                        text,
    lat                         double precision,
    lon                         double precision,
    x_3301                      double precision,
    y_3301                      double precision,
    motorcycle_count            integer,
    car_light_van_count         integer,
    car_light_van_trailer_count integer,
    heavy_van_count             integer,
    light_goods_count           integer,
    rigid_count                 integer,
    rigid_trailer_count         integer,
    articulated_hgv_count       integer,
    minibus_count               integer,
    bus_coach_count             integer,
    speed_lt_40_count           integer,
    speed_40_50_count           integer,
    speed_50_60_count           integer,
    speed_60_70_count           integer,
    speed_70_80_count           integer,
    speed_80_90_count           integer,
    speed_90_100_count          integer,
    speed_100_110_count         integer,
    speed_110_120_count         integer,
    speed_120_130_count         integer,
    speed_gte_130_count         integer,
    source_file                 text,
    loaded_at                   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pk_traffic_counts_raw
        PRIMARY KEY (id, kanal, aeg)
);

CREATE TABLE IF NOT EXISTS staging.traffic_live_raw (
    run_id               uuid REFERENCES staging.pipeline_runs(run_id),
    traffic_detector_id  text        NOT NULL,
    measurement_time     timestamptz NOT NULL,
    site_name            text,
    road_name            text,
    area                 text,
    lat                  double precision,
    lon                  double precision,
    x_3301               double precision,
    y_3301               double precision,
    total_flow_forwards  integer,
    total_flow_backwards integer,
    heavy_traffic_forwards  integer,
    heavy_traffic_backwards integer,
    average_speed_forwards  double precision,
    average_speed_backwards double precision,
    relative_speed_forwards  double precision,
    relative_speed_backwards double precision,
    loaded_at            timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pk_traffic_live_raw
        PRIMARY KEY (traffic_detector_id, measurement_time)
);

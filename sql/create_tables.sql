-- Staging skeema ja tabelid
-- Airflow DAG laeb API-dest andmeid siia. dbt loeb siit edasi.
-- Andmed võetakse py failide abil: ingest_weather.py, ingest_air_quality.py, ja ingest_traffic.py

CREATE SCHEMA IF NOT EXISTS staging;

-- -----------------------------------------------------------------------------
-- Weather observations 
-- Source script: ingest_weather.py
-- Output grain: one row per weather station x observation hour
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS staging.weather_observations (
    jaam_kood TEXT NOT NULL,
    obs_time TIMESTAMP NOT NULL,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    temperature_c DOUBLE PRECISION,
    wind_speed_ms DOUBLE PRECISION,
    wind_direction_deg DOUBLE PRECISION,
    precip_mm DOUBLE PRECISION,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_weather_observations
        PRIMARY KEY (jaam_kood, obs_time)
);

CREATE INDEX IF NOT EXISTS idx_weather_observations_obs_time
    ON staging.weather_observations (obs_time);

CREATE INDEX IF NOT EXISTS idx_weather_observations_station
    ON staging.weather_observations (jaam_kood);


-- -----------------------------------------------------------------------------
-- Air quality observations 
-- Source script: ingest_air_quality.py
-- Output grain: one row per monitoring station x observation hour
-- Notes: obs_time is parsed as UTC in the Python script, so TIMESTAMPTZ is used.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS staging.air_quality_observations (
    seirekoha_kood TEXT NOT NULL,
    obs_time TIMESTAMPTZ NOT NULL,
    area TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    o3 DOUBLE PRECISION,
    no2 DOUBLE PRECISION,
    pm10 DOUBLE PRECISION,
    pm25 DOUBLE PRECISION,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_air_quality_observations
        PRIMARY KEY (seirekoha_kood, obs_time)
);

CREATE INDEX IF NOT EXISTS idx_air_quality_observations_obs_time
    ON staging.air_quality_observations (obs_time);

CREATE INDEX IF NOT EXISTS idx_air_quality_observations_station
    ON staging.air_quality_observations (seirekoha_kood);

CREATE INDEX IF NOT EXISTS idx_air_quality_observations_area
    ON staging.air_quality_observations (area);


-- -----------------------------------------------------------------------------
-- Traffic live detector snapshot
-- Source script: ingest_traffic.py --mode live
-- Output grain: one row per traffic detector in the live API response
-- Note: measurement_time may be null in some API responses; therefore the table
-- uses a surrogate identity key and a non-unique helper index instead of a strict
-- primary key on (traffic_detector_id, measurement_time).
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS staging.traffic_live (
    traffic_live_id BIGSERIAL PRIMARY KEY,
    traffic_detector_id TEXT,
    site_name TEXT,
    road_name TEXT,
    measurement_time TIMESTAMP,
    total_flow_forwards DOUBLE PRECISION,
    total_flow_backwards DOUBLE PRECISION,
    heavy_traffic_forwards DOUBLE PRECISION,
    heavy_traffic_backwards DOUBLE PRECISION,
    average_speed_forwards DOUBLE PRECISION,
    average_speed_backwards DOUBLE PRECISION,
    relative_speed_forwards DOUBLE PRECISION,
    relative_speed_backwards DOUBLE PRECISION,
    x_3301 DOUBLE PRECISION,
    y_3301 DOUBLE PRECISION,
    area TEXT,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_traffic_live_detector_time
    ON staging.traffic_live (traffic_detector_id, measurement_time);

CREATE INDEX IF NOT EXISTS idx_traffic_live_measurement_time
    ON staging.traffic_live (measurement_time);

CREATE INDEX IF NOT EXISTS idx_traffic_live_area
    ON staging.traffic_live (area);


-- -----------------------------------------------------------------------------
-- Traffic detector registry
-- Source script: ingest_traffic.py --mode live
-- The script maintains a detector registry file from live detector metadata.
-- This table mirrors that registry if you decide to load it into PostgreSQL.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS staging.traffic_detector_registry (
    traffic_detector_id TEXT PRIMARY KEY,
    site_name TEXT,
    road_name TEXT,
    x_3301 DOUBLE PRECISION,
    y_3301 DOUBLE PRECISION,
    area TEXT,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_traffic_detector_registry_area
    ON staging.traffic_detector_registry (area);


-- -----------------------------------------------------------------------------
-- Traffic historical backfill
-- Source script: ingest_traffic.py --mode backfill
-- The CSV contains detector id and timestamp column aeg. The script derives
-- total_flow, heavy_vehicle_count, and heavy_vehicle_share. Vehicle class columns
-- 1-10 are awkward SQL identifiers, so they are renamed here to vehicle_class_1...
-- vehicle_class_10 for database use.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS staging.traffic_backfill (
    detector_id TEXT NOT NULL,
    aeg TIMESTAMP NOT NULL,
    vehicle_class_1 DOUBLE PRECISION,
    vehicle_class_2 DOUBLE PRECISION,
    vehicle_class_3 DOUBLE PRECISION,
    vehicle_class_4 DOUBLE PRECISION,
    vehicle_class_5 DOUBLE PRECISION,
    vehicle_class_6 DOUBLE PRECISION,
    vehicle_class_7 DOUBLE PRECISION,
    vehicle_class_8 DOUBLE PRECISION,
    vehicle_class_9 DOUBLE PRECISION,
    vehicle_class_10 DOUBLE PRECISION,
    total_flow DOUBLE PRECISION,
    heavy_vehicle_count DOUBLE PRECISION,
    heavy_vehicle_share DOUBLE PRECISION,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_traffic_backfill
        PRIMARY KEY (detector_id, aeg)
);

CREATE INDEX IF NOT EXISTS idx_traffic_backfill_aeg
    ON staging.traffic_backfill (aeg);

CREATE INDEX IF NOT EXISTS idx_traffic_backfill_detector
    ON staging.traffic_backfill (detector_id);

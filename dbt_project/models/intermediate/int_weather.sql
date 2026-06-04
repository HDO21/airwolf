{{ config(materialized='table', schema='intermediate') }}

-- Jaamade nimed ja piirkondade vastavused tulevad weather_stations andmestikust
-- (dbt_project/seeds/weather_stations.csv), et need oleksid defineeritud vaid ühes kohas.

with raw as (
    select
        jaam_kood,
        obs_time::timestamptz as obs_time,
        lat::double precision as lat,
        lon::double precision as lon,
        temperature_c::double precision as temperature_c,
        wind_speed_ms::double precision as wind_speed_ms,
        wind_direction_deg::double precision as wind_direction_deg,
        precip_mm::double precision as precip_mm,
        loaded_at
    from {{ source('staging', 'weather_raw') }}
),

latest_per_hour as (
    select *
    from (
        select
            raw.*,
            row_number() over (
                partition by jaam_kood, obs_time
                order by loaded_at desc
            ) as rn
        from raw
    ) x
    where rn = 1
),

stations as (
    select jaam_kood, station_name, area
    from {{ ref('weather_stations') }}
)

select
    r.jaam_kood as station_id,
    s.station_name,
    s.area,
    r.obs_time,
    r.lat,
    r.lon,
    r.temperature_c,
    r.wind_speed_ms,
    r.wind_direction_deg,
    greatest(r.precip_mm, 0) as precip_mm
from latest_per_hour r
inner join stations s on r.jaam_kood = s.jaam_kood

{{ config(materialized='table', schema='intermediate') }}

with raw as (
    select
        station::integer as station_id,
        indicator::integer as indicator_id,
        measured::timestamptz as obs_time,
        value::numeric as value,
        loaded_at
    from {{ source('staging', 'air_quality_raw') }}
),

mapped as (
    select
        station_id,
        case station_id
            when 4 then 'Narva'
            when 5 then 'Liivalaia'
            when 7 then 'Õismäe'
            when 8 then 'Tartu'
            else station_id::text
        end as station_name,
        case station_id
            when 4 then 'narva'
            when 5 then 'tallinn'
            when 7 then 'tallinn'
            when 8 then 'tartu'
        end as area,
        case station_id
            when 4 then 59.3722
            when 5 then 59.4310
            when 7 then 59.4140
            when 8 then 58.3706
        end::double precision as lat,
        case station_id
            when 4 then 28.2007
            when 5 then 24.7605
            when 7 then 24.6497
            when 8 then 26.7348
        end::double precision as lon,
        obs_time,
        case indicator_id
            when 1 then 'SO2'
            when 3 then 'NO2'
            when 6 then 'O3'
            when 21 then 'PM10'
            when 23 then 'PM25'
        end as pollutant,
        value,
        loaded_at
    from raw
    where station_id in (4, 5, 7, 8)
      and indicator_id in (1, 3, 6, 21, 23)
),

latest_values as (
    select *
    from (
        select
            mapped.*,
            row_number() over (
                partition by station_id, pollutant, obs_time
                order by loaded_at desc
            ) as rn
        from mapped
    ) x
    where rn = 1
)

select
    station_id,
    station_name,
    area,
    obs_time,
    lat,
    lon,
    avg(value) filter (where pollutant = 'SO2')  as "SO2",
    avg(value) filter (where pollutant = 'O3')   as "O3",
    avg(value) filter (where pollutant = 'NO2')  as "NO2",
    avg(value) filter (where pollutant = 'PM10') as "PM10",
    avg(value) filter (where pollutant = 'PM25') as "PM25"
from latest_values
group by station_id, station_name, area, obs_time, lat, lon

{{ config(materialized='table', schema='marts') }}

with weather as (
    select distinct
        station_id::text as station_id,
        station_name,
        area,
        lat,
        lon,
        'weather' as source
    from {{ ref('mart_weather') }}
),

aq as (
    select distinct
        station_id::text as station_id,
        station_name,
        area,
        lat,
        lon,
        'air_quality' as source
    from {{ ref('mart_aq') }}
),

traffic as (
    select distinct
        detector_id::text as station_id,
        site_name as station_name,
        area,
        lat,
        lon,
        'traffic' as source
    from {{ ref('mart_traffic') }}
)

select * from weather
union all
select * from aq
union all
select * from traffic

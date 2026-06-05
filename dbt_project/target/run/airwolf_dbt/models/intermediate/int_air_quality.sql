
  
    

  create  table "airwolf"."intermediate"."int_air_quality__dbt_tmp"
  
  
    as
  
  (
    

-- Jaama metaandmed (nimed, piirkonnad, koordinaadid) ning indikaatori koodide teisendus nimedeks.

with indicator_map (indicator_id, pollutant) as (
    values
        (1,  'SO2'),
        (3,  'NO2'),
        (6,  'O3'),
        (21, 'PM10'),
        (23, 'PM25')
),

raw as (
    select
        station::integer  as station_id,
        indicator::integer as indicator_id,
        measured::timestamptz as obs_time,
        value::numeric as value,
        loaded_at
    from "airwolf"."staging"."air_quality_raw"
),

mapped as (
    select
        r.station_id,
        r.obs_time,
        i.pollutant,
        r.value,
        r.loaded_at
    from raw r
    inner join indicator_map i on r.indicator_id = i.indicator_id
    inner join "airwolf"."reference"."aq_stations" s on r.station_id = s.station_id
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
    lv.station_id,
    s.station_name,
    s.area,
    lv.obs_time,
    s.lat,
    s.lon,
    avg(lv.value) filter (where lv.pollutant = 'SO2')  as "SO2",
    avg(lv.value) filter (where lv.pollutant = 'O3')   as "O3",
    avg(lv.value) filter (where lv.pollutant = 'NO2')  as "NO2",
    avg(lv.value) filter (where lv.pollutant = 'PM10') as "PM10",
    avg(lv.value) filter (where lv.pollutant = 'PM25') as "PM25"
from latest_values lv
inner join "airwolf"."reference"."aq_stations" s on lv.station_id = s.station_id
group by lv.station_id, s.station_name, s.area, lv.obs_time, s.lat, s.lon
  );
  
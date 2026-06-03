
  
    

  create  table "airwolf"."intermediate"."int_weather__dbt_tmp"
  
  
    as
  
  (
    

with raw as (
    select
        jaam_kood,
        obs_time::timestamp as obs_time,
        lat::double precision as lat,
        lon::double precision as lon,
        temperature_c::double precision as temperature_c,
        wind_speed_ms::double precision as wind_speed_ms,
        wind_direction_deg::double precision as wind_direction_deg,
        precip_mm::double precision as precip_mm,
        loaded_at
    from "airwolf"."staging"."weather_raw"
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
)

select
    jaam_kood as station_id,
    case jaam_kood
        when 'AJHARK01' then 'Tallinn-Harku'
        when 'AJTART01' then 'Tartu-Tõravere'
        when 'AJNARV01' then 'Narva'
        else jaam_kood
    end as station_name,
    case jaam_kood
        when 'AJHARK01' then 'tallinn'
        when 'AJTART01' then 'tartu'
        when 'AJNARV01' then 'narva'
    end as area,
    obs_time,
    lat,
    lon,
    temperature_c,
    wind_speed_ms,
    wind_direction_deg,
    greatest(precip_mm, 0) as precip_mm
from latest_per_hour
where jaam_kood in ('AJHARK01', 'AJTART01', 'AJNARV01')
  );
  

  
    

  create  table "airwolf"."intermediate"."int_traffic__dbt_tmp"
  
  
    as
  
  (
    

with backfill_raw as (

    select
        id::text as detector_id,
        aeg::timestamptz as obs_time,
        site_name,
        area,
        lat::double precision as lat,
        lon::double precision as lon,

        coalesce(motorcycle_count, 0)
        + coalesce(car_light_van_count, 0)
        + coalesce(car_light_van_trailer_count, 0)
        + coalesce(heavy_van_count, 0)
        + coalesce(light_goods_count, 0)
        + coalesce(rigid_count, 0)
        + coalesce(rigid_trailer_count, 0)
        + coalesce(articulated_hgv_count, 0)
        + coalesce(minibus_count, 0)
        + coalesce(bus_coach_count, 0) as total_flow,

        loaded_at,
        'backfill' as source_type

    from "airwolf"."staging"."traffic_counts_raw"
    where id::text <> '944ab'

),

backfill_hourly as (

    select
        detector_id,
        obs_time,
        max(site_name) as site_name,
        max(area) as area,
        avg(lat) as lat,
        avg(lon) as lon,
        sum(total_flow) as total_flow,
        max(loaded_at) as loaded_at,
        'backfill' as source_type

    from backfill_raw
    group by detector_id, obs_time

),

live_raw as (

    select
        traffic_detector_id::text as detector_id,
        measurement_time::timestamptz as obs_time,
        site_name,
        area,
        lat::double precision as lat,
        lon::double precision as lon,

        coalesce(total_flow_forwards, 0)
        + coalesce(total_flow_backwards, 0) as total_flow,

        loaded_at,
        'live' as source_type

    from "airwolf"."staging"."traffic_live_raw"
    where traffic_detector_id::text <> '944ab'

),

unioned as (

    select * from backfill_hourly
    union all
    select * from live_raw

),

deduplicated as (

    select *
    from (
        select
            unioned.*,
            row_number() over (
                partition by detector_id, obs_time
                order by
                    case when source_type = 'live' then 2 else 1 end desc,
                    loaded_at desc
            ) as rn
        from unioned
    ) x
    where rn = 1

)

select
    detector_id,
    site_name,
    area,
    obs_time,
    lat,
    lon,
    total_flow,
    source_type,
    loaded_at

from deduplicated
where area is not null
  );
  
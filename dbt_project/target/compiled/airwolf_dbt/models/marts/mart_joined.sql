

with aq_area as (
    select
        area,
        obs_time,
        avg("SO2") as "SO2",
        avg("O3") as "O3",
        avg("NO2") as "NO2",
        avg("PM10") as "PM10",
        avg("PM25") as "PM25"
    from "airwolf"."marts"."mart_aq"
    group by area, obs_time
),

weather_area as (
    select
        area,
        obs_time,
        avg(temperature_c) as temperature_c,
        avg(wind_speed_ms) as wind_speed_ms,
        avg(precip_mm) as precip_mm
    from "airwolf"."marts"."mart_weather"
    group by area, obs_time
),

traffic_area as (
    select
        area,
        obs_time,
        avg(total_flow) as total_flow
    from "airwolf"."marts"."mart_traffic"
    group by area, obs_time
)

select
    aq_area.area,
    aq_area.obs_time,
    aq_area."SO2",
    aq_area."O3",
    aq_area."NO2",
    aq_area."PM10",
    aq_area."PM25",
    weather_area.temperature_c,
    weather_area.wind_speed_ms,
    weather_area.precip_mm,
    traffic_area.total_flow
from aq_area
left join weather_area
    on aq_area.area = weather_area.area
   and aq_area.obs_time = weather_area.obs_time
left join traffic_area
    on aq_area.area = traffic_area.area
   and aq_area.obs_time = traffic_area.obs_time
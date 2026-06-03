
  
    

  create  table "airwolf"."marts"."mart_traffic__dbt_tmp"
  
  
    as
  
  (
    

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
from "airwolf"."intermediate"."int_traffic"
  );
  
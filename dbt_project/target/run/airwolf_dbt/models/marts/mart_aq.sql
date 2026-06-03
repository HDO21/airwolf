
  
    

  create  table "airwolf"."marts"."mart_aq__dbt_tmp"
  
  
    as
  
  (
    

select *
from "airwolf"."intermediate"."int_air_quality"
where area is not null
  );
  
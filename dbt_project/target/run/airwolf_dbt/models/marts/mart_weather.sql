
  
    

  create  table "airwolf"."marts"."mart_weather__dbt_tmp"
  
  
    as
  
  (
    

select *
from "airwolf"."intermediate"."int_weather"
where area is not null
  );
  
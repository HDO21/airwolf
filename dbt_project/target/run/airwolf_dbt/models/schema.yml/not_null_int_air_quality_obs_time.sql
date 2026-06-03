
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select obs_time
from "airwolf"."intermediate"."int_air_quality"
where obs_time is null



  
  
      
    ) dbt_internal_test
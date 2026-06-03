
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select detector_id
from "airwolf"."intermediate"."int_traffic"
where detector_id is null



  
  
      
    ) dbt_internal_test

    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select area
from "airwolf"."marts"."mart_joined"
where area is null



  
  
      
    ) dbt_internal_test
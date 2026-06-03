
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        area as value_field,
        count(*) as n_records

    from "airwolf"."intermediate"."int_air_quality"
    group by area

)

select *
from all_values
where value_field not in (
    'tallinn','tartu','narva'
)



  
  
      
    ) dbt_internal_test
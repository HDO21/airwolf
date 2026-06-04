
    
    

with all_values as (

    select
        area as value_field,
        count(*) as n_records

    from "airwolf"."intermediate"."int_weather"
    group by area

)

select *
from all_values
where value_field not in (
    'tallinn','tartu','narva'
)



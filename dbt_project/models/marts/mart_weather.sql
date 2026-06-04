{{ config(materialized='table', schema='marts') }}

select *
from {{ ref('int_weather') }}
where area is not null

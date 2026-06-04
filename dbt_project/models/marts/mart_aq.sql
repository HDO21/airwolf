{{ config(materialized='table', schema='marts') }}

select *
from {{ ref('int_air_quality') }}
where area is not null

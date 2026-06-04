{{ config(materialized='table', schema='marts') }}

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
from {{ ref('int_traffic') }}
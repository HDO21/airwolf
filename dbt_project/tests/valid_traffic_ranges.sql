select *
from {{ ref('int_traffic') }}
where total_flow < 0
   or lat < 57
   or lat > 60.5
   or lon < 21
   or lon > 29
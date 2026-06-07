select *
from {{ ref('int_air_quality') }}
where SO2 < 0
   or O3 < 0
   or NO2 < 0
   or PM10 < 0
   or PM25 < 0
   or lat < 57
   or lat > 60.5
   or lon < 21
   or lon > 29
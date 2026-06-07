select *
from {{ ref('int_weather') }}
where temperature_c < -50
   or temperature_c > 50
   or wind_speed_ms < 0
   or precip_mm < 0
   or lat < 57
   or lat > 60.5
   or lon < 21
   or lon > 29
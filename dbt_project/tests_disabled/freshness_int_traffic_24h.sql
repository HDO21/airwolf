-- Kontrollib, kas int_traffic tabelis olevad andmed on vähem kui 24 tundi vana.
select
    max(obs_time) as latest_obs_time
from {{ ref('int_traffic') }}
having 
    max(obs_time) is null
    or max(obs_time) < now() - interval '24 hours'
--Tuvastab dublikaatide olemasolu int_weather tabelis, kus station_id ja obs_time kombinatsioon on sama. Kui row_count on suurem kui 1, siis tähendab see, et on leitud duplikaate.
select
    station_id,
    obs_time,
    count(*) as row_count
from {{ ref('int_weather') }}
group by station_id, obs_time
having count(*) > 1
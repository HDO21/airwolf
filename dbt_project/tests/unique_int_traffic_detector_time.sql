--Dublikaatide tuvastamine int_traffic tabelis, kus detector_id ja obs_time kombinatsioon on sama. Kui row_count on suurem kui 1, siis tähendab see, et on leitud duplikaate.
select
    detector_id,
    obs_time,
    count(*) as row_count
from {{ ref('int_traffic') }}
group by detector_id, obs_time
having count(*) > 1
# airwolf - Õhukvaliteedi analüütika

## Äriküsimus

Projekti eesmärk on uurida, kas, kuidas ja millisel määral sõltub Eesti asulates mõõdetud õhukvaliteet ilmastikunähtustest, nagu tuul, sademed ja temperatuur, ning liiklussagedusest. Millistes Eesti asulates ja mis aegadel tagab ilmastiku ning liiklussageduse koosmõju kõige puhtama/saastatuma õhukvaliteedi?

## Andmeallikad ja nende muutuvus ajas (sh lingid)

- **Ilmavaatluste andmed**  

Allikas: https://keskkonnaandmed.envir.ee/f_kliima_paev  

Tegemist on ajas muutuva andmeallikaga, mis sisaldab meteoroloogilisi vaatlusi erinevate ilmastikunäitajate kohta. Avaandmete päringuid uuendatakse reeglina üks kord ööpäevas, tavaliselt öisel ajal. Andmeid on enamasti iga tunni kohta.

- **Välisõhu seire andmed**

Allikas: https://keskkonnaandmed.envir.ee/f_keskkonnaseire  

Tegemist on ajas muutuva andmeallikaga, mis sisaldab õhukvaliteedi seireandmeid erinevate saasteainete ja mõõtepunktide lõikes. Ka selle andmeallika avaandmete päringuid uuendatakse reeglina üks kord ööpäevas. Andmeid salvestatakse iga 10 minuti järel.
Hetkel eksisteeriv kaardirakendus: https://ohuseire.ee/ 

- **Liiklussageduse andmed**  

Allikas: https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer  

Tegemist on ajas muutuva andmeallikaga, mis sisaldab liiklusdetektorite mõõtmisi, sealhulgas liiklusvoogude, raskeveokite osakaalu ja kiiruste infot. Ajalugu ei salvestata ja nähtav on korraga ühe päeva andmed.

Allikas: https://andmed.eesti.ee/datasets/liiklusloenduse-andmed

Tegemist on liiklusloenduse ajalooandmetega, mis on sobilikud "backfilliks". Eraldi saab lehelt alla laadida aastate kaupa liiklusloenduse andmeid. Liiklusandmete ajaloo andmete salvestamiseks antud projektis on vajalik alla laadida 2025, 2026 aasta liiklusloenduse andmed ja salvestada need järgnevalt:

data\raw\stations\counts\traffic_2025.csv
data\raw\stations\counts\traffic_2026.csv

Allikas: https://andmed.eesti.ee/datasets/liiklusloendusseadmed

Tegemist on liiklusloendusjaamade nimekirjaga. See fail on vaja alla laadida ja salvestada data\raw\stations kausta nimega LL_jaamad.xlsx



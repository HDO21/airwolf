# Edenemisraport

## Mis on valmis

- Toimib täielik andmevoog (ingest -> transform -> mart), aga andmed salvestatakse parguet failidesse
- Andmed saadakse allikatest kätte ja salvestatakse hetkel parguet failidesse (staging kausta) ja mart kihid ehitatakse nende baasilt
- Vähemalt üks transformatsioon toimib ja on tehtud ka esimesed analüüsid õhukvaliteedi kohta Tartus
- Näidikulaual on nähtavad erinevad andmed
- Kontrollitakse andmekvaliteeti

Töövoog Airflow ja dbt-ga on pooleli, valmis on järgmised osad:
- Docker Compose käivitab kõik teenused: analytics-db, Airflow, Streamlit
- Ilmavaatluse- ja õhukvaliteedi andmed saadakse allikatest kätte ja salvestatakse 'staging' kihti andmebaasi tabelitesse

## Järgmised sammud

- Transpordiandmed vaja allikatest kätte saada ja salvestada andmebaasi 
- Transformatsioonid ja valmis ehitada mart kihid
- Seoste/korrelatsiooni leidmine õhukvaliteedi, ilma ja tranpordiandmete vahel
- Näidikulaua täiendused

## Mis takistab

- Ajanappus
- Sõltuvus üksteise tööst, kuna tööülesanded tulevad järjestikku, ei saa enne tegelema hakata näiteks transformatsioonidega kui andmete sissevõtmine on tehtud
- Töövahendite valiku puhul erinev tase (algajate vs edasijõudnute grupp)

## Kontrollpunkt

Käsk, millega saab hetkel kontrollida, et töövoog töötab:

```bash
# python run_pipeline.py
```


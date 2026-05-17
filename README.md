# Django Weather Forecast App

A Django weather forecast project styled to match the reference UI: dark page, warm current-weather panel, storm-photo forecast panel, city search, live forecast details, and hourly weather cards.

## Run

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Then visit:

```text
http://127.0.0.1:8000
```

## Weather API

The Django view in `forecast/views.py` uses Open-Meteo, so no API key is required.

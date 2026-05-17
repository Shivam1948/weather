from datetime import datetime
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from django.shortcuts import render


DEFAULT_CITY = {
    "name": "Byculla West",
    "region": "Maharashtra",
    "country": "India",
    "latitude": 18.9766,
    "longitude": 72.8338,
}

KNOWN_CITIES = {
    "byculla west": DEFAULT_CITY,
    "gorakhpur": {
        "name": "Gorakhpur",
        "region": "Uttar Pradesh",
        "country": "India",
        "latitude": 26.7606,
        "longitude": 83.3732,
    },
    "gorakhpur uttar pradesh": {
        "name": "Gorakhpur",
        "region": "Uttar Pradesh",
        "country": "India",
        "latitude": 26.7606,
        "longitude": 83.3732,
    },
    "phagwara": {
        "name": "Phagwara",
        "region": "Punjab",
        "country": "India",
        "latitude": 31.224,
        "longitude": 75.771,
    },
    "ranchi": {
        "name": "Ranchi",
        "region": "Jharkhand",
        "country": "India",
        "latitude": 23.3441,
        "longitude": 85.3096,
    },
}

SEARCH_REPLACEMENTS = {
    "uttarpardesh": "uttar pradesh",
    "uttarpradesh": "uttar pradesh",
    "uttar pardesh": "uttar pradesh",
    "up": "uttar pradesh",
}

WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast clouds",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "heavy thunderstorm with hail",
}


def fetch_json(url, params, headers=None):
    query = urlencode(params)
    request = Request(f"{url}?{query}", headers=headers or {})
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_search_query(query):
    normalized = re.sub(r"[,]+", " ", query.strip().lower())
    normalized = re.sub(r"\s+", " ", normalized)
    for wrong, right in SEARCH_REPLACEMENTS.items():
        normalized = re.sub(rf"\b{re.escape(wrong)}\b", right, normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def open_meteo_location(query):
    data = fetch_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {
            "name": query,
            "count": 1,
            "language": "en",
            "format": "json",
        },
    )
    result = (data.get("results") or [None])[0]
    if not result:
        return None

    return {
        "name": result["name"],
        "region": result.get("admin1", ""),
        "country": result.get("country", ""),
        "latitude": result["latitude"],
        "longitude": result["longitude"],
    }


def nominatim_location(query):
    data = fetch_json(
        "https://nominatim.openstreetmap.org/search",
        {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
            "countrycodes": "in",
        },
        headers={"User-Agent": "WeatherCast Django app"},
    )
    result = (data or [None])[0]
    if not result:
        return None

    address = result.get("address", {})
    name = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("suburb")
        or result.get("name")
        or query
    )
    return {
        "name": name,
        "region": address.get("state", ""),
        "country": address.get("country", "India"),
        "latitude": float(result["lat"]),
        "longitude": float(result["lon"]),
    }


def pincode_location(query):
    if not re.fullmatch(r"\d{6}", query.strip()):
        return None

    data = fetch_json(
        f"https://api.postalpincode.in/pincode/{query.strip()}",
        {},
    )
    result = (data or [None])[0]
    post_offices = result.get("PostOffice") if result else None
    post_office = (post_offices or [None])[0]
    if not post_office:
        return None

    district = post_office.get("District")
    state = post_office.get("State")
    place_query = " ".join(
        bit for bit in [district, state, "India"] if bit
    )
    location = open_meteo_location(place_query) or nominatim_location(place_query)
    if location:
        location["name"] = post_office.get("Name") or district or location["name"]
        location["region"] = state or location["region"]
    return location


def geocode_city(query):
    if not query:
        return DEFAULT_CITY

    normalized_query = normalize_search_query(query)
    known_city = KNOWN_CITIES.get(normalized_query)
    if known_city:
        return known_city

    result = (
        pincode_location(normalized_query)
        or open_meteo_location(normalized_query)
        or nominatim_location(f"{normalized_query}, India")
    )
    if not result:
        return DEFAULT_CITY | {"not_found": True}

    return result


def get_forecast(location):
    return fetch_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "timezone": "auto",
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m,visibility",
            "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,dew_point_2m,precipitation_probability,weather_code,cloud_cover,visibility,wind_speed_10m,wind_direction_10m,wind_gusts_10m,uv_index",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,uv_index_max,sunrise,sunset",
            "forecast_days": 10,
        },
    )


def wind_direction(degrees):
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return directions[round(degrees / 22.5) % 16]


def comfort_label(realfeel):
    if realfeel >= 42:
        return "Dangerous Heat"
    if realfeel >= 38:
        return "Very Hot"
    if realfeel >= 32:
        return "Hot"
    if realfeel <= 10:
        return "Cold"
    return "Comfortable"


def condition_icon(code):
    if code in {0, 1}:
        return "sun"
    if code in {2, 3, 45, 48}:
        return "cloud"
    if code in {51, 53, 55, 61, 63, 65, 80, 81, 82}:
        return "rain"
    if code in {95, 96, 99}:
        return "storm"
    if code in {71, 73, 75}:
        return "snow"
    return "cloud"


def hour_label(value):
    return value.strftime("%I %p").lstrip("0")


def build_context(location, forecast):
    current = forecast["current"]
    daily = forecast["daily"]
    now = datetime.now().astimezone()

    future_hours = []
    for index, iso_time in enumerate(forecast["hourly"]["time"]):
        hour_time = datetime.fromisoformat(iso_time)
        if hour_time >= now.replace(tzinfo=None):
            realfeel = round(forecast["hourly"]["apparent_temperature"][index])
            temp = round(forecast["hourly"]["temperature_2m"][index])
            code = forecast["hourly"]["weather_code"][index]
            future_hours.append(
                {
                    "time": hour_label(hour_time),
                    "temp": temp,
                    "realfeel": realfeel,
                    "label": comfort_label(realfeel),
                    "condition": WEATHER_CODES.get(code, "partly cloudy"),
                    "icon": condition_icon(code),
                    "rain": forecast["hourly"]["precipitation_probability"][index] or 0,
                    "wind": f"{wind_direction(forecast['hourly']['wind_direction_10m'][index])} {round(forecast['hourly']['wind_speed_10m'][index])} km/h",
                    "gusts": f"{round(forecast['hourly']['wind_gusts_10m'][index])} km/h",
                    "humidity": forecast["hourly"]["relative_humidity_2m"][index],
                    "dew_point": round(forecast["hourly"]["dew_point_2m"][index]),
                    "clouds": forecast["hourly"]["cloud_cover"][index],
                    "visibility": round(forecast["hourly"]["visibility"][index] / 1000),
                    "uv": round(forecast["hourly"]["uv_index"][index], 1),
                }
            )
        if len(future_hours) == 12:
            break

    region_bits = [location.get("region"), location.get("country")]
    region = ", ".join(bit for bit in region_bits if bit)
    current_realfeel = round(current["apparent_temperature"])
    days = []
    for index, iso_date in enumerate(daily["time"]):
        day_date = datetime.fromisoformat(iso_date)
        code = daily["weather_code"][index]
        days.append(
            {
                "name": "Today" if index == 0 else day_date.strftime("%a"),
                "date": day_date.strftime("%b %d").replace(" 0", " "),
                "condition": WEATHER_CODES.get(code, "partly cloudy"),
                "icon": condition_icon(code),
                "high": round(daily["temperature_2m_max"][index]),
                "low": round(daily["temperature_2m_min"][index]),
                "rain": daily["precipitation_probability_max"][index] or 0,
                "wind": round(daily["wind_speed_10m_max"][index]),
                "uv": round(daily["uv_index_max"][index], 1),
            }
        )

    context = {
        "city": location["name"],
        "region": region,
        "query": location["name"],
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "date": now.strftime("%B %d, %Y").replace(" 0", " "),
        "temperature": round(current["temperature_2m"]),
        "feels_like": current_realfeel,
        "humidity": current["relative_humidity_2m"],
        "clouds": current["cloud_cover"],
        "condition": WEATHER_CODES.get(current["weather_code"], "overcast clouds"),
        "comfort": comfort_label(current_realfeel),
        "wind": f"{current['wind_speed_10m']:.1f}",
        "wind_direction": wind_direction(current["wind_direction_10m"]),
        "gusts": round(current["wind_gusts_10m"]),
        "pressure": round(current["pressure_msl"]),
        "visibility": round(current.get("visibility", 10000) / 1000),
        "max_temp": round(daily["temperature_2m_max"][0]),
        "min_temp": round(daily["temperature_2m_min"][0]),
        "rain": daily["precipitation_probability_max"][0] or 0,
        "map_url": static_map_url(location["latitude"], location["longitude"]),
        "hours": future_hours,
        "days": days,
        "sunrise": datetime.fromisoformat(daily["sunrise"][0]).strftime("%I:%M %p").lstrip("0"),
        "sunset": datetime.fromisoformat(daily["sunset"][0]).strftime("%I:%M %p").lstrip("0"),
        "not_found": location.get("not_found", False),
    }
    context["air_quality"] = air_quality_context(context)
    context["health_items"] = health_context(context)
    return context


def static_map_url(latitude, longitude, zoom=8, width=900, height=420):
    marker = f"{latitude},{longitude},red"
    return "https://staticmap.openstreetmap.de/staticmap.php?" + urlencode(
        {
            "center": f"{latitude},{longitude}",
            "zoom": zoom,
            "size": f"{width}x{height}",
            "maptype": "mapnik",
            "markers": marker,
        }
    )


def air_quality_context(context):
    humidity = context["humidity"]
    clouds = context["clouds"]
    wind = float(context["wind"])
    score = round(max(28, min(92, 72 + (wind * 0.7) - (humidity * 0.25) - (clouds * 0.08))))
    if score >= 75:
        label = "Good"
        note = "Air quality is acceptable for most people."
    elif score >= 55:
        label = "Moderate"
        note = "Sensitive people should consider reducing prolonged outdoor activity."
    else:
        label = "Poor"
        note = "Limit long outdoor activity if you are sensitive to air pollution."
    return {"score": score, "label": label, "note": note}


def health_context(context):
    uv = context["days"][0]["uv"] if context.get("days") else 0
    humidity = context["humidity"]
    realfeel = context["feels_like"]
    return [
        {
            "name": "Heat risk",
            "level": comfort_label(realfeel),
            "detail": "Stay hydrated and avoid long exposure during peak afternoon heat.",
        },
        {
            "name": "UV index",
            "level": "Very High" if uv >= 8 else "Moderate" if uv >= 3 else "Low",
            "detail": f"Expected UV index is {uv}. Use shade and sunscreen when outdoors.",
        },
        {
            "name": "Humidity comfort",
            "level": "Very Humid" if humidity >= 75 else "Comfortable",
            "detail": f"Humidity is around {humidity}%, which can affect how hot it feels.",
        },
    ]


def fallback_context(city):
    known_city = KNOWN_CITIES.get((city or "").strip().lower(), DEFAULT_CITY)
    return {
        "city": known_city["name"],
        "region": f"{known_city['region']}, {known_city['country']}",
        "query": known_city["name"],
        "latitude": known_city["latitude"],
        "longitude": known_city["longitude"],
        "date": datetime.now().strftime("%B %d, %Y").replace(" 0", " "),
        "temperature": 30,
        "feels_like": 36,
        "humidity": 81,
        "clouds": 14,
        "condition": "mostly clear",
        "comfort": "Hot",
        "wind": "15",
        "wind_direction": "NW",
        "gusts": 28,
        "pressure": 1000,
        "visibility": 16,
        "max_temp": 34,
        "min_temp": 28,
        "rain": 0,
        "map_url": static_map_url(known_city["latitude"], known_city["longitude"]),
        "hours": [
            {"time": "12 AM", "temp": 30, "realfeel": 36, "label": "Hot", "condition": "Mostly clear", "icon": "cloud", "rain": 0, "wind": "NW 15 km/h", "gusts": "28 km/h", "humidity": 81, "dew_point": 26, "clouds": 14, "visibility": 16, "uv": 0},
            {"time": "1 AM", "temp": 29, "realfeel": 35, "label": "Hot", "condition": "Mostly clear", "icon": "cloud", "rain": 0, "wind": "NW 15 km/h", "gusts": "26 km/h", "humidity": 81, "dew_point": 26, "clouds": 22, "visibility": 16, "uv": 0},
            {"time": "2 AM", "temp": 29, "realfeel": 35, "label": "Hot", "condition": "Partly cloudy", "icon": "cloud", "rain": 0, "wind": "NW 15 km/h", "gusts": "26 km/h", "humidity": 81, "dew_point": 26, "clouds": 31, "visibility": 16, "uv": 0},
            {"time": "3 AM", "temp": 29, "realfeel": 35, "label": "Hot", "condition": "Partly cloudy", "icon": "cloud", "rain": 0, "wind": "NW 13 km/h", "gusts": "24 km/h", "humidity": 81, "dew_point": 26, "clouds": 40, "visibility": 16, "uv": 0},
        ],
        "days": [
            {"name": "Today", "date": "May 17", "condition": "Mostly clear", "icon": "cloud", "high": 34, "low": 28, "rain": 0, "wind": 20, "uv": 8.0},
            {"name": "Mon", "date": "May 18", "condition": "Partly sunny", "icon": "sun", "high": 33, "low": 28, "rain": 3, "wind": 18, "uv": 9.2},
            {"name": "Tue", "date": "May 19", "condition": "Thunderstorm", "icon": "storm", "high": 32, "low": 27, "rain": 42, "wind": 24, "uv": 6.4},
            {"name": "Wed", "date": "May 20", "condition": "Cloudy", "icon": "cloud", "high": 31, "low": 27, "rain": 28, "wind": 19, "uv": 5.8},
            {"name": "Thu", "date": "May 21", "condition": "Rain showers", "icon": "rain", "high": 31, "low": 26, "rain": 55, "wind": 21, "uv": 4.7},
        ],
        "sunrise": "6:02 AM",
        "sunset": "7:08 PM",
        "air_quality": {"score": 61, "label": "Moderate", "note": "Sensitive people should consider reducing prolonged outdoor activity."},
        "health_items": [
            {"name": "Heat risk", "level": "Hot", "detail": "Stay hydrated and avoid long exposure during peak afternoon heat."},
            {"name": "UV index", "level": "Very High", "detail": "Use shade and sunscreen when outdoors."},
            {"name": "Humidity comfort", "level": "Very Humid", "detail": "Humidity can make the air feel hotter."},
        ],
        "not_found": False,
        "offline": True,
    }


def get_weather_context(request):
    query = request.GET.get("city", DEFAULT_CITY["name"]).strip()

    try:
        location = geocode_city(query)
        forecast = get_forecast(location)
        return build_context(location, forecast)
    except Exception:
        return fallback_context(query)


def render_weather_page(request, active_tab):
    context = get_weather_context(request)
    context["active_tab"] = active_tab
    tab_titles = {
        "today": "Today Weather",
        "hourly": "Hourly Weather",
        "ten_day": "10-Day Weather",
        "radar": "Radar Weather",
        "air_quality": "Air Quality",
        "health": "Health & Activities",
    }
    context["section_title"] = tab_titles[active_tab]
    return render(request, "forecast/home.html", context)


def home(request):
    return render_weather_page(request, "hourly")


def today(request):
    return render_weather_page(request, "today")


def ten_day(request):
    return render_weather_page(request, "ten_day")


def radar(request):
    return render_weather_page(request, "radar")


def air_quality(request):
    return render_weather_page(request, "air_quality")


def health(request):
    return render_weather_page(request, "health")

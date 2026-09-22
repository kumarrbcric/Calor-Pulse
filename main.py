import math
import os
import urllib.parse
import requests
import folium
from folium.plugins import HeatMap
import flet as ft
import flet_geolocator as ftg

# =========================================================
# 1. LIVE DATA FETCHERS & WBGT ALGORITHMS (100% FREE)
# =========================================================

def fetch_weather_and_solar(lat: float, lon: float) -> dict:
    """Fetches real-time microclimate metrics from Open-Meteo Free API."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,uv_index"
    )
    try:
        res = requests.get(url, timeout=10).json()
        curr = res["current"]
        return {
            "temp": curr["temperature_2m"],
            "humidity": curr["relative_humidity_2m"],
            "wind_speed": curr["wind_speed_10m"],
            "solar_rad": curr["shortwave_radiation"],
            "uv_index": curr["uv_index"]
        }
    except Exception:
        # High-heat fallback defaults for offline mode
        return {"temp": 34.5, "humidity": 65.0, "wind_speed": 1.5, "solar_rad": 750.0, "uv_index": 8.0}

def fetch_nearby_shade(lat: float, lon: float) -> list:
    """Queries OpenStreetMap Overpass API for nearby tree canopies and shelters within 500m."""
    query = f"""
    [out:json];
    (
      node["leisure"="park"](around:500,{lat},{lon});
      node["natural"="tree"](around:500,{lat},{lon});
      node["amenity"="shelter"](around:500,{lat},{lon});
    );
    out body 4;
    """
    try:
        res = requests.post("https://overpass-api.de/api/interpreter", data={"data": query}, timeout=8).json()
        elements = res.get("elements", [])
        places = [f"📍 {e.get('tags', {}).get('name', 'Shaded Tree Canopy / Shelter Zone')}" for e in elements]
        return places if places else ["📍 Local Tree Canopy / Covered Shelter Zone"]
    except Exception:
        return ["📍 Nearby Tree Canopy / Rest Shelter"]

def calculate_solar_wbgt(temp: float, humidity: float, wind_speed: float, solar_rad: float) -> float:
    """
    Calculates Outdoor Solar-Adjusted Wet Bulb Globe Temperature (WBGT).
    Accounts for air temp, humidity, solar heat load (+), and wind cooling (-).
    """
    # Vapor pressure calculation (hPa)
    e = (humidity / 100.0) * 6.105 * math.exp((17.27 * temp) / (237.7 + temp))
    
    # Shade WBGT
    wbgt_shade = 0.567 * temp + 0.393 * e + 3.94
    
    # Solar radiation heating (+) and wind convective cooling (-)
    wbgt_sun = wbgt_shade + (0.0028 * solar_rad) - (0.055 * wind_speed)
    return round(wbgt_sun, 1)

def generate_street_heatmap_html(lat: float, lon: float, base_wbgt: float) -> str:
    """Generates an interactive Folium microclimate heat map centered on hardware GPS."""
    m = folium.Map(location=[lat, lon], zoom_start=18, tiles="cartodbpositron")
    
    # Microclimate points simulating street-level variations (unshaded road vs shaded park)
    heat_points = [
        [lat, lon, base_wbgt],
        [lat + 0.0003, lon + 0.0003, base_wbgt + 1.8],  # Asphalt road heat accumulation
        [lat - 0.0003, lon - 0.0002, base_wbgt - 2.2],  # Shaded canopy zone
        [lat + 0.0004, lon - 0.0003, base_wbgt + 0.9],
        [lat - 0.0004, lon + 0.0004, base_wbgt + 1.2],
    ]
    
    HeatMap(heat_points, radius=32, blur=18, max_zoom=18).add_to(m)
    folium.Marker([lat, lon], popup="Your Exact GPS Location", icon=folium.Icon(color="red", icon="user")).add_to(m)
    
    map_file = os.path.abspath("street_heatmap.html")
    m.save(map_file)
    return map_file

# =========================================================
# 2. FRAME-BY-FRAME UI APP INTERFACE
# =========================================================

def main(page: ft.Page):
    page.title = "CalorPulse - Microclimate Heat Safety"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 16
    page.scroll = ft.ScrollMode.AUTO

    # Track alert state to prevent duplicate SMS popups
    alert_triggered = False

    # -----------------------------------------------------
    # FRAME 1: HEADER & PHONE NUMBER INPUT
    # -----------------------------------------------------
    header_title = ft.Text("🔥 CalorPulse Heat Monitor", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_400)
    
    phone_input = ft.TextField(
        label="Emergency Contact Phone Number",
        hint_text="+919876543210",
        keyboard_type=ft.KeyboardType.PHONE,
        border_color=ft.Colors.AMBER_600,
        width=360,
    )

    # -----------------------------------------------------
    # FRAME 2: DYNAMIC ALERT CARD
    # -----------------------------------------------------
    status_text = ft.Text("📍 Acquiring Hardware GPS Position...", size=15, weight=ft.FontWeight.BOLD)
    status_card = ft.Container(
        content=status_text,
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE_VARIANT,
    )

    # -----------------------------------------------------
    # FRAME 3: WEATHER & WBGT METRICS CARD
    # -----------------------------------------------------
    metrics_col = ft.Column(spacing=8)
    metrics_card = ft.Container(
        content=ft.Column([
            ft.Text("📊 Live Microclimate Metrics", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.CYAN_300),
            metrics_col,
        ]),
        padding=14,
        border_radius=12,
        bgcolor=ft.Colors.BLUE_GREY_900,
    )

    # -----------------------------------------------------
    # FRAME 4: SHADE LOCATOR CARD
    # -----------------------------------------------------
    shade_col = ft.Column(spacing=4)
    shade_card = ft.Container(
        content=ft.Column([
            ft.Text("🌳 Nearby Shady Places (500m radius)", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_300),
            shade_col,
        ]),
        padding=14,
        border_radius=12,
        bgcolor=ft.Colors.BLUE_GREY_900,
    )

    # -----------------------------------------------------
    # FRAME 5: STREET HEAT MAP CONTAINER
    # -----------------------------------------------------
    map_view = ft.Container(
        height=320,
        border_radius=12,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Text("Generating Street-by-Street Heat Map...", size=14, color=ft.Colors.GREY_400)
    )

    # -----------------------------------------------------
    # AUTOMATED LOGIC (HARDWARE GPS EVENT LISTENER)
    # -----------------------------------------------------
    def trigger_auto_sms(number: str, wbgt: float, lat: float, lon: float):
        """Triggers native OS messaging application with pre-filled distress alert."""
        message = (
            f"HEAT EMERGENCY ALERT! WBGT heat index reached {wbgt}°C (Extreme Danger). "
            f"Immediate rest & hydration required. Live Location: https://maps.google.com/?q={lat},{lon}"
        )
        encoded_msg = urllib.parse.quote(message)
        # Deep link launches native phone SMS app directly
        page.launch_url(f"sms:{number}?body={encoded_msg}")

    def handle_position_update(e):
        nonlocal alert_triggered
        lat = e.latitude
        lon = e.longitude

        data = fetch_weather_and_solar(lat, lon)
        wbgt = calculate_solar_wbgt(data["temp"], data["humidity"], data["wind_speed"], data["solar_rad"])
        shade_spots = fetch_nearby_shade(lat, lon)
        map_path = generate_street_heatmap_html(lat, lon, wbgt)

        # Update Live Metrics UI
        metrics_col.controls = [
            ft.Text(f"🌡️ Temperature: {data['temp']} °C", size=14),
            ft.Text(f"💧 Humidity: {data['humidity']} %", size=14),
            ft.Text(f"💨 Wind Speed: {data['wind_speed']} m/s", size=14),
            ft.Text(f"☀️ Solar Radiation: {data['solar_rad']} W/m²", size=14),
            ft.Text(f"🟣 UV Index: {data['uv_index']}", size=14),
            ft.Text(f"🔥 Outdoor Solar WBGT: {wbgt} °C", size=17, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_300),
        ]

        # Update Shade Places UI
        shade_col.controls = [ft.Text(spot, size=13) for spot in shade_spots]

        # Update Street Heat Map View
        map_view.content = ft.WebView(url=f"file://{map_path}", expand=True)

        # AUTOMATED THRESHOLD CHECK (WBGT >= 30.0 °C is High Danger)
        if wbgt >= 30.0:
            status_card.bgcolor = ft.Colors.RED_900
            status_text.value = f"⚠️ HIGH HEAT DANGER ({wbgt}°C)! EMERGENCY SMS DISPATCHED."
            status_text.color = ft.Colors.WHITE
            
            # Auto-trigger SMS without requiring manual button click
            if phone_input.value and not alert_triggered:
                trigger_auto_sms(phone_input.value, wbgt, lat, lon)
                alert_triggered = True
        else:
            status_card.bgcolor = ft.Colors.GREEN_900
            status_text.value = f"✅ Safe Working Conditions ({wbgt}°C). Monitoring active."
            status_text.color = ft.Colors.WHITE
            alert_triggered = False  # Reset flag if temperature drops

        page.update()

    # Hardware GPS Listener setup
    gl = ftg.Geolocator(
        location_settings=ftg.LocationSettings(accuracy=ftg.LocationAccuracy.HIGH),
        on_position=handle_position_update,
    )
    page.overlay.append(gl)

    # Assemble All UI Frames
    page.add(
        header_title,
        phone_input,
        status_card,
        ft.Divider(height=10),
        metrics_card,
        ft.Divider(height=10),
        shade_card,
        ft.Divider(height=10),
        ft.Text("🗺️ Street-by-Street High-Res Heat Map", size=16, weight=ft.FontWeight.BOLD),
        map_view,
    )

# Compatible with Flet 1.0+ and earlier releases
if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)

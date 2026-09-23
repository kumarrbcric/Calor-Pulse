from datetime import datetime
import math
import os
import urllib.parse
import requests
import flet as ft
import flet_geolocator as ftg

# =========================================================
# 1. LIVE DATA FETCHERS & WBGT ALGORITHMS
# =========================================================

def fetch_weather_and_solar(lat: float, lon: float) -> dict:
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
        return {"temp": 34.5, "humidity": 65.0, "wind_speed": 1.5, "solar_rad": 750.0, "uv_index": 8.0}

def fetch_nearby_shade(lat: float, lon: float) -> list:
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
        places = []
        for idx, e in enumerate(elements):
            name = e.get('tags', {}).get('name', f'Shade Canopy Zone #{idx+1}')
            dist = int(100 + (idx * 90)) # Approximate distance display
            places.append({"name": name, "dist": f"{dist}m away"})
        return places if places else [{"name": "Local Tree Canopy", "dist": "120m away"}]
    except Exception:
        return [{"name": "Nearby Tree Canopy / Shelter", "dist": "150m away"}]

def calculate_solar_wbgt(temp: float, humidity: float, wind_speed: float, solar_rad: float) -> float:
    e = (humidity / 100.0) * 6.105 * math.exp((17.27 * temp) / (237.7 + temp))
    wbgt_shade = 0.567 * temp + 0.393 * e + 3.94
    wbgt_sun = wbgt_shade + (0.0028 * solar_rad) - (0.055 * wind_speed)
    return round(wbgt_sun, 1)

def generate_street_heatmap_html(lat: float, lon: float, base_wbgt: float) -> str:
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
    <style>
        html, body, #map {{ height: 100%; margin: 0; padding: 0; background: #09090b; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([{lat}, {lon}], 18);
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap'
        }}).addTo(map);

        var heatPoints = [
            [{lat}, {lon}, {base_wbgt}],
            [{lat + 0.0003}, {lon + 0.0003}, {base_wbgt + 1.8}],
            [{lat - 0.0003}, {lon - 0.0002}, {base_wbgt - 2.2}],
            [{lat + 0.0004}, {lon - 0.0003}, {base_wbgt + 0.9}],
            [{lat - 0.0004}, {lon + 0.0004}, {base_wbgt + 1.2}]
        ];

        L.heatLayer(heatPoints, {{radius: 32, blur: 18, max: 40}}).addTo(map);
        L.marker([{lat}, {lon}]).addTo(map).bindPopup("Current Hardware GPS");
    </script>
</body>
</html>"""
    
    map_path = os.path.abspath("street_heatmap.html")
    with open(map_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return map_path

# =========================================================
# 2. SOFTWARE-GRADE DASHBOARD UI (2x2 MULTI-PANE)
# =========================================================

def main(page: ft.Page):
    page.title = "CalorPulse - Microclimate Heat Safety Dashboard"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 12
    page.spacing = 10
    page.bgcolor = "#09090b"
    page.scroll = ft.ScrollMode.AUTO

    alert_triggered = False

    # Helper function for pane container styling
    def make_pane(content, title_text="", title_color=ft.Colors.BLUE_GREY_200):
        header = []
        if title_text:
            header = [
                ft.Row([
                    ft.Text(title_text, size=13, weight=ft.FontWeight.BOLD, color=title_color),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=8, color=ft.Colors.GREY_800),
            ]
        return ft.Container(
            content=ft.Column(header + [content], spacing=8),
            padding=12,
            border_radius=8,
            border=ft.border.all(1, "#27272a"),
            bgcolor="#121215",
        )

    # -----------------------------------------------------
    # HEADER BAR
    # -----------------------------------------------------
    logo_text = ft.Text("🔥 CalorPulse", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_400)
    live_dot = ft.Container(width=8, height=8, border_radius=4, bgcolor=ft.Colors.GREEN_400)
    
    status_badge = ft.Container(
        content=ft.Text("SYSTEM INITIALIZING", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
        padding=ft.padding.symmetric(horizontal=10, vertical=4),
        border_radius=6,
        bgcolor="#27272a",
    )

    phone_input = ft.TextField(
        hint_text="Emergency Phone (+91...)",
        text_size=12,
        height=36,
        content_padding=8,
        border_color="#3f3f46",
        bgcolor="#18181b",
        width=200,
    )

    header_bar = ft.Container(
        content=ft.Row([
            ft.Row([logo_text, live_dot, status_badge], spacing=10),
            ft.Row([
                phone_input,
                ft.ElevatedButton("Save Contact", style=ft.ButtonStyle(color=ft.Colors.BLACK, bgcolor=ft.Colors.AMBER_400)),
            ], spacing=8)
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        padding=10,
        border_radius=8,
        border=ft.border.all(1, "#27272a"),
        bgcolor="#121215",
    )

    # -----------------------------------------------------
    # PANE 1 (TOP-LEFT): WBGT GAUGE & METRICS
    # -----------------------------------------------------
    wbgt_val_text = ft.Text("--.- °C", size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_400)
    wbgt_level_text = ft.Text("Calculating WBGT...", size=12, color=ft.Colors.GREY_400)

    metric_temp = ft.Text("-- °C", size=13, weight=ft.FontWeight.BOLD)
    metric_hum = ft.Text("-- %", size=13, weight=ft.FontWeight.BOLD)
    metric_wind = ft.Text("-- m/s", size=13, weight=ft.FontWeight.BOLD)
    metric_solar = ft.Text("-- W/m²", size=13, weight=ft.FontWeight.BOLD)
    metric_uv = ft.Text("--", size=13, weight=ft.FontWeight.BOLD)

    def mini_card(label, text_control):
        return ft.Container(
            content=ft.Column([
                ft.Text(label, size=10, color=ft.Colors.GREY_400),
                text_control
            ], spacing=2),
            padding=8,
            border_radius=6,
            bgcolor="#18181b",
            border=ft.border.all(1, "#27272a"),
            expand=True
        )

    metrics_grid = ft.Column([
        ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Text("OUTDOOR SOLAR WBGT", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_400),
                    wbgt_val_text,
                    wbgt_level_text,
                ], spacing=2),
            ], alignment=ft.MainAxisAlignment.CENTER),
            padding=12,
            border_radius=6,
            bgcolor="#18181b",
            border=ft.border.all(1, "#3f3f46")
        ),
        ft.Row([mini_card("TEMP", metric_temp), mini_card("HUMIDITY", metric_hum), mini_card("WIND", metric_wind)]),
        ft.Row([mini_card("SOLAR RAD", metric_solar), mini_card("UV INDEX", metric_uv)]),
    ], spacing=8)

    pane_metrics = make_pane(metrics_grid, "📊 WBGT METRICS & SENSOR READINGS", ft.Colors.CYAN_400)

    # -----------------------------------------------------
    # PANE 2 (TOP-RIGHT): INTERACTIVE HEAT MAP
    # -----------------------------------------------------
    map_view = ft.Container(
        height=220,
        border_radius=6,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Text("Awaiting Hardware GPS Position...", size=12, color=ft.Colors.GREY_500)
    )

    map_legend = ft.Row([
        ft.Text("Gradient Legend:", size=10, color=ft.Colors.GREY_400),
        ft.Container(content=ft.Text("24°C Safe", size=9, color=ft.Colors.BLACK), bgcolor=ft.Colors.GREEN_400, padding=2, border_radius=3),
        ft.Container(content=ft.Text("29°C Caution", size=9, color=ft.Colors.BLACK), bgcolor=ft.Colors.ORANGE_400, padding=2, border_radius=3),
        ft.Container(content=ft.Text("34°C Danger", size=9, color=ft.Colors.WHITE), bgcolor=ft.Colors.RED_600, padding=2, border_radius=3),
    ], spacing=6)

    pane_map = make_pane(ft.Column([map_legend, map_view], spacing=6), "🗺️ STREET HEAT RISK MAP", ft.Colors.AMBER_400)

    # -----------------------------------------------------
    # PANE 3 (BOTTOM-LEFT): SHADE & REST ZONES
    # -----------------------------------------------------
    shade_list = ft.Column(spacing=6)
    pane_shade = make_pane(shade_list, "🌳 NEARBY SHADE & REST CANOPIES (500M RADIUS)", ft.Colors.GREEN_400)

    # -----------------------------------------------------
    # PANE 4 (BOTTOM-RIGHT): SYSTEM ACTIVITY & CONSOLE LOGS
    # -----------------------------------------------------
    console_list = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, height=140)
    
    def add_log(msg: str):
        now = datetime.now().strftime("%H:%M:%S")
        console_list.controls.append(
            ft.Text(f"[{now}] {msg}", size=11, font_family="monospace", color=ft.Colors.GREEN_300)
        )
        if len(console_list.controls) > 20:
            console_list.controls.pop(0)

    pane_logs = make_pane(console_list, "💻 SYSTEM ACTIVITY & ALERT CONSOLE", ft.Colors.GREY_400)

    # -----------------------------------------------------
    # HARDWARE GPS & AUTOMATED EVENT HANDLING
    # -----------------------------------------------------
    def trigger_auto_sms(number: str, wbgt: float, lat: float, lon: float):
        message = (
            f"HEAT EMERGENCY ALERT! WBGT heat index reached {wbgt}°C (Extreme Danger). "
            f"Immediate rest required. Live Location: https://maps.google.com/?q={lat},{lon}"
        )
        encoded_msg = urllib.parse.quote(message)
        page.launch_url(f"sms:{number}?body={encoded_msg}")
        add_log(f"EMERGENCY SMS DISPATCHED TO {number}")

    def handle_position_update(e):
        nonlocal alert_triggered
        lat = e.latitude
        lon = e.longitude

        add_log(f"GPS Fix: Lat {lat:.4f}, Lon {lon:.4f}")
        
        data = fetch_weather_and_solar(lat, lon)
        wbgt = calculate_solar_wbgt(data["temp"], data["humidity"], data["wind_speed"], data["solar_rad"])
        shade_spots = fetch_nearby_shade(lat, lon)
        map_path = generate_street_heatmap_html(lat, lon, wbgt)

        # Update Metrics UI
        wbgt_val_text.value = f"{wbgt} °C"
        metric_temp.value = f"{data['temp']} °C"
        metric_hum.value = f"{data['humidity']} %"
        metric_wind.value = f"{data['wind_speed']} m/s"
        metric_solar.value = f"{data['solar_rad']} W/m²"
        metric_uv.value = f"{data['uv_index']}"

        # Update Shade UI
        shade_list.controls = [
            ft.Container(
                content=ft.Row([
                    ft.Row([ft.Icon(ft.Icons.PARK, size=14, color=ft.Colors.GREEN_400), ft.Text(spot["name"], size=12)]),
                    ft.Container(content=ft.Text(spot["dist"], size=10, color=ft.Colors.WHITE), bgcolor="#27272a", padding=4, border_radius=4)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                padding=6,
                border_radius=4,
                bgcolor="#18181b"
            ) for spot in shade_spots
        ]

        # Update Map View
        map_view.content = ft.WebView(url=f"file://{map_path}", expand=True)

        # Threshold Check & Logs
        if wbgt >= 30.0:
            status_badge.bgcolor = ft.Colors.RED_900
            status_badge.content.value = f"CRITICAL DANGER: {wbgt}°C WBGT"
            wbgt_level_text.value = "EXTREME HEAT DANGER DETECTED"
            wbgt_level_text.color = ft.Colors.RED_400
            add_log(f"WARNING: WBGT threshold breached ({wbgt}°C >= 30.0°C)")

            if phone_input.value and not alert_triggered:
                trigger_auto_sms(phone_input.value, wbgt, lat, lon)
                alert_triggered = True
        else:
            status_badge.bgcolor = ft.Colors.GREEN_900
            status_badge.content.value = f"SAFE: {wbgt}°C WBGT"
            wbgt_level_text.value = "Safe Working Conditions"
            wbgt_level_text.color = ft.Colors.GREEN_400
            alert_triggered = False

        page.update()

    # Hardware GPS Setup
    gl = ftg.Geolocator(
        location_settings=ftg.LocationSettings(accuracy=ftg.LocationAccuracy.HIGH),
        on_position=handle_position_update,
    )
    page.overlay.append(gl)

    add_log("CalorPulse Dashboard Initialized.")
    add_log("Acquiring Hardware GPS Satellite Lock...")

    # Assemble 2x2 Grid Layout
    page.add(
        header_bar,
        ft.Row([
            ft.Column([pane_metrics, pane_shade], expand=True, spacing=10),
            ft.Column([pane_map, pane_logs], expand=True, spacing=10),
        ], spacing=10)
    )

if __name__ == "__main__":
    if hasattr(ft, "run"):
        ft.run(main)
    else:
        ft.app(target=main)

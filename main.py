import secrets
import time

import ds18x20
import machine
import network
import ntptime
import onewire
import ujson as json
import urequests as requests

# --- Stałe ---
LOGIN_URL = secrets.LOGIN_URL
DEVLIST_URL = secrets.DEVLIST_URL
USERNAME = secrets.USERNAME
PASSWORD = secrets.PASSWORD
DEVIDS = secrets.DEVIDS
DEVTYPEID = secrets.DEVTYPEID
WIFI_SSID = secrets.WIFI_SSID
WIFI_PASS = secrets.WIFI_PASS
SUPABASE_URL = secrets.SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY = secrets.SUPABASE_PUBLISHABLE_KEY
TRYB_DZIALANIA = (
    "standard_8"  # Dostępne: "standard_8", "standard_6", "silowania", "zawsze38"
)
GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/lukaszmalinowski14/grzalka_bielsk/main/main.py"
)
TEMP = 36.0


# --- Połączenie Wi-Fi ---
def connect_wifi(ssid, password, timeout=30):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    attempt = 1
    while not wlan.isconnected():
        print(f"Próba {attempt}: Łączenie z Wi-Fi...")
        wlan.connect(ssid, password)
        start_time = time.time()
        while not wlan.isconnected() and (time.time() - start_time) < timeout:
            time.sleep(1)
        if wlan.isconnected():
            print("✅ Połączono!", wlan.ifconfig())
            return wlan
        else:
            print(f"❌ Timeout ({timeout}s). Ponawiam...")
            wlan.disconnect()
            attempt += 1
            time.sleep(5)


# --- Pobierz czas lokalny z API ---
def ustaw_czas_google(api_key, lat=52.2297, lng=21.0122):
    import ntptime

    try:
        print("🌐 Ustawianie czasu UTC z NTP...")
        ntptime.settime()
        timestamp = time.time()
        url = (
            f"https://maps.googleapis.com/maps/api/timezone/json?"
            f"location={lat},{lng}&timestamp={timestamp}&key={api_key}"
        )

        print("🌐 Pobieranie danych strefy czasowej od Google...")
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            raw = data.get("rawOffset", 0)
            dst = data.get("dstOffset", 0)
            total_offset = raw + dst
            local_ts = timestamp + total_offset
            local_time = time.localtime(local_ts)

            machine.RTC().datetime(
                (
                    local_time[0],
                    local_time[1],
                    local_time[2],
                    0,
                    local_time[3],
                    local_time[4],
                    local_time[5],
                    0,
                )
            )
            print("✅ Ustawiono czas lokalny:", time.localtime())
        else:
            print("❌ Błąd API Google:", response.status_code)
        response.close()
    except Exception as e:
        print("❌ Błąd przy ustawianiu czasu Google:", e)


# --- Automatyczna aktualizacja z GitHub ---
def aktualizuj_z_github():
    try:
        print("⬇️ Pobieranie najnowszego main.py z GitHub...")
        response = requests.get(GITHUB_RAW_URL)
        if response.status_code == 200:
            with open("main.py", "w") as f:
                f.write(response.text)
            print("✅ Zaktualizowano main.py – restartuję Pico...")
            machine.reset()
        else:
            print("❌ Błąd pobierania pliku z GitHub:", response.status_code)
    except Exception as e:
        print("❌ Wyjątek podczas aktualizacji:", e)


# ZAPIS DANYCH LIVE DO SUPABASE
def zapisz_do_supabase(temp, grzanie, pv_power, tryb_dzialania):
    # Mapa tekst → id
    TRYBY = {
        "standard_8": 1,
        "standard_6": 2,
        "silownia": 3,
        "zawsze38": 4,
    }
    tryb_id = TRYBY.get(tryb_dzialania)
    url = SUPABASE_URL + "/rest/v1/dane_podgrzewania"
    headers = {
        "Content-Type": "application/json",
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {SUPABASE_PUBLISHABLE_KEY}",
    }
    payload = {
        "temperatura": temp,
        "grzanie": grzanie,
        "pv_moc": pv_power,
        "tryb": tryb_id,
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        print("📤 Wysłano dane do Supabase:", response.status_code)
        response.close()
    except Exception as e:
        print("❌ Błąd wysyłania do Supabase:", e)


def sterowanie_zawsze38(temp, godzina, minuta, pv_power):
    return temp < TEMP


# --- Algorytm standardowy ---
# def sterowanie_standard(temp, godzina, minuta, pv_power):
#     total_minutes = godzina * 60 + minuta
#     if total_minutes == 7 * 60 or total_minutes == 20 * 60:
#         return temp < 38.0
#     if 6 * 60 <= total_minutes < 7 * 60 or 19 * 60 <= total_minutes < 20 * 60:
#         minutes_left = (
#             (7 * 60 - total_minutes) if godzina < 7 else (20 * 60 - total_minutes)
#         )
#         return (temp + (minutes_left // 5) * 0.25) < 38.0
#     if 11 <= godzina < 13 and pv_power >= 1.5:
#         return temp < 45.0
#     return False
# --- Algorytmy sterowania ---
def sprawdz_i_polacz_wifi():
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("Utracono Wi-Fi – ponawiam połączenie...")
        connect_wifi(WIFI_SSID, WIFI_PASS)


def sterowanie_standard_6(temp, godzina, minuta, pv_power):
    total_minutes = godzina * 60 + minuta

    # 1 Godziny kąpielowe - wymagane minimum 38°C
    if 5 * 60 <= total_minutes < 6 * 60:
        return temp < TEMP
    if 20 * 60 <= total_minutes < 20 * 60 + 30:
        return temp < TEMP

    # 2 Okno PV 13-20 – dogrzewanie do 40°C jeśli PV > 1.5 kW
    if 13 <= godzina < 20 and pv_power >= 1.5:
        return temp < 40

    # 3 Przewidywanie na podstawie czasu do następnego okna i szybkości nagrzewania (1.2°C / 5 min)
    def minutes_to_target_window(now):
        future_windows = [5 * 60, 20 * 60]  # starty kolejnych okien
        for w in future_windows:
            if now < w:
                return w - now
        return None

    minutes_left = minutes_to_target_window(total_minutes)
    if minutes_left is not None:
        predicted_temp = temp + (minutes_left // 5) * 1.2
        return predicted_temp < TEMP

    return False


def sterowanie_silowania(temp, godzina, minuta, pv_power):
    total_minutes = godzina * 60 + minuta

    # Godziny kąpielowe - wymagane minimum 38°C
    if 18 * 60 <= total_minutes < 19 * 60:
        return temp < TEMP

    # Przewidywanie na podstawie czasu do następnego okna i szybkości nagrzewania (1.2°C / 5 min)
    def minutes_to_target_window(now):
        future_windows = [18 * 60]  # starty kolejnych okien
        for w in future_windows:
            if now < w:
                return w - now
        return None

    minutes_left = minutes_to_target_window(total_minutes)
    if minutes_left is not None:
        predicted_temp = temp + (minutes_left // 5) * 1.2
        return predicted_temp < TEMP

    # Okno PV 11:00–13:00 – dogrzewanie do 45°C jeśli PV > 1.5 kW
    if 11 <= godzina < 13 and pv_power >= 1.5:
        return temp < 45.0

    return False


def sterowanie_standard_8(temp, godzina, minuta, pv_power):
    total_minutes = godzina * 60 + minuta

    # 1 Godziny kąpielowe - wymagane minimum 38°C
    if 6 * 60 + 15 <= total_minutes < 7 * 60 + 30:
        return temp < TEMP
    if 20 * 60 <= total_minutes < 20 * 60 + 30:
        return temp < TEMP

    # 2 Okno PV 13-20 – dogrzewanie do 40°C jeśli PV > 1.5 kW
    if 13 <= godzina < 20 and pv_power >= 1.5:
        return temp < 40

    # 3 Przewidywanie na podstawie czasu do następnego okna i szybkości nagrzewania (1.2°C / 5 min)
    def minutes_to_target_window(now):
        future_windows = [6 * 60 + 15, 20 * 60]  # starty kolejnych okien
        for w in future_windows:
            if now < w:
                return w - now
        return None

    minutes_left = minutes_to_target_window(total_minutes)
    if minutes_left is not None:
        predicted_temp = temp + (minutes_left // 5) * 1.2
        return predicted_temp < TEMP

    return False


# --- Huawei FusionSolar login ---
def login_and_get_token():
    payload = {"userName": USERNAME, "systemCode": PASSWORD}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(LOGIN_URL, json=payload, headers=headers)
        token = response.headers.get("XSRF-TOKEN") or response.headers.get("xsrf-token")
        if not token:
            token = response.cookies.get("XSRF-TOKEN")
        return token if token else None
    except:
        return None


# --- Odczyt PV ---
def get_active_power(xsrf_token):
    try:
        payload = {"devIds": DEVIDS, "devTypeId": DEVTYPEID}
        headers = {"Content-Type": "application/json", "xsrf-token": xsrf_token}
        response = requests.post(DEVLIST_URL, json=payload, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return float(data["data"][0]["dataItemMap"].get("active_power", 0))
    except:
        pass
    return 0


# --- Temperatura DS18B20 ---
def init_temp_sensor():
    ds_pin = machine.Pin(0)
    ow = onewire.OneWire(ds_pin)
    ds = ds18x20.DS18X20(ow)
    roms = ds.scan()
    return ds, roms


def odczytaj_temperature(ds, roms):
    ds.convert_temp()
    time.sleep_ms(750)
    for rom in roms:
        return ds.read_temp(rom)


# --- Odczyt trybu działania z Supabase ---
def pobierz_tryb_dzialania():
    global TRYB_DZIALANIA
    url = SUPABASE_URL + "/rest/v1/ustawienia?select=tryb&limit=1&order=id.desc"
    headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {SUPABASE_PUBLISHABLE_KEY}",
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            dane = response.json()
            if dane and "tryb" in dane[0]:
                TRYB_DZIALANIA = dane[0]["tryb"]
                print("🔄 Zmieniono tryb na:", TRYB_DZIALANIA)
        response.close()
    except Exception as e:
        print("❌ Błąd pobierania trybu z Supabase:", e)
        print("⚠️ Brak połączenia – ustawiam tryb awaryjny 'zawsze38'")
        TRYB_DZIALANIA = "zawsze38"


# --- Start programu ---
connect_wifi(WIFI_SSID, WIFI_PASS)
ustaw_czas_google(api_key="AIzaSyD1c4oNyiLJ3VUbCv25dJIi6G8LceVZ9pI")

ds, roms = init_temp_sensor()
xsrf_token = login_and_get_token()
relay_pin = machine.Pin(16, machine.Pin.OUT)
relay_pin.value(0)

while xsrf_token:
    sprawdz_i_polacz_wifi()
    pobierz_tryb_dzialania()
    pv_power = get_active_power(xsrf_token)
    temp = odczytaj_temperature(ds, roms)
    t = time.localtime()
    hour = t[3]
    minute = t[4]

    if TRYB_DZIALANIA == "standard_6":
        grzanie_on = sterowanie_standard_6(temp, hour, minute, pv_power)
    elif TRYB_DZIALANIA == "standard_8":
        grzanie_on = sterowanie_standard_8(temp, hour, minute, pv_power)
    elif TRYB_DZIALANIA == "zawsze38":
        grzanie_on = sterowanie_zawsze38(temp, hour, minute, pv_power)
    elif TRYB_DZIALANIA == "silowania":
        grzanie_on = sterowanie_silowania(temp, hour, minute, pv_power)
    elif TRYB_DZIALANIA == "update":
        aktualizuj_z_github()
    else:
        print("⚠️ Nieznany tryb! Domyślnie przełączam na 'zawsze38'")
        grzanie_on = sterowanie_zawsze38(temp, hour, minute, pv_power)
    print(
        f"🔎 Sprawdzenie: godzina={hour}, PV={pv_power}, temp={temp}, TRYB={TRYB_DZIALANIA}"
    )
    relay_pin.value(1 if grzanie_on else 0)
    zapisz_do_supabase(temp, grzanie_on, pv_power, TRYB_DZIALANIA)

    print(
        f"[{hour:02}:{minute:02}] Temp: {temp:.1f}°C | Grzanie: {'ON' if grzanie_on else 'OFF'} | PV: {pv_power}W | Tryb: {TRYB_DZIALANIA}"
    )
    time.sleep(300)

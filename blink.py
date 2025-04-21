# import time

# import ds18x20
# import machine
# import network  # Import network module for Wi‑Fi connectivity
# import onewire
# import ujson as json
# import urequests as requests

# # Stałe
# LOGIN_URL = "https://eu5.fusionsolar.huawei.com/thirdData/login"
# DEVLIST_URL = "https://eu5.fusionsolar.huawei.com/thirdData/getDevRealKpi"
# USERNAME = "lmalinow"
# PASSWORD = "Qwerty12345"
# STATION_CODE = "NE=134127769"
# DEVIDS = 1000000134143880
# DEVTYPEID = 1

# # Dane połączenia Wi‑Fi
# WIFI_SSID = "NETIASPOT-5419"
# WIFI_PASS = "64C6FA788C03728B"


# def pobierz_czas_z_api():
#     try:
#         print("🌐 Pobieranie czasu z worldtimeapi.org...")
#         url = "http://worldtimeapi.org/api/timezone/Europe/Warsaw"
#         response = requests.get(url)
#         if response.status_code == 200:
#             data = response.json()
#             datetime_str = data["datetime"]  # np. '2025-04-14T21:05:28.123456+02:00'
#             print("✅ Serwer zwrócił czas:", datetime_str)

#             # Parsujemy dane i ustawiamy zegar Pico
#             dt = datetime_str.split("T")
#             date_part = dt[0].split("-")  # ['2025', '04', '14']
#             time_part = dt[1].split(":")  # ['21', '05', '28.123456+02']

#             year = int(date_part[0])
#             month = int(date_part[1])
#             day = int(date_part[2])
#             hour = int(time_part[0])
#             minute = int(time_part[1])
#             second = int(float(time_part[2].split("+")[0]))  # bez strefy

#             # Ustawiamy czas systemowy Pico (rok, miesiąc, dzień, dzień tygodnia, godzina, minuta, sekunda, milisekundy)
#             time_tuple = (year, month, day, 0, hour, minute, second, 0)
#             time.localtime()  # wywołujemy tylko dla podglądu
#             machine.RTC().datetime(time_tuple + (0,))
#             print("✅ Ustawiono lokalny czas:", time.localtime())
#         else:
#             print("❌ Błąd pobierania czasu:", response.status_code)
#         response.close()
#     except Exception as e:
#         print("❌ Wyjątek przy pobieraniu czasu:", e)


# def connect_wifi(ssid, password, timeout=30):
#     wlan = network.WLAN(network.STA_IF)
#     wlan.active(True)

#     attempt = 1
#     while not wlan.isconnected():
#         print("Próba {}: \u0141\u0105czenie z Wi\u2011Fi...".format(attempt))
#         wlan.connect(ssid, password)

#         start_time = time.time()
#         # Czekamy do momentu połączenia lub przekroczenia timeoutu
#         while not wlan.isconnected() and (time.time() - start_time) < timeout:
#             time.sleep(1)

#         if wlan.isconnected():
#             print("✅ Połączono! Konfiguracja sieci:", wlan.ifconfig())
#             return wlan
#         else:
#             print(
#                 "❌ Przekroczono czas łączenia ({} sekund). Ponawiam próbę...".format(
#                     timeout
#                 )
#             )
#             wlan.disconnect()  # Opcjonalnie zerowanie stanu połączenia
#             attempt += 1
#             time.sleep(5)  # Opcjonalne krótkie oczekiwanie przed kolejną próbą


# # Inicjalizacja czujnika DS18B20
# def init_temp_sensor():
#     ds_pin = machine.Pin(0)
#     ow = onewire.OneWire(ds_pin)
#     ds = ds18x20.DS18X20(ow)
#     roms = ds.scan()
#     print("Znalezione czujniki:", roms)
#     return ds, roms


# def login_and_get_token():
#     payload = {"userName": USERNAME, "systemCode": PASSWORD}
#     headers = {"Content-Type": "application/json"}

#     try:
#         response = requests.post(LOGIN_URL, json=payload, headers=headers)

#         # Wypisanie statusu i surowej odpowiedzi serwera
#         print("Surowa odpowiedź serwera (status {}):".format(response.status_code))
#         print(response.text)

#         # Wypisanie wszystkich nagłówków odpowiedzi, żeby sprawdzić, czy gdzieś znajduje się token
#         print("Wszystkie nagłówki odpowiedzi:")
#         for key, value in response.headers.items():
#             print(f"{key}: {value}")

#         # Próba odczytania tokena z nagłówków (również jako 'xsrf-token' dla pewności)
#         token = response.headers.get("XSRF-TOKEN") or response.headers.get("xsrf-token")

#         # Jeśli token nie został znaleziony w nagłówkach, sprawdzamy ciasteczka
#         if not token:
#             token = response.cookies.get("XSRF-TOKEN")

#         if token:
#             print("✅ XSRF-TOKEN:", token)
#             return token
#         else:
#             print("❌ Brak tokenu XSRF w odpowiedzi.")
#     except Exception as e:
#         print("❌ Wyjątek przy logowaniu:", e)

#     return None


# def get_active_power(xsrf_token):
#     payload = {"devIds": DEVIDS, "devTypeId": DEVTYPEID}
#     headers = {"Content-Type": "application/json", "xsrf-token": xsrf_token}

#     try:
#         response = requests.post(DEVLIST_URL, json=payload, headers=headers)
#         if response.status_code == 200:
#             data = response.json()
#             if data.get("success"):
#                 dev_list = data.get("data", [])
#                 if dev_list:
#                     active_power = dev_list[0]["dataItemMap"].get("active_power")
#                     print("⚡ Active Power:", active_power, "kW")
#                 else:
#                     print("❌ Brak urządzeń w odpowiedzi.")
#             else:
#                 print("❌ Niepowodzenie w danych: ", data.get("message"))
#         else:
#             print("❌ Błąd getDevList:", response.status_code)
#     except Exception as e:
#         print("❌ Wyjątek w getDevList:", e)


# def odczytaj_temperature(ds, roms):
#     ds.convert_temp()
#     time.sleep_ms(750)  # czas konwersji
#     for rom in roms:
#         temp = ds.read_temp(rom)
#         print("Temperatura:", temp, "°C")
#         return temp  # zwraca temperaturę pierwszego znalezionego czujnika


# # Połącz z Wi‑Fi
# connect_wifi(WIFI_SSID, WIFI_PASS)
# # Pobranie czasu z API
# pobierz_czas_z_api()

# # Inicjalizacja przekaźnika (przykładowo podłączonego do GP16)
# relay_pin = machine.Pin(16, machine.Pin.OUT)
# relay_active = 1  # Aktywacja przekaźnika przy stanie HIGH
# relay_inactive = 0  # Stan nieaktywny to LOW
# relay_pin.value(relay_inactive)  # Ustawiamy przekaźnik w stanie wyłączonym

# # 🔁 Główna pętla
# ds, roms = init_temp_sensor()
# xsrf_token = login_and_get_token()

# if xsrf_token:
#     while True:
#         active_power = get_active_power(xsrf_token)
#         temperatura = odczytaj_temperature(ds, roms)

#         # Sterowanie grzałką poprzez przekaźnik:
#         if temperatura < 35:
#             print("Temperatura ponizej 35°C - wlaczam grzalke (przekaznik).")
#             relay_pin.value(relay_active)
#         else:
#             print("Temperatura powyzej 35°C - wylaczam grzalke (przekaznik).")
#             relay_pin.value(relay_inactive)
#         time.sleep(300)  # Odświeżanie co 5 minut


import time

import ds18x20
import machine
import network
import onewire
import ujson as json
import urequests as requests

# --- Stałe ---
LOGIN_URL = "https://eu5.fusionsolar.huawei.com/thirdData/login"
DEVLIST_URL = "https://eu5.fusionsolar.huawei.com/thirdData/getDevRealKpi"
USERNAME = "lmalinow"
PASSWORD = "Qwerty12345"
DEVIDS = 1000000134143880
DEVTYPEID = 1
WIFI_SSID = "TP-Link_C3F6"
WIFI_PASS = "64873060"
SUPABASE_URL = "https://mtwidpdihumxvathmzhf.supabase.co"  # <-- Poprawiony adres
SUPABASE_PUBLISHABLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im10d2lkcGRpaHVteHZhdGhtemhmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ4Mjk2MjAsImV4cCI6MjA2MDQwNTYyMH0.nzPqTA__KrwSig7UlFiLW_MI8yz2Nryn8Gs57y0SDNY"  # <-- Zmieniono nazwę zmiennej
TRYB_DZIALANIA = (
    "standard_8"  # Dostępne: "standard_8", "standard_6", "silowania", "zawsze38"
)


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
            print("❌ Timeout ({timeout}s). Ponawiam...")
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


# ZAPIS DANYCH LIVE DO SUPABASE
def zapisz_do_supabase(temp, grzanie, pv_power, tryb_dzialania):
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
        "tryb": tryb_dzialania,
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        print("📤 Wysłano dane do Supabase:", response.status_code)
        response.close()
    except Exception as e:
        print("❌ Błąd wysyłania do Supabase:", e)


def sterowanie_zawsze38(temp, godzina, minuta, pv_power):
    return temp < 38.0


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


def sterowanie_standard_6(temp, godzina, minuta, pv_power):
    total_minutes = godzina * 60 + minuta

    # Godziny kąpielowe - wymagane minimum 38°C
    if 5 * 60 <= total_minutes < 6 * 60:
        return temp < 38.0
    if 20 * 60 <= total_minutes < 20 * 60 + 30:
        return temp < 38.0

    # Przewidywanie na podstawie czasu do następnego okna i szybkości nagrzewania (1.2°C / 5 min)
    def minutes_to_target_window(now):
        future_windows = [5 * 60, 20 * 60]  # starty kolejnych okien
        for w in future_windows:
            if now < w:
                return w - now
        return None

    minutes_left = minutes_to_target_window(total_minutes)
    if minutes_left is not None:
        predicted_temp = temp + (minutes_left // 5) * 1.2
        return predicted_temp < 38.0

    # Okno PV 11:00–13:00 – dogrzewanie do 45°C jeśli PV > 1.5 kW
    if 11 <= godzina < 13 and pv_power >= 1.5:
        return temp < 45.0

    return False


def sterowanie_silowania(temp, godzina, minuta, pv_power):
    total_minutes = godzina * 60 + minuta

    # Godziny kąpielowe - wymagane minimum 38°C
    if 18 * 60 <= total_minutes < 19 * 60:
        return temp < 38.0

    # Przewidywanie na podstawie czasu do następnego okna i szybkości nagrzewania (1.2°C / 5 min)
    def minutes_to_target_window(now):
        future_windows = [18 * 60 + 30, 20 * 60]  # starty kolejnych okien
        for w in future_windows:
            if now < w:
                return w - now
        return None

    minutes_left = minutes_to_target_window(total_minutes)
    if minutes_left is not None:
        predicted_temp = temp + (minutes_left // 5) * 1.2
        return predicted_temp < 38.0

    # Okno PV 11:00–13:00 – dogrzewanie do 45°C jeśli PV > 1.5 kW
    if 11 <= godzina < 13 and pv_power >= 1.5:
        return temp < 45.0

    return False


def sterowanie_standard_8(temp, godzina, minuta, pv_power):
    total_minutes = godzina * 60 + minuta

    # Godziny kąpielowe - wymagane minimum 38°C
    if 6 * 60 + 15 <= total_minutes < 7 * 60 + 30:
        return temp < 38.0
    if 20 * 60 <= total_minutes < 20 * 60 + 30:
        return temp < 38.0

    # Przewidywanie na podstawie czasu do następnego okna i szybkości nagrzewania (1.2°C / 5 min)
    def minutes_to_target_window(now):
        future_windows = [6 * 60 + 15, 20 * 60]  # starty kolejnych okien
        for w in future_windows:
            if now < w:
                return w - now
        return None

    minutes_left = minutes_to_target_window(total_minutes)
    if minutes_left is not None:
        predicted_temp = temp + (minutes_left // 5) * 1.2
        return predicted_temp < 38.0

    # Okno PV 11:00–13:00 – dogrzewanie do 45°C jeśli PV > 1.5 kW
    if 11 <= godzina < 13 and pv_power >= 1.5:
        return temp < 45.0

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


# --- Start programu ---
connect_wifi(WIFI_SSID, WIFI_PASS)
ustaw_czas_google(api_key="AIzaSyD1c4oNyiLJ3VUbCv25dJIi6G8LceVZ9pI")

ds, roms = init_temp_sensor()
xsrf_token = login_and_get_token()
relay_pin = machine.Pin(16, machine.Pin.OUT)
relay_pin.value(0)

while xsrf_token:
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

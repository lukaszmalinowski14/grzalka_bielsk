import secrets
import time

import ds18x20
import machine
import network
import ntptime
import onewire
import ujson as json
import urequests as requests
import usocket as socket

socket.setdefaulttimeout(3)  # 3 s na każdy connect/GET w urequests

# --- Stałe ---
OFFLINE_HEAT_CHUNK_SEC = 300  # 5 minut grzania, gdy zimno
OFFLINE_IDLE_RETRY_SEC = 300  # co ile sekund sprawdzać net, gdy nie grzejemy
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
TEMP = 38.0
prognoza_wyslana = False
PROGNOZA = 0.0
LOG_GAP = {}


def is_wifi_up():
    try:
        wlan = network.WLAN(network.STA_IF)
        return wlan.isconnected()
    except:
        return False


def has_internet():
    """
    Test 'internetu' – szybkie żądanie do znanego endpointu, który zwraca 204/200.
    Jeśli Wi-Fi jest, ale DNS/routing nie działa, zwróci False.
    """
    try:
        # lekki endpoint do sprawdzania łączności:
        r = requests.get("http://connectivitycheck.gstatic.com/generate_204")
        ok = r.status_code in (200, 204)
        try:
            r.close()
        except:
            pass
        return ok
    except:
        return False


def try_recover_connectivity():
    """
    Zwraca True tylko, jeśli **działa internet** (HTTP 204/200).
    Ma krótkie, limitowane próby Wi-Fi, więc nie blokuje programu.
    """
    try:
        if not is_wifi_up():
            connect_wifi_fast(WIFI_SSID, WIFI_PASS)
        return has_internet()
    except:
        return False


def _is_session_expired(payload):
    # oczekiwany format błędu:
    # {"message":"USER_MUST_RELOGIN","success":False,"failCode":305,"immediately":True}
    try:
        return (
            isinstance(payload, dict)
            and payload.get("success") is False
            and int(payload.get("failCode", 0)) == 305
        )
    except Exception:
        return False


def connect_wifi(ssid, password, timeout=30, max_attempts=None):
    """
    Łączy z Wi-Fi. Jeśli max_attempts=None => próbuje bez końca (jak dotąd).
    Jeśli max_attempts to liczba => przerywa po tylu nieudanych próbach.
    """
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
        print(f"❌ Timeout ({timeout}s).")
        wlan.disconnect()
        attempt += 1
        if max_attempts is not None and attempt > max_attempts:
            print("⛔ Maks. liczba prób Wi-Fi osiągnięta.")
            return None
        time.sleep(5)


def connect_wifi_fast(ssid, password):
    """Szybka, nieblokująca próba: 1 podejście, timeout 10 s."""
    return connect_wifi(ssid, password, timeout=10, max_attempts=1)


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
# def aktualizuj_z_github():
#     try:
#         print("⬇️ Pobieranie najnowszego main.py z GitHub...")
#         response = requests.get(GITHUB_RAW_URL)
#         if response.status_code == 200:
#             with open("main.py", "w") as f:
#                 f.write(response.text)
#             print("✅ Zaktualizowano main.py – restartuję Pico...")
#             machine.reset()
#         else:
#             print("❌ Błąd pobierania pliku z GitHub:", response.status_code)
#     except Exception as e:
#         print("❌ Wyjątek podczas aktualizacji:", e)
def pobierz_prognoze_z_supabase():
    global PROGNOZA
    try:
        url = SUPABASE_URL + "/rest/v1/prognoza?select=value&id=eq.1"
        headers = {
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Authorization": f"Bearer {SUPABASE_PUBLISHABLE_KEY}",
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data and "value" in data[0]:
                PROGNOZA = data[0]["value"]
                print(f"📥 Prognoza z Supabase: {PROGNOZA:.2f} kWh")
        else:
            print("❌ Błąd pobierania prognozy z Supabase:", response.status_code)
        response.close()
    except Exception as e:
        print("❌ Wyjątek przy pobieraniu prognozy z Supabase:", e)


def pobierz_prognoze_i_zapisz():
    global prognoza_wyslana, PROGNOZA
    t = time.localtime()
    if t[3] == 6 and not prognoza_wyslana:
        try:
            print("🌤 Pobieram prognozę z Solcast...")
            headers = {"Authorization": secrets.SOLCAST_PWD}
            response = requests.get(secrets.SOLCAST_URL, headers=headers)

            if response.status_code == 200:
                dane = response.json()
                dzien_str = f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"

                suma = 0.0
                for entry in dane.get("forecasts", []):
                    if entry["period_end"].startswith(dzien_str):
                        suma += entry.get("pv_estimate", 0)

                suma = suma * 0.5

                print(f"🔆 Suma prognoz na dzisiaj: {suma:.2f} kWh")

                url = SUPABASE_URL + "/rest/v1/prognoza?id=eq.1"
                headers = {
                    "Content-Type": "application/json",
                    "apikey": SUPABASE_PUBLISHABLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_PUBLISHABLE_KEY}",
                }
                PROGNOZA = suma
                payload = json.dumps({"value": round(suma, 3)})
                res = requests.patch(url, headers=headers, data=payload)
                print("📬 Zapisano prognozę:", res.status_code, res.text)

                prognoza_wyslana = True  # ✅ ustaw flagę
            else:
                print("❌ Błąd pobierania prognozy:", response.status_code)
        except Exception as e:
            print("❌ Wyjątek przy pobieraniu prognozy:", e)

    elif t[3] != 6:
        prognoza_wyslana = False  # 🔁 zresetuj flagę po 6:59


def aktualizuj_z_github():
    try:
        print("⬇️ Pobieranie najnowszego main.py z GitHub...")
        response = requests.get(GITHUB_RAW_URL)
        if response.status_code == 200:
            with open("main.py", "w") as f:
                f.write(response.text)

            # ZMIANA TRYBU na zawsze38 (PATCH id=1)
            try:
                print("🔁 Aktualizacja zakończona – resetuję tryb na zawsze38")
                url = SUPABASE_URL + "/rest/v1/ustawienia?id=eq.1"
                headers = {
                    "apikey": SUPABASE_PUBLISHABLE_KEY,
                    "Authorization": f"Bearer {SUPABASE_PUBLISHABLE_KEY}",
                    "Content-Type": "application/json",
                }
                payload = json.dumps({"tryb": "zawsze38"})
                res = requests.patch(url, headers=headers, data=payload)
                print("📬 Supabase response:", res.status_code, res.text)
            except Exception as e:
                print("❌ Nie udało się zresetować trybu:", e)

            print("✅ Zaktualizowano main.py – restartuję Pico...")
            time.sleep(2)
            machine.reset()
        else:
            print("❌ Błąd pobierania pliku z GitHub:", response.status_code)
    except Exception as e:
        print("❌ Wyjątek podczas aktualizacji:", e)


# ZAPIS DANYCH LIVE DO SUPABASE
def zapisz_do_supabase(temp, grzanie, pv_power, tryb_dzialania, log_gap):
    # Mapa tekst → id
    TRYBY = {
        "standard_8": 1,
        "standard_6": 2,
        "silownia": 3,
        "zawsze38": 4,
        "opt": 6,
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
        "log_gap": log_gap,
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


def offline_maintain_38_chunks(ds, roms, relay_pin):
    """
    Tryb awaryjny bez internetu:
    - temp < TEMP  => grzej 5 min, potem sprawdź łączność (Wi-Fi + internet),
    - temp >= TEMP => nie grzej, odczekaj 5 min, potem sprawdź łączność,
    - jeśli internet wróci – natychmiast wyjdź (wracamy do trybu online).
    """
    while True:
        # 1) próba odzyskania łączności przed cyklem
        if try_recover_connectivity():
            print("🌐 Internet dostępny — wychodzę z trybu offline.")
            return

        # 2) odczyt temperatury (awaryjnie: przy błędzie traktujemy jak za zimno)
        try:
            temp = odczytaj_temperature(ds, roms)
        except Exception as e:
            print("❌ Offline: błąd odczytu DS18B20:", e)
            temp = TEMP - 10  # konserwatywnie: potraktuj jako zimno

        t = time.localtime()
        print(
            f"[{t[3]:02}:{t[4]:02}] (OFFLINE) Temp: {temp:.1f}°C | Próg: {TEMP:.1f}°C"
        )

        if temp < TEMP:
            # ❄️ za zimno — włącz grzałkę na 5 min
            print("🔥 (OFFLINE) Za zimno — grzeję 5 min.")
            relay_pin.value(1)
            time.sleep(OFFLINE_HEAT_CHUNK_SEC)
            relay_pin.value(0)

            # po bloku 5 min sprawdź łączność i ewentualnie wróć online
            if try_recover_connectivity():
                print("🌐 Internet wrócił po bloku grzania — wracam online.")
                return

            # jeśli wciąż offline — pętla wraca na początek: znów sprawdzimy temp itd.
        else:
            # 🌡️ wystarczająco ciepło — nie grzej, odczekaj 5 min i dopiero sprawdź łączność
            relay_pin.value(0)
            print(
                "🧊 (OFFLINE) Temp ≥ 38°C — nie grzeję. Odczekam 5 min przed próbą łączności."
            )
            time.sleep(OFFLINE_IDLE_RETRY_SEC)

            if try_recover_connectivity():
                print("🌐 Internet wrócił — wracam online.")
                return

            # jeśli dalej offline — pętla wraca i znów oceni temp


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


# opt v1
# def opt(temp, godzina, minuta, pv_power):
#     if temp < TEMP:
#         return True
#     if pv_power >= 2.0 and temp < 39.0:
#         return True
#     return False


# opt v2
# def opt(temp, godzina, minuta, pv_power):
#     global PROGNOZA

#     # Zakładana temperatura bazowa
#     temp_min = TEMP
#     temp_dogrzej = 39.0

#     if PROGNOZA < 5:
#         # Mała produkcja – utrzymuj minimalną temperaturę
#         return temp < temp_min

#     elif PROGNOZA < 10:
#         # Średnia produkcja – utrzymuj niższą temp, dogrzewaj przy PV >= 1.0
#         if temp < temp_min - 2:
#             return True
#         if pv_power >= 1.0 and temp < temp_dogrzej:
#             return True

#     elif PROGNOZA < 15:
#         # Większa produkcja – dogrzewaj przy PV >= 1.5
#         if temp < temp_min - 2:
#             return True
#         if pv_power >= 1.5 and temp < temp_dogrzej:
#             return True

#     else:
#         # Bardzo wysoka produkcja – dogrzewaj przy PV >= 2.0
#         if temp < temp_min - 2:
#             return True
#         if pv_power >= 2.0 and temp < temp_dogrzej:
#             return True

#     return False


# opt v3
def opt(temp, godzina, minuta, pv_power):
    global PROGNOZA

    night_hours = godzina >= 16 or godzina < 6  # 16:00–06:00
    low_threshold = TEMP

    if PROGNOZA < 5:
        return temp < TEMP

    elif 5 <= PROGNOZA < 10:
        if night_hours:
            return temp < low_threshold
        else:
            return pv_power >= 0.7 and temp < 39.0

    elif 10 <= PROGNOZA < 15:
        if night_hours:
            return temp < low_threshold
        else:
            return pv_power >= 1.5 and temp < 39.0

    elif PROGNOZA >= 15:
        if night_hours:
            return temp < low_threshold
        else:
            return pv_power >= 2.0 and temp < 39.0

    return False  # domyślnie nie grzej


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
    """Zwraca (moc_W, ewentualnie_nowy_token). Gdy sesja wygasła, próbuje zalogować i powtarza raz."""
    global LOG_GAP

    def _call(token):
        url_headers = {"Content-Type": "application/json", "xsrf-token": token}
        payload = {"devIds": DEVIDS, "devTypeId": DEVTYPEID}
        r = requests.post(DEVLIST_URL, json=payload, headers=url_headers)
        return r

    try:
        r = _call(xsrf_token)
        try:
            if r.status_code == 200:
                data = r.json()

                # 1) Sesja wygasła?
                if _is_session_expired(data):
                    print("🔒 Sesja FusionSolar wygasła (305) – loguję ponownie...")
                    new_token = login_and_get_token()
                    if not new_token:
                        print("❌ Ponowne logowanie nieudane.")
                        return 0.0, None

                    # 2) retry z nowym tokenem
                    r2 = _call(new_token)
                    try:
                        if r2.status_code == 200:
                            data2 = r2.json()
                            if _is_session_expired(data2):
                                print("❌ Ponownie: USER_MUST_RELOGIN – przerywam.")
                                return 0.0, None

                            LOG_GAP = data2
                            power = float(
                                data2["data"][0]["dataItemMap"].get("active_power", 0)
                            )
                            return power, new_token
                        else:
                            print("❌ DEVLIST retry HTTP:", r2.status_code)
                            return 0.0, None
                    finally:
                        try:
                            r2.close()
                        except:
                            pass

                # 3) Happy path
                LOG_GAP = data
                power = float(data["data"][0]["dataItemMap"].get("active_power", 0))
                return power, None

            else:
                print("❌ DEVLIST HTTP:", r.status_code)
                return 0.0, None
        finally:
            try:
                r.close()
            except:
                pass

    except Exception as e:
        print("❌ get_active_power błąd:", e)

    return 0.0, None


# --- Temperatura DS18B20 ---
def init_temp_sensor():
    ds_pin = machine.Pin(0)
    ow = onewire.OneWire(ds_pin)
    ds = ds18x20.DS18X20(ow)
    roms = ds.scan()
    if not roms:
        print("⚠️ Nie znaleziono DS18B20!")
    return ds, roms


def odczytaj_temperature(ds, roms):
    if not roms:
        raise RuntimeError("Brak czujnika DS18B20")
    ds.convert_temp()
    time.sleep_ms(750)
    for rom in roms:
        t = ds.read_temp(rom)
        if t is not None:
            return t
    raise RuntimeError("DS18B20 zwrócił None")


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
pobierz_prognoze_z_supabase()
relay_pin = machine.Pin(16, machine.Pin.OUT)
relay_pin.value(0)

while True:
    # brak **internetu** ⇒ tryb offline
    if not has_internet():  # (ostrzejsze niż samo is_wifi_up)
        print("📵 Brak internetu — tryb offline 5-min blokami.")
        offline_maintain_38_chunks(ds, roms, relay_pin)
        # tu wracamy już z działającym internetem
    sprawdz_i_polacz_wifi()
    pobierz_prognoze_i_zapisz()
    pobierz_tryb_dzialania()

    # jeśli brak tokenu (lub poprzednio nieudane odświeżenie) – spróbuj zalogować
    if not xsrf_token:
        xsrf_token = login_and_get_token()
        if not xsrf_token:
            print("❌ Brak tokenu – śpię 60s i próbuję ponownie.")
            time.sleep(60)
            continue

    # odczyt PV z auto-relogiem
    pv_power, maybe_new_token = get_active_power(xsrf_token)
    if maybe_new_token:
        xsrf_token = maybe_new_token  # zaktualizuj token po relogu

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
        # aktualizuj_z_github() robi reset – więc dalszy kod i tak się nie wykona
        continue
    elif TRYB_DZIALANIA == "opt":
        grzanie_on = opt(temp, hour, minute, pv_power)
    else:
        print("⚠️ Nieznany tryb! Domyślnie 'zawsze38'")
        grzanie_on = sterowanie_zawsze38(temp, hour, minute, pv_power)

    print(
        f"🔎 Sprawdzenie: godzina={hour}, PV={pv_power}, temp={temp}, TRYB={TRYB_DZIALANIA}"
    )
    relay_pin.value(1 if grzanie_on else 0)
    zapisz_do_supabase(temp, grzanie_on, pv_power, TRYB_DZIALANIA, LOG_GAP)

    print(
        f"[{hour:02}:{minute:02}] Temp: {temp:.1f}°C | Grzanie: {'ON' if grzanie_on else 'OFF'} | PV: {pv_power}W | Tryb: {TRYB_DZIALANIA}"
    )
    time.sleep(300)

# 🏠 Room Scanner - Lublin

**Automatyczny agent monitorujący oferty pokoi do wynajęcia w Lublinie**

[![Monitoring Status](https://github.com/YOUR_USERNAME/room-scanner-lublin/actions/workflows/monitor.yml/badge.svg)](https://github.com/YOUR_USERNAME/room-scanner-lublin/actions/workflows/monitor.yml)
[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-Live%20Map-blue)](https://YOUR_USERNAME.github.io/room-scanner-lublin/)

## 🎯 Funkcje

- 🔍 **Automatyczne skanowanie** - codziennie o 10:00 i 18:00
- 📍 **Precyzyjne geokodowanie** - wyciąga adresy z treści ogłoszeń  
- 🗺️ **Interaktywna mapa** - z kolorami według cen
- 📚 **Historia ofert** - nieaktywne pokazane jako przekreślone domy
- 🚀 **GitHub Actions** - w pełni automatyczne uruchamianie
- 💾 **Baza danych** - SQLite z pełną historią

## 🗺️ Mapa na żywo

**👉 [Zobacz mapę pokoi w Lublinie](https://YOUR_USERNAME.github.io/room-scanner-lublin/)**

Mapa jest automatycznie aktualizowana dwa razy dziennie i zawiera:
- 🟢 **Zielone markery** - pokoje < 600 zł
- 🔵 **Niebieskie markery** - pokoje 600-799 zł  
- 🟠 **Pomarańczowe markery** - pokoje 800-999 zł
- 🔴 **Czerwone markery** - pokoje 1000-1199 zł
- 🟤 **Brązowe markery** - pokoje 1200+ zł
- ❌ **Szare przekreślone** - oferty nieaktywne (historia)

## 🏃‍♂️ Jak uruchomić

### 1. Fork tego repozytorium

Kliknij przycisk "Fork" w prawym górnym rogu

### 2. Włącz GitHub Actions

1. Idź do zakładki **Actions** w swoim forku
2. Kliknij **"I understand my workflows, go ahead and enable them"**

### 3. Włącz GitHub Pages

1. Idź do **Settings** → **Pages**
2. Wybierz **Source: GitHub Actions**
3. Zapisz

### 4. Uruchom pierwszy monitoring

1. Idź do **Actions** → **OLX Lublin Room Monitor**
2. Kliknij **Run workflow** → **Run workflow**
3. Poczekaj na zakończenie (około 5-15 minut)

### 5. Zobacz wyniki

Twoja mapa będzie dostępna pod adresem:
`https://YOUR_USERNAME.github.io/room-scanner-lublin/`

## ⏰ Harmonogram

Agent automatycznie uruchamia się:
- **10:00 UTC** (11:00/12:00 w Polsce) - poranny monitoring
- **18:00 UTC** (19:00/20:00 w Polsce) - wieczorny monitoring

## 📊 Co monitoruje

Agent skanuje [stancje-pokoje w Lublinie na OLX](https://www.olx.pl/nieruchomosci/stancje-pokoje/lublin/) i:

1. **Pobiera wszystkie ogłoszenia** ze stron listingowych
2. **Otwiera każde ogłoszenie** i czyta pełną treść
3. **Szuka adresów** w formacie "ul. Nazwa + numer"
4. **Geokoduje precyzyjnie** używając OpenStreetMap
5. **Nanosi na mapę** z kolorami według cen
6. **Prowadzi historię** - nieaktywne oferty pozostają widoczne

## 🗂️ Struktura projektu

```
room-scanner-lublin/
├── olx_room_monitor.py          # Główny agent
├── .github/workflows/monitor.yml # GitHub Actions
├── requirements.txt             # Zależności Python
├── data/                        # Dane (baza, cache)
│   ├── olx_rooms.db            # SQLite baza danych
│   └── geocoding_cache.json    # Cache geokodowania
├── docs/                        # GitHub Pages
│   └── index.html              # Mapa (generowana automatycznie)
└── logs/                        # Logi (opcjonalne)
```

## 🔧 Konfiguracja

### Zmiana harmonogramu

Edytuj `.github/workflows/monitor.yml`:

```yaml
on:
  schedule:
    - cron: '0 8 * * *'   # 8:00 UTC zamiast 10:00
    - cron: '0 20 * * *'  # 20:00 UTC zamiast 18:00
```

### Zmiana granic cenowych

Edytuj `olx_room_monitor.py`, funkcja `_generate_map()`:

```python
if offer.price_numeric < 600:        # Było 700
    color, icon = 'green', 'home'
elif offer.price_numeric < 900:     # Było 1000  
    color, icon = 'blue', 'home'
```

## 📈 Statystyki

W każdym uruchomieniu GitHub Actions pokazuje:
- 📊 Liczbę znalezionych ofert
- 📍 Ile ma precyzyjne adresy
- 🆕 Ile jest nowych
- 🔄 Ile zaktualizowanych
- 🏠 Aktywne vs nieaktywne

## 🐛 Rozwiązywanie problemów

### Agent się nie uruchamia
- Sprawdź czy włączyłeś GitHub Actions w Settings
- Upewnij się że fork ma aktualny kod

### Brak mapy
- Sprawdź czy włączyłeś GitHub Pages
- Poczekaj kilka minut po pierwszym uruchomieniu

### Mała liczba ofert
- Agent filtruje tylko oferty z konkretnymi adresami "ul. Nazwa + numer"
- To normalne - nie wszystkie ogłoszenia zawierają pełne adresy

## 🤝 Contribution

Chcesz ulepszyć agenta? 

1. Fork → zmień kod → Pull Request
2. Zgłoś issues z pomysłami
3. ⭐ Star jeśli project Ci się podoba!

## 📝 Licencja

MIT License - używaj dowolnie!

---

## 🎯 Przykładowe wyniki

Po uruchomieniu agent znajduje oferty takie jak:
- `ul. Narutowicza 14` - 690 zł - 🟢
- `ul. Głęboka 18` - 1300 zł - 🔴  
- `ul. Paganiniego 12` - 640 zł - 🟢
- `ul. Romanowskiego 58` - 640 zł - 🟢

Wszystkie naniesione na mapę z precyzyjnymi współrzędnymi GPS! 🗺️

---

**⚡ Automatyzacja + precyzja + historia = idealne narzędzie do monitoringu rynku wynajmu!**

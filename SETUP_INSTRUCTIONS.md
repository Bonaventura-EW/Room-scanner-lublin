# 🚀 Instrukcja wdrożenia Room Scanner - Lublin na GitHub

## 📋 Kompletna instrukcja krok po kroku

### 1. 📁 Przygotowanie repozytorium

1. **Utwórz nowe repozytorium na GitHub:**
   - Nazwa: `room-scanner-lublin` (lub dowolna)
   - Publiczne (wymagane dla GitHub Pages)
   - **NIE** inicjalizuj z README

2. **Sklonuj i przygotuj pliki:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/room-scanner-lublin.git
   cd room-scanner-lublin
   
   # Skopiuj wszystkie pliki z outputs do katalogu repozytorium
   # Struktura powinna wyglądać tak:
   # .
   # ├── .github/workflows/monitor.yml
   # ├── .gitignore
   # ├── README.md
   # ├── requirements.txt
   # ├── olx_room_monitor.py
   # ├── test_local.py
   # └── data/.gitkeep
   ```

### 2. 🏗️ Wdrożenie na GitHub

```bash
git add .
git commit -m "Add Room Scanner - Lublin"
git push origin main
```

### 3. ⚡ Konfiguracja GitHub Actions

1. **Włącz Actions:**
   - Idź do zakładki **Actions** w repozytorium
   - Kliknij **"I understand my workflows, go ahead and enable them"**

2. **Pierwsze uruchomienie:**
   - Kliknij **"Room Scanner - Lublin"** workflow
   - Kliknij **"Run workflow"** → **"Run workflow"**
   - Poczekaj na zakończenie (5-15 minut)

### 4. 🌐 Konfiguracja GitHub Pages

1. **Włącz Pages:**
   - Idź do **Settings** → **Pages**
   - **Source:** wybierz **"GitHub Actions"**
   - Kliknij **Save**

2. **Sprawdź adres:**
   - Po pierwszym udanym workflow mapa będzie dostępna pod:
   - `https://YOUR_USERNAME.github.io/room-scanner-lublin/`

### 5. ✅ Weryfikacja

Po pierwszym uruchomieniu sprawdź:

1. **GitHub Actions:**
   - ✅ Workflow zakończył się sukcesem
   - 📊 Summary pokazuje statystyki

2. **GitHub Pages:**
   - 🌐 Mapa ładuje się pod adresem Pages
   - 🗺️ Widoczne markery z ofertami

3. **Logi:**
   - Sprawdź logi w Actions czy agent znajduje oferty
   - Jeśli 0 ofert z adresami - to normalne (nie wszystkie mają adresy)

### 6. 🎯 Harmonogram automatyczny

Agent będzie się uruchamiać automatycznie:
- **10:00 UTC** (11:00/12:00 w Polsce)
- **18:00 UTC** (19:00/20:00 w Polsce)

### 7. 🔧 Opcjonalne dostosowania

#### Zmiana harmonogramu
Edytuj `.github/workflows/monitor.yml`:
```yaml
on:
  schedule:
    - cron: '0 8 * * *'   # 8:00 UTC 
    - cron: '0 16 * * *'  # 16:00 UTC
```

#### Zmiana kolorów cenowych
Edytuj `olx_room_monitor.py`, metoda `_generate_map()`:
```python
if offer.price_numeric < 600:        # Było 700
    color, icon = 'green', 'home'
elif offer.price_numeric < 800:     # Było 1000
    color, icon = 'blue', 'home'
```

## 🎉 Gotowe!

Po wdrożeniu otrzymasz:

- 🤖 **Automatycznego agenta** działającego 2x dziennie
- 🗺️ **Interaktywną mapę** z ofertami pokoi
- 📚 **Historię wszystkich ofert** 
- 📊 **Statystyki** w GitHub Actions
- 🔄 **Automatyczne aktualizacje** bez Twojej interwencji

### 📞 Wsparcie

Jeśli coś nie działa:

1. Sprawdź logi w GitHub Actions
2. Upewnij się że Actions i Pages są włączone
3. Poczekaj - pierwszy setup może potrwać 15-20 minut

### 🚀 Zaawansowane opcje

- **Powiadomienia:** Dodaj webhook'i do Discord/Slack
- **Filtrowanie:** Rozszerz kryteria wyszukiwania  
- **Analiza:** Dodaj wykresy trendów cenowych
- **Eksport:** CSV z danymi do analizy

---

**🏠 Miłego monitorowania rynku wynajmu w Lublinie!**

Agent automatycznie znajdzie wszystkie pokoje z precyzyjnymi adresami i naniesie je na mapę z historią. Bez Twojego udziału, codziennie o stałych godzinach!

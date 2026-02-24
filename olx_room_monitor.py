#!/usr/bin/env python3
"""
🏠 Room Scanner - Lublin
Automatyczny monitor ofert pokoi na OLX
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import os
import sqlite3
from datetime import datetime
import folium
import time
from typing import Optional, List, Dict, Tuple
import logging

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RoomOffer:
    """Reprezentacja oferty pokoju"""
    def __init__(self, offer_id: str, title: str, price: str, url: str, 
                 address: Optional[str] = None, lat: Optional[float] = None, 
                 lon: Optional[float] = None):
        self.offer_id = offer_id
        self.title = title
        self.price = price
        self.price_numeric = self._extract_price_numeric(price)
        self.url = url
        self.address = address
        self.latitude = lat
        self.longitude = lon
        self.is_active = True
        self.last_seen = datetime.now().isoformat()
    
    def _extract_price_numeric(self, price_str: str) -> float:
        """Wyciąga liczbę z stringa ceny"""
        try:
            # Szukaj liczb
            numbers = re.findall(r'\d+', price_str.replace(',', '.'))
            if numbers:
                return float(numbers[0])
        except:
            pass
        return 0

class RoomScanner:
    """Agent skanujący oferty pokoi"""
    
    def __init__(self, db_path: str = 'data/olx_rooms.db'):
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'pl-PL,pl;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
        self.offers = []
        self.geocoding_cache = self._load_geocoding_cache()
        self._init_database()
    
    def _load_geocoding_cache(self) -> Dict:
        """Wczytaj cache geokodowania"""
        cache_file = 'data/geocoding_cache.json'
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_geocoding_cache(self):
        """Zapisz cache geokodowania"""
        os.makedirs('data', exist_ok=True)
        with open('data/geocoding_cache.json', 'w', encoding='utf-8') as f:
            json.dump(self.geocoding_cache, f, ensure_ascii=False, indent=2)
    
    def _init_database(self):
        """Inicjalizuj bazę danych"""
        os.makedirs('data', exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Tabela ofert
        c.execute('''CREATE TABLE IF NOT EXISTS offers (
            offer_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            price TEXT,
            price_numeric REAL,
            url TEXT UNIQUE,
            address TEXT,
            latitude REAL,
            longitude REAL,
            is_active INTEGER DEFAULT 1,
            first_seen TEXT,
            last_seen TEXT,
            description TEXT
        )''')
        
        # Tabela historii
        c.execute('''CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id TEXT,
            event TEXT,
            timestamp TEXT,
            details TEXT,
            FOREIGN KEY(offer_id) REFERENCES offers(offer_id)
        )''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Baza danych zainicjalizowana")
    
    def _extract_address(self, text: str) -> Optional[str]:
        """
        Wyciąga adres z tekstu
        Obsługuje formaty:
        - ul. Nazwa 123
        - ul. Nazwa 123a
        - ul. Nazwa 123/45
        - ul. Nazwa 123a/45
        """
        if not text:
            return None
        
        patterns = [
            # ul./UL. + nazwa + numer + opcjonalnie litera + opcjonalnie mieszkanie
            r'[Uu]l\.?\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s\-]+?)\s+(\d+)([a-zA-Z]?)(?:\s*[\/\-]\s*(\d+))?',
            # ulica + nazwa + numer
            r'[Uu]lica\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s\-]+?)\s+(\d+)([a-zA-Z]?)(?:\s*[\/\-]\s*(\d+))?',
            # pl. + nazwa
            r'[Pp]l\.?\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s\-]+?)\s+(\d+)([a-zA-Z]?)(?:\s*[\/\-]\s*(\d+))?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                street = match.group(1).strip()
                number = match.group(2)
                letter = match.group(3) if match.group(3) else ""
                apartment = f"/{match.group(4)}" if len(match.groups()) > 3 and match.group(4) else ""
                
                full_number = number + letter + apartment
                address = f"ul. {street.title()} {full_number}, Lublin"
                return address
        
        return None
    
    def _geocode_address(self, address: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Geokoduj adres - używa Nominatim (OpenStreetMap)
        z cache'em aby nie bombardować API
        """
        if not address:
            return None, None
        
        # Sprawdź cache
        if address in self.geocoding_cache:
            cached = self.geocoding_cache[address]
            return cached.get('lat'), cached.get('lon')
        
        try:
            # Zapytanie do Nominatim
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': address,
                'format': 'json',
                'limit': 1
            }
            
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            
            results = response.json()
            if results:
                lat = float(results[0]['lat'])
                lon = float(results[0]['lon'])
                
                # Zapisz do cache
                self.geocoding_cache[address] = {'lat': lat, 'lon': lon}
                self._save_geocoding_cache()
                
                logger.info(f"📍 Geokodowano: {address} -> ({lat}, {lon})")
                return lat, lon
        
        except Exception as e:
            logger.warning(f"⚠️ Błąd geokodowania {address}: {e}")
        
        # Domyślne koordynaty Lublina jeśli się nie uda
        return None, None
    
    def scan_olx(self, url: str = "https://www.olx.pl/nieruchomosci/stancje-pokoje/lublin/"):
        """Skanuj OLX"""
        logger.info(f"🔍 Skanowanie: {url}")
        
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Błąd pobierania strony: {e}")
            return
        
        if response.status_code != 200:
            logger.error(f"❌ Błąd HTTP: {response.status_code}")
            return
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Szukaj linków do ofert - nowe selektory dla OLX
        offer_elements = soup.find_all('a', href=re.compile(r'/d/oferta/|/oferta/'))
        logger.info(f"🔗 Znalezionych ofert: {len(offer_elements)}")
        
        if not offer_elements:
            logger.warning("⚠️ Brak ofert - możliwy problem z selektorem OLX")
            return
        
        # Przetwórz oferty
        for i, element in enumerate(offer_elements[:50], 1):  # Limit 50 ofert na stronę
            try:
                href = element.get('href')
                if not href:
                    continue
                
                # Pełny URL
                full_url = href if href.startswith('http') else f"https://www.olx.pl{href}"
                
                # Wyciągnij ID oferty z URL
                offer_id_match = re.search(r'/oferta/(\d+)', full_url)
                if not offer_id_match:
                    continue
                
                offer_id = offer_id_match.group(1)
                title = element.get_text(strip=True)
                
                # Przeszukaj treść oferty
                self._process_offer(offer_id, title, full_url)
                
                # Rate limiting
                if i % 10 == 0:
                    time.sleep(2)
            
            except Exception as e:
                logger.error(f"❌ Błąd przetwarzania oferty {i}: {e}")
                continue
        
        logger.info(f"✅ Znaleziono {len(self.offers)} ofert z adresami")
    
    def _process_offer(self, offer_id: str, title: str, url: str):
        """Pobierz i przetwórz szczegóły oferty"""
        try:
            # Sprawdź czy już istnieje w DB
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('SELECT offer_id FROM offers WHERE offer_id = ?', (offer_id,))
            
            if c.fetchone():
                logger.debug(f"⏩ Oferta {offer_id} już w bazie")
                conn.close()
                return
            
            conn.close()
            
            # Pobierz szczegóły
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Szukaj ceny i opisu - nowe selektory
            price = "Nie podana"
            description = ""
            
            # Cena
            price_elem = soup.find('div', {'data-testid': 'ad-price'}) or \
                        soup.find('strong', string=re.compile(r'zł|PLN'))
            if price_elem:
                price = price_elem.get_text(strip=True)
            
            # Opis
            desc_selectors = [
                {'data-cy': 'ad_description'},
                {'class': re.compile('description|ad-description')},
            ]
            
            for selector in desc_selectors:
                desc_elem = soup.find('div', selector)
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                    break
            
            # Szukaj adresu w tytule i opisie
            full_text = f"{title} {description}"
            address = self._extract_address(full_text)
            
            if not address:
                logger.debug(f"❌ Brak adresu w {offer_id}")
                return
            
            # Geokoduj
            lat, lon = self._geocode_address(address)
            
            if lat is None or lon is None:
                logger.warning(f"⚠️ Nie można geokodować: {address}")
                lat, lon = 51.2465, 22.5684  # Domyślne koordynaty Lublina
            
            # Zapisz do bazy
            offer = RoomOffer(offer_id, title, price, url, address, lat, lon)
            self.offers.append(offer)
            self._save_offer(offer, description)
            
            logger.info(f"✅ {address} - {price}")
        
        except Exception as e:
            logger.error(f"❌ Błąd pobierania {url}: {e}")
    
    def _save_offer(self, offer: RoomOffer, description: str = ""):
        """Zapisz ofertę do bazy"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        now = datetime.now().isoformat()
        
        c.execute('''INSERT OR REPLACE INTO offers 
                    (offer_id, title, price, price_numeric, url, address, 
                     latitude, longitude, is_active, first_seen, last_seen, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (offer.offer_id, offer.title, offer.price, offer.price_numeric,
                   offer.url, offer.address, offer.latitude, offer.longitude,
                   1, now, now, description))
        
        # Historia
        c.execute('''INSERT INTO history (offer_id, event, timestamp)
                    VALUES (?, 'found', ?)''', (offer.offer_id, now))
        
        conn.commit()
        conn.close()
    
    def generate_map(self):
        """Generuj interaktywną mapę"""
        logger.info("🗺️ Generowanie mapy...")
        
        # Załaduj wszystkie oferty z DB
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('SELECT * FROM offers WHERE latitude IS NOT NULL ORDER BY price_numeric')
        rows = c.fetchall()
        conn.close()
        
        # Centrum mapy
        map_center = [51.2465, 22.5684]
        m = folium.Map(location=map_center, zoom_start=13)
        
        # Definicje kolorów
        def get_color(price: float) -> Tuple[str, str]:
            if price < 600:
                return 'green', '🏠'
            elif price < 800:
                return 'blue', '🏠'
            elif price < 1000:
                return 'orange', '🏠'
            elif price < 1200:
                return 'red', '🏠'
            else:
                return 'darkred', '🏠'
        
        # Dodaj markery
        for row in rows:
            offer_id, title, price, price_numeric, url, address, lat, lon, is_active, first_seen, last_seen, description = row
            
            if not lat or not lon:
                continue
            
            color, icon = get_color(price_numeric)
            
            # HTML popup
            popup_html = f'''
            <div style="width: 250px; font-family: Arial; font-size: 12px;">
                <h4 style="margin: 0 0 10px 0;">{address}</h4>
                <p><b>Cena:</b> {price}</p>
                <p><b>Tytuł:</b> {title[:50]}...</p>
                <a href="{url}" target="_blank" style="color: #007bff; text-decoration: none;">
                    Otwórz ogłoszenie →
                </a>
            </div>
            '''
            
            folium.Marker(
                [lat, lon],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"{address} - {price}",
                icon=folium.Icon(color=color, icon='home', prefix='fa')
            ).add_to(m)
        
        # Info panel
        stats_html = f'''
        <div style="position: fixed; bottom: 50px; right: 10px; width: 280px; 
                    background: white; padding: 15px; border-radius: 8px; 
                    box-shadow: 0 4px 8px rgba(0,0,0,0.15); z-index: 999; 
                    font-family: Arial; font-size: 13px;">
            <h3 style="margin-top: 0;">🏠 Room Scanner</h3>
            <hr style="margin: 5px 0;">
            <p><b>Pokoje:</b> {len(rows)}</p>
            <p><b>Aktualizacja:</b> {datetime.now().strftime('%H:%M')}</p>
            <p style="font-size: 11px; color: #666; margin-bottom: 0;">
                Automatyczne skanowanie 2x dziennie
            </p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(stats_html))
        
        # Legenda
        legend_html = '''
        <div style="position: fixed; top: 10px; right: 10px; width: 180px; 
                    background: white; padding: 12px; border-radius: 8px; 
                    box-shadow: 0 4px 8px rgba(0,0,0,0.15); z-index: 999; 
                    font-family: Arial; font-size: 12px;">
            <h4 style="margin-top: 0; margin-bottom: 10px;">Ceny (PLN)</h4>
            <p style="margin: 5px 0;"><span style="color: green;">●</span> &lt; 600 zł</p>
            <p style="margin: 5px 0;"><span style="color: blue;">●</span> 600-800 zł</p>
            <p style="margin: 5px 0;"><span style="color: orange;">●</span> 800-1000 zł</p>
            <p style="margin: 5px 0;"><span style="color: red;">●</span> 1000-1200 zł</p>
            <p style="margin: 5px 0;"><span style="color: darkred;">●</span> 1200+ zł</p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
        
        # Zapisz
        os.makedirs('docs', exist_ok=True)
        m.save('docs/index.html')
        logger.info(f"✅ Mapa zapisana: docs/index.html")
    
    def print_stats(self):
        """Wypisz statystyki"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('SELECT COUNT(*) FROM offers WHERE is_active = 1')
        active = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM offers WHERE is_active = 0')
        inactive = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM offers')
        total = c.fetchone()[0]
        
        conn.close()
        
        logger.info("=" * 60)
        logger.info("📊 STATYSTYKI")
        logger.info("=" * 60)
        logger.info(f"🔗 Razem ofert: {total}")
        logger.info(f"✅ Aktywne: {active}")
        logger.info(f"❌ Nieaktywne: {inactive}")
        logger.info("=" * 60)

def main():
    """Główna funkcja"""
    logger.info("🚀 Uruchamianie Room Scanner - Lublin")
    logger.info(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    scanner = RoomScanner()
    scanner.scan_olx()
    scanner.generate_map()
    scanner.print_stats()
    
    logger.info("✅ Monitoring zakończony")

if __name__ == "__main__":
    main()

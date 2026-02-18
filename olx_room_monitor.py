#!/usr/bin/env python3
"""
Room Scanner - Lublin - POPRAWIONA WERSJA
- Przeszukuje treść ogłoszeń (nie tylko tytuł)
- Obsługuje "Al." (aleje) + liter w numerach (73a)
- Skanuje WSZYSTKIE strony (nie zatrzymuje na pustych)
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import sqlite3
import os
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Set
import logging
import time
import folium
from folium import plugins
import hashlib

# Konfiguracja
LUBLIN_BOUNDS = {'min_lat': 51.15, 'max_lat': 51.35, 'min_lon': 22.35, 'max_lon': 22.75}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class RoomOffer:
    """Oferta pokoju z pełnymi danymi"""
    offer_id: str
    title: str
    price: str
    price_numeric: int
    url: str
    description: str
    street_name: str
    building_number: str
    apartment_number: Optional[str]
    full_address: str
    latitude: float
    longitude: float
    first_seen: str
    last_seen: str
    is_active: bool
    hash: str
    days_active: int = 0

class DatabaseManager:
    """Zarządza bazą danych SQLite z historią ofert"""
    
    def __init__(self, db_path: str = "data/olx_rooms.db"):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else "data", exist_ok=True)
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Inicjalizacja tabel"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS offers (
                    offer_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    price TEXT NOT NULL,
                    price_numeric INTEGER,
                    url TEXT NOT NULL,
                    description TEXT,
                    street_name TEXT,
                    building_number TEXT,
                    apartment_number TEXT,
                    full_address TEXT,
                    latitude REAL,
                    longitude REAL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    hash TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS monitoring_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    total_found INTEGER,
                    with_addresses INTEGER,
                    new_offers INTEGER,
                    updated_offers INTEGER,
                    active_offers INTEGER,
                    inactive_offers INTEGER
                )
            """)
            
            conn.commit()
            logger.info("📊 Baza danych zainicjalizowana")
    
    def save_offer(self, offer: RoomOffer) -> str:
        """Zapisuje/aktualizuje ofertę. Zwraca 'new'/'updated'/'unchanged'"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT hash, is_active, first_seen FROM offers WHERE offer_id = ?", (offer.offer_id,))
            result = cursor.fetchone()
            
            if result:
                old_hash, is_active, first_seen = result
                offer.first_seen = first_seen  # Zachowaj pierwotną datę
                
                if old_hash != offer.hash or not is_active:
                    cursor.execute("""
                        UPDATE offers SET title=?, price=?, price_numeric=?, description=?,
                        last_seen=?, is_active=1, hash=? WHERE offer_id=?
                    """, (offer.title, offer.price, offer.price_numeric, offer.description,
                         offer.last_seen, offer.hash, offer.offer_id))
                    return 'updated'
                else:
                    cursor.execute("UPDATE offers SET last_seen=? WHERE offer_id=?", 
                                 (offer.last_seen, offer.offer_id))
                    return 'unchanged'
            else:
                cursor.execute("""
                    INSERT INTO offers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (offer.offer_id, offer.title, offer.price, offer.price_numeric, 
                     offer.url, offer.description, offer.street_name, offer.building_number,
                     offer.apartment_number, offer.full_address, offer.latitude, offer.longitude,
                     offer.first_seen, offer.last_seen, 1, offer.hash))
                return 'new'
    
    def mark_inactive_offers(self, active_ids: Set[str], timestamp: str):
        """Oznacza oferty jako nieaktywne"""
        with sqlite3.connect(self.db_path) as conn:
            if active_ids:
                placeholders = ','.join('?' * len(active_ids))
                conn.execute(f"""
                    UPDATE offers SET is_active=0, last_seen=?
                    WHERE offer_id NOT IN ({placeholders}) AND is_active=1
                """, [timestamp] + list(active_ids))
            else:
                conn.execute("UPDATE offers SET is_active=0, last_seen=? WHERE is_active=1", 
                           (timestamp,))
    
    def get_all_offers(self) -> List[RoomOffer]:
        """Pobiera wszystkie oferty z historią"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM offers WHERE latitude IS NOT NULL")
            
            offers = []
            for row in cursor.fetchall():
                first_seen = datetime.fromisoformat(row['first_seen'])
                last_seen = datetime.fromisoformat(row['last_seen'])
                days_active = (last_seen - first_seen).days
                
                offer = RoomOffer(
                    offer_id=row['offer_id'],
                    title=row['title'],
                    price=row['price'],
                    price_numeric=row['price_numeric'] or 0,
                    url=row['url'],
                    description=row['description'] or '',
                    street_name=row['street_name'],
                    building_number=row['building_number'],
                    apartment_number=row['apartment_number'],
                    full_address=row['full_address'],
                    latitude=row['latitude'],
                    longitude=row['longitude'],
                    first_seen=row['first_seen'],
                    last_seen=row['last_seen'],
                    is_active=bool(row['is_active']),
                    hash=row['hash'],
                    days_active=days_active
                )
                offers.append(offer)
            
            return offers
    
    def save_stats(self, stats: Dict):
        """Zapisuje statystyki monitoringu"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO monitoring_stats 
                (timestamp, total_found, with_addresses, new_offers, updated_offers, active_offers, inactive_offers)
                VALUES (?,?,?,?,?,?,?)
            """, (datetime.now().isoformat(), stats['total_found'], stats['with_addresses'],
                 stats['new_offers'], stats['updated_offers'], stats['active_offers'], stats['inactive_offers']))

class ImprovedGeocoder:
    """Geocoder z cache'owaniem"""
    
    def __init__(self, cache_file: str = "data/geocoding_cache.json"):
        self.nominatim_url = "https://nominatim.openstreetmap.org/search"
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Room-Scanner-Lublin/2.0 (Educational)'
        })
    
    def _load_cache(self) -> Dict:
        """Ładuje cache geokodowania"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def _save_cache(self):
        """Zapisuje cache geokodowania"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
    
    def geocode(self, street: str, number: str) -> Optional[Tuple[float, float]]:
        """Geokoduje adres z cache'owaniem"""
        cache_key = f"{street.lower()}_{number}_lublin"
        
        if cache_key in self.cache:
            return tuple(self.cache[cache_key])
        
        queries = [
            f"{street} {number}, Lublin, Polska",
            f"ul. {street} {number}, Lublin, Poland", 
            f"ulica {street} {number}, Lublin, Polska",
            f"al. {street} {number}, Lublin, Poland",  # Dodane aleje
            f"aleja {street} {number}, Lublin, Polska",
            f"{street}, Lublin, Polska"  # Fallback - tylko ulica
        ]
        
        for query in queries:
            try:
                params = {
                    'q': query,
                    'format': 'json',
                    'limit': 3,
                    'countrycodes': 'pl',
                    'bounded': 1,
                    'viewbox': f"{LUBLIN_BOUNDS['min_lon']},{LUBLIN_BOUNDS['min_lat']},{LUBLIN_BOUNDS['max_lon']},{LUBLIN_BOUNDS['max_lat']}"
                }
                
                response = self.session.get(self.nominatim_url, params=params, timeout=10)
                response.raise_for_status()
                
                results = response.json()
                if results:
                    for result in results:
                        lat, lon = float(result['lat']), float(result['lon'])
                        
                        # Sprawdź czy w granicach Lublina
                        if (LUBLIN_BOUNDS['min_lat'] <= lat <= LUBLIN_BOUNDS['max_lat'] and
                            LUBLIN_BOUNDS['min_lon'] <= lon <= LUBLIN_BOUNDS['max_lon']):
                            
                            self.cache[cache_key] = [lat, lon]
                            self._save_cache()
                            logger.info(f"✅ Geokodowano: {street} {number} -> ({lat:.6f}, {lon:.6f})")
                            time.sleep(1.2)
                            return (lat, lon)
                
            except Exception as e:
                logger.warning(f"⚠️ Błąd geokodowania '{query}': {e}")
            
            time.sleep(1.2)
        
        logger.error(f"❌ Nie można geokodować: {street} {number}")
        return None

class ImprovedOLXMonitor:
    """Poprawiony agent monitorujący OLX"""
    
    def __init__(self):
        self.base_url = "https://www.olx.pl"
        self.search_url = "https://www.olx.pl/nieruchomosci/stancje-pokoje/lublin/"
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        self.db = DatabaseManager()
        self.geocoder = ImprovedGeocoder()
        
        # POPRAWIONE wzorce adresów - obsługują Al. i litery w numerach
        self.address_patterns = [
            # "Al. Nazwa 123a" lub "Al. Nazwa 123/45" (ALEJE z literami!)
            r'[Aa]l\.?\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s]+?)\s+(\d+)([a-zA-Z]?)(?:[\/\-\s]*(\d+))?',
            # "ul. Nazwa 123a" lub "ul. Nazwa 123/45"  
            r'[Uu]l\.?\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s]+?)\s+(\d+)([a-zA-Z]?)(?:[\/\-\s]*(\d+))?',
            # "ulica Nazwa 123a"
            r'[Uu]lica\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s]+?)\s+(\d+)([a-zA-Z]?)(?:[\/\-\s]*(\d+))?',
            # "Nazwa 123a" na końcu (bez ul./al.)
            r'([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s]{3,25}?)\s+(\d+)([a-zA-Z]?)(?:[\/\-\s]*(\d+))?(?=\s*[,\.\s]*(?:lublin|$))',
        ]
    
    def run_monitoring(self) -> Dict:
        """Główny cykl monitorowania"""
        timestamp = datetime.now().isoformat()
        logger.info(f"🚀 Rozpoczynam monitoring OLX Lublin - {timestamp}")
        
        try:
            # Zbierz WSZYSTKIE oferty ze WSZYSTKICH stron
            all_offers = self._collect_ALL_offers()
            logger.info(f"📄 Znaleziono {len(all_offers)} ofert na wszystkich stronach")
            
            # Przetworz oferty z adresami
            processed_offers = []
            stats = {'new_offers': 0, 'updated_offers': 0, 'unchanged_offers': 0}
            active_ids = set()
            
            for i, basic_offer in enumerate(all_offers, 1):
                if i % 20 == 0:
                    logger.info(f"   📊 Przetworzono {i}/{len(all_offers)} ofert...")
                
                # PRZESZUKAJ TREŚĆ I TYTUŁ
                full_offer = self._process_offer_CONTENT(basic_offer, timestamp)
                if full_offer:
                    processed_offers.append(full_offer)
                    active_ids.add(full_offer.offer_id)
                    
                    # Zapisz do bazy
                    result = self.db.save_offer(full_offer)
                    stats[f'{result}_offers'] += 1
                    
                    if result == 'new':
                        logger.info(f"🆕 Nowa: {full_offer.full_address} - {full_offer.price}")
                    elif result == 'updated':
                        logger.info(f"🔄 Zaktualizowana: {full_offer.full_address}")
                
                time.sleep(0.8)  # Opóźnienie między requestami
            
            # Oznacz nieaktywne
            self.db.mark_inactive_offers(active_ids, timestamp)
            
            # Pobierz statystyki
            all_offers_in_db = self.db.get_all_offers()
            active_count = sum(1 for o in all_offers_in_db if o.is_active)
            inactive_count = len(all_offers_in_db) - active_count
            
            # ZAWSZE wygeneruj mapę (nawet jeśli brak ofert)
            self._generate_map_ALWAYS(all_offers_in_db)
            
            # Zapisz statystyki
            final_stats = {
                'total_found': len(all_offers),
                'with_addresses': len(processed_offers),
                'new_offers': stats['new_offers'],
                'updated_offers': stats['updated_offers'],
                'active_offers': active_count,
                'inactive_offers': inactive_count
            }
            self.db.save_stats(final_stats)
            
            logger.info("✅ Monitoring zakończony pomyślnie")
            logger.info(f"   📊 Ofert ze stron: {len(all_offers)}")
            logger.info(f"   📍 Z adresami: {len(processed_offers)}")
            logger.info(f"   🆕 Nowych: {stats['new_offers']}")
            logger.info(f"   🔄 Zaktualizowanych: {stats['updated_offers']}")
            logger.info(f"   🏠 Aktywnych: {active_count}")
            logger.info(f"   ❌ Nieaktywnych: {inactive_count}")
            
            return final_stats
            
        except Exception as e:
            logger.error(f"❌ Błąd monitorowania: {e}")
            return {'status': 'ERROR', 'error': str(e)}
    
    def _collect_ALL_offers(self) -> List[Dict]:
        """Zbiera WSZYSTKIE oferty ze WSZYSTKICH stron - nie zatrzymuje na pustych"""
        all_offers = []
        page = 1
        max_pages = 20  # Bezpiecznik - maksymalnie 20 stron
        
        while page <= max_pages:
            try:
                url = f"{self.search_url}?page={page}"
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                offer_links = soup.find_all('a', href=re.compile(r'/d/oferta/'))
                
                if not offer_links:
                    logger.info(f"📄 Strona {page}: pusta - KONIEC")
                    break  # Pierwsza pusta strona = koniec
                
                page_offers = []
                for link in offer_links:
                    href = link.get('href')
                    if href and '/d/oferta/' in href:
                        full_url = href if href.startswith('http') else f"{self.base_url}{href}"
                        
                        # Wyciągnij ID z URL
                        offer_id_match = re.search(r'ID([A-Za-z0-9]+)', href)
                        if offer_id_match:
                            offer_id = offer_id_match.group(1)
                            title = link.get_text(strip=True)
                            
                            page_offers.append({
                                'offer_id': offer_id,
                                'url': full_url,
                                'title': title
                            })
                
                # Usuń duplikaty na stronie
                unique_page_offers = {o['offer_id']: o for o in page_offers}.values()
                logger.info(f"📄 Strona {page}: {len(unique_page_offers)} unikalnych ofert")
                all_offers.extend(unique_page_offers)
                
                page += 1
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"❌ Błąd strony {page}: {e}")
                break
        
        # Usuń duplikaty globalne
        unique_offers = {o['offer_id']: o for o in all_offers}
        return list(unique_offers.values())
    
    def _process_offer_CONTENT(self, basic_offer: Dict, timestamp: str) -> Optional[RoomOffer]:
        """Przetwarza ofertę - PRZESZUKUJE TREŚĆ + TYTUŁ"""
        
        try:
            response = self.session.get(basic_offer['url'], timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Wyciągnij szczegóły
            title = self._extract_title(soup) or basic_offer['title']
            price, price_numeric = self._extract_price(soup)
            description = self._extract_description(soup)
            
            # PRZESZUKAJ TYTUŁ + TREŚĆ razem
            full_text = f"{title} {description}" if description else title
            
            # Znajdź adres w pełnym tekście
            address_info = self._extract_address_IMPROVED(full_text)
            if not address_info:
                return None
            
            # Geokoduj
            coords = self.geocoder.geocode(
                address_info['street_name'], 
                address_info['building_number']
            )
            
            if not coords:
                return None
            
            lat, lon = coords
            
            # Hash dla wykrywania zmian
            content_hash = hashlib.md5(
                f"{title}{price}{description}".encode('utf-8')
            ).hexdigest()
            
            return RoomOffer(
                offer_id=basic_offer['offer_id'],
                title=title,
                price=price,
                price_numeric=price_numeric,
                url=basic_offer['url'],
                description=description[:2000] if description else '',
                street_name=address_info['street_name'],
                building_number=address_info['building_number'],
                apartment_number=address_info.get('apartment_number'),
                full_address=address_info['full_address'],
                latitude=lat,
                longitude=lon,
                first_seen=timestamp,
                last_seen=timestamp,
                is_active=True,
                hash=content_hash
            )
            
        except Exception as e:
            logger.warning(f"⚠️ Błąd przetwarzania {basic_offer['url']}: {e}")
            return None
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Wyciąga tytuł oferty"""
        selectors = ['h1[data-cy="ad_title"]', 'h1', '[data-testid="ad-title"]']
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)
        return None
    
    def _extract_price(self, soup: BeautifulSoup) -> Tuple[str, int]:
        """Wyciąga cenę oferty"""
        selectors = ['[data-testid="ad-price-container"]', '[data-cy="ad-price"]', '.price-label']
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                price_text = elem.get_text(strip=True)
                price_match = re.search(r'(\d+(?:\s\d+)*)', price_text)
                if price_match:
                    price_numeric = int(price_match.group(1).replace(' ', ''))
                    return price_text, price_numeric
        
        return "Brak ceny", 0
    
    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Wyciąga opis oferty"""
        selectors = ['[data-cy="ad_description"]', '.css-g5mtl5', '[data-testid="description"]']
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text(strip=True)
        return None
    
    def _extract_address_IMPROVED(self, text: str) -> Optional[Dict]:
        """POPRAWIONE wyciąganie adresu - obsługuje Al. i litery"""
        
        for pattern in self.address_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                street_name = match.group(1).strip()
                building_number = match.group(2)
                letter_suffix = match.group(3) if match.lastindex >= 3 and match.group(3) else ""
                apartment_number = match.group(4) if match.lastindex >= 4 and match.group(4) else None
                
                # Połącz numer z literą (np. "73" + "a" = "73a")
                full_building_number = building_number + letter_suffix
                
                # Filtruj nieprawidłowe nazwy
                if (len(street_name) < 3 or 
                    street_name.lower() in ['pokój', 'pokoj', 'wynajm', 'mieszkanie', 'oferta'] or
                    any(char.isdigit() for char in street_name[:3])):
                    continue
                
                # Sprawdź numer
                try:
                    base_num = int(building_number)  # Sprawdź tylko cyfrową część
                    if not (1 <= base_num <= 999):
                        continue
                except ValueError:
                    continue
                
                street_normalized = street_name.title()
                
                result = {
                    "street_name": street_normalized,
                    "building_number": full_building_number,  # Z literą!
                    "apartment_number": apartment_number,
                    "full_address": f"ul. {street_normalized} {full_building_number}"
                }
                
                if apartment_number:
                    result["full_address"] += f"/{apartment_number}"
                result["full_address"] += ", Lublin"
                
                return result
        
        return None
    
    def _generate_map_ALWAYS(self, offers: List[RoomOffer]):
        """ZAWSZE generuje mapę - nawet gdy brak ofert (demo)"""
        
        # Stwórz folder docs
        os.makedirs('docs', exist_ok=True)
        
        if not offers:
            # Brak ofert - stwórz demo mapę
            logger.info("📍 Brak ofert z adresami - tworzę demo mapę")
            self._create_demo_map()
            return
        
        # Są oferty - stwórz normalną mapę
        logger.info(f"🗺️ Tworzę mapę z {len(offers)} ofertami")
        
        # Centrum mapy
        active_offers = [o for o in offers if o.is_active]
        if active_offers:
            center_lat = sum(o.latitude for o in active_offers) / len(active_offers)
            center_lon = sum(o.longitude for o in active_offers) / len(active_offers)
        else:
            center_lat, center_lon = 51.2465, 22.5684
        
        m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
        
        # Warstwy markerów
        active_group = folium.FeatureGroup(name="🏠 Aktywne oferty")
        inactive_group = folium.FeatureGroup(name="❌ Nieaktywne (historia)")
        
        for offer in offers:
            # Kolor według ceny i statusu
            if offer.is_active:
                if offer.price_numeric < 600:
                    color, icon = 'green', 'home'
                elif offer.price_numeric < 800:
                    color, icon = 'blue', 'home'
                elif offer.price_numeric < 1000:
                    color, icon = 'orange', 'home'
                elif offer.price_numeric < 1200:
                    color, icon = 'red', 'home'
                else:
                    color, icon = 'darkred', 'home'
                prefix = 'fa'
                group = active_group
                status = "🏠 AKTYWNA"
            else:
                color, icon, prefix = 'gray', 'remove', 'glyphicon'
                group = inactive_group  
                status = "❌ NIEAKTYWNA"
            
            # Popup
            popup_html = f"""
            <div style="width: 320px; font-family: Arial, sans-serif;">
                <h4 style="margin-bottom: 10px; color: #333;">
                    {offer.title[:80]}{'...' if len(offer.title) > 80 else ''}
                </h4>
                
                <div style="background: {'#e8f5e8' if offer.is_active else '#f5f5f5'}; 
                            padding: 8px; border-radius: 4px; margin: 8px 0;">
                    <strong>{status}</strong>
                </div>
                
                <p><strong>💰 {offer.price}</strong></p>
                <p>📍 {offer.full_address}</p>
                <p>📅 Pierwsza: {offer.first_seen[:10]}</p>
                <p>📅 Ostatnia: {offer.last_seen[:10]}</p>
                <p>⏱️ Aktywność: {offer.days_active} dni</p>
                
                <div style="margin-top: 12px;">
                    <a href="{offer.url}" target="_blank" 
                       style="background: #007bff; color: white; padding: 6px 12px; 
                              text-decoration: none; border-radius: 3px; font-size: 12px;">
                        Zobacz ofertę
                    </a>
                </div>
            </div>
            """
            
            folium.Marker(
                [offer.latitude, offer.longitude],
                popup=folium.Popup(popup_html, max_width=350),
                tooltip=f"{offer.full_address} - {offer.price} ({'aktywna' if offer.is_active else 'nieaktywna'})",
                icon=folium.Icon(color=color, icon=icon, prefix=prefix)
            ).add_to(group)
        
        # Dodaj grupy do mapy
        active_group.add_to(m)
        inactive_group.add_to(m)
        folium.LayerControl().add_to(m)
        
        # Dodaj legendę i statystyki
        self._add_map_overlay(m, offers)
        
        # Zapisz mapę
        map_path = 'docs/index.html'
        m.save(map_path)
        logger.info(f"🗺️ Mapa zapisana: {map_path}")
    
    def _create_demo_map(self):
        """Tworzy demo mapę gdy brak prawdziwych ofert"""
        
        m = folium.Map(location=[51.2465, 22.5684], zoom_start=14)
        
        # Demo marker
        folium.Marker(
            [51.2465, 22.5684],
            popup=folium.Popup("""
            <div style="width: 300px; font-family: Arial; text-align: center;">
                <h4>🎯 Room Scanner - Lublin</h4>
                <p><strong>Mapa jest gotowa!</strong></p>
                <p>Agent przeszukuje OLX i szuka ofert z precyzyjnymi adresami.</p>
                <p>📍 Gdy znajdzie oferty typu "ul. Narutowicza 14" - pojawią się tutaj automatycznie.</p>
                <p>🔄 Monitoring: codziennie o 10:00 i 18:00</p>
            </div>
            """),
            tooltip="Room Scanner - gotowy do działania!",
            icon=folium.Icon(color='blue', icon='info-sign', prefix='glyphicon')
        ).add_to(m)
        
        # Info
        info_html = '''
        <div style="position: fixed; top: 10px; right: 10px; width: 250px; 
                    background: white; padding: 15px; border-radius: 8px; 
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1); z-index: 1000; 
                    font-family: Arial, sans-serif;">
            <h4 style="margin: 0 0 12px 0; color: #333;">📊 Room Scanner - Lublin</h4>
            <div style="background: #d4edda; padding: 8px; border-radius: 4px; margin: 8px 0; border: 1px solid #c3e6cb;">
                <strong>🎯 GOTOWY DO DZIAŁANIA</strong><br>
                <small>Agent przeszukuje OLX i czeka na oferty z adresami</small>
            </div>
            <p style="margin: 5px 0;">🔍 Szuka: "ul. Nazwa + numer"</p>
            <p style="margin: 5px 0;">⏰ Monitoring: 10:00 i 18:00</p>
            <p style="margin: 5px 0; font-size: 11px; color: #666;">
                📅 Sprawdzono: ''' + datetime.now().strftime('%d.%m %H:%M') + '''
            </p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(info_html))
        
        # Zapisz demo mapę
        map_path = 'docs/index.html'
        m.save(map_path)
        logger.info(f"🗺️ Demo mapa zapisana: {map_path}")
    
    def _add_map_overlay(self, m, offers):
        """Dodaje legendę i statystyki do mapy"""
        
        active_count = sum(1 for o in offers if o.is_active)
        inactive_count = len(offers) - active_count
        
        if active_count > 0:
            active_prices = [o.price_numeric for o in offers if o.is_active and o.price_numeric > 0]
            avg_price = sum(active_prices) // len(active_prices) if active_prices else 0
        else:
            avg_price = 0
        
        # Statystyki
        stats_html = f'''
        <div style="position: fixed; top: 10px; right: 10px; width: 220px; 
                    background: white; padding: 15px; border-radius: 8px; 
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1); z-index: 1000; 
                    font-family: Arial, sans-serif;">
            <h4 style="margin: 0 0 12px 0; color: #333;">📊 Room Scanner - Lublin</h4>
            <p style="margin: 5px 0;">🏠 Aktywne: <strong>{active_count}</strong></p>
            <p style="margin: 5px 0;">❌ Nieaktywne: <strong>{inactive_count}</strong></p>
            <p style="margin: 5px 0;">💰 Średnia cena: <strong>{avg_price} zł</strong></p>
            <p style="margin: 5px 0; font-size: 11px; color: #666;">
                📅 Aktualizacja: {datetime.now().strftime('%d.%m %H:%M')}
            </p>
            <hr style="margin: 8px 0;">
            <p style="margin: 0; font-size: 10px; color: #999;">
                🔄 Monitoring: 10:00 i 18:00<br>
                🎯 Treść + tytuł ofert
            </p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(stats_html))
        
        # Legenda
        legend_html = '''
        <div style="position: fixed; bottom: 20px; left: 20px; width: 200px; 
                    background: white; padding: 15px; border-radius: 8px; 
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1); z-index: 1000; 
                    font-family: Arial, sans-serif; font-size: 13px;">
            <h4 style="margin: 0 0 12px 0; color: #333; font-size: 14px;">🏷️ Ceny (precyzyjne adresy)</h4>
            <div style="display: flex; align-items: center; margin: 6px 0;">
                <div style="width: 16px; height: 16px; background: #28a745; border-radius: 50%; margin-right: 8px;"></div>
                <span>< 600 zł</span>
            </div>
            <div style="display: flex; align-items: center; margin: 6px 0;">
                <div style="width: 16px; height: 16px; background: #007bff; border-radius: 50%; margin-right: 8px;"></div>
                <span>600-799 zł</span>
            </div>
            <div style="display: flex; align-items: center; margin: 6px 0;">
                <div style="width: 16px; height: 16px; background: #fd7e14; border-radius: 50%; margin-right: 8px;"></div>
                <span>800-999 zł</span>
            </div>
            <div style="display: flex; align-items: center; margin: 6px 0;">
                <div style="width: 16px; height: 16px; background: #dc3545; border-radius: 50%; margin-right: 8px;"></div>
                <span>1000-1199 zł</span>
            </div>
            <div style="display: flex; align-items: center; margin: 6px 0;">
                <div style="width: 16px; height: 16px; background: #6f4423; border-radius: 50%; margin-right: 8px;"></div>
                <span>1200+ zł</span>
            </div>
            <div style="display: flex; align-items: center; margin: 6px 0;">
                <div style="width: 16px; height: 16px; background: #6c757d; margin-right: 8px;">
                    <span style="color: white; font-size: 10px; display: flex; align-items: center; justify-content: center; height: 100%;">✕</span>
                </div>
                <span>Nieaktywne</span>
            </div>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

def main():
    """Funkcja główna - poprawiona wersja"""
    print("🏠 Room Scanner - Lublin (POPRAWIONA WERSJA)")
    print("🔍 Przeszukuje treść + tytuł / Obsługuje Al. + litery / WSZYSTKIE strony")
    print("=" * 70)
    
    monitor = ImprovedOLXMonitor()
    stats = monitor.run_monitoring()
    
    print(f"\n📊 Wyniki poprawionej wersji:")
    for key, value in stats.items():
        if key != 'status':
            print(f"   {key}: {value}")

if __name__ == "__main__":
    main()

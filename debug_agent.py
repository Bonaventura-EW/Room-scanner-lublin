#!/usr/bin/env python3
"""
Room Scanner - DEBUG VERSION
Intensywne logowanie żeby zobaczyć gdzie jest problem
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import os
from datetime import datetime
import folium
import time

def debug_olx_scan():
    """Debug scan pierwszych 3 ofert z dokładnym logowaniem"""
    
    print("🔍 DEBUG SCAN - pierwsze 3 oferty z OLX")
    print("=" * 60)
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # Wzorce - poprawione
    patterns = [
        r'[Aa]l\.?\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s]+?)\s+(\d+)([a-zA-Z]?)(?:[\/\-\s]*(\d+))?',
        r'[Uu]l\.?\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s]+?)\s+(\d+)([a-zA-Z]?)(?:[\/\-\s]*(\d+))?',
        r'[Uu]lica\s+([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż\s]+?)\s+(\d+)([a-zA-Z]?)(?:[\/\-\s]*(\d+))?',
    ]
    
    try:
        # Test podstawowy URL
        url = "https://www.olx.pl/nieruchomosci/stancje-pokoje/lublin/"
        print(f"🌐 Testuję URL: {url}")
        
        response = session.get(url, timeout=20)
        print(f"📡 Status kod: {response.status_code}")
        print(f"📄 Długość odpowiedzi: {len(response.text)} znaków")
        
        if response.status_code != 200:
            print(f"❌ BŁĄD: OLX zwrócił kod {response.status_code}")
            return
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Znajdź linki do ofert
        offer_links = soup.find_all('a', href=re.compile(r'/d/oferta/'))
        print(f"🔗 Znalezionych linków do ofert: {len(offer_links)}")
        
        if not offer_links:
            print("❌ BRAK LINKÓW - OLX może blokować lub zmienił strukturę")
            # Sprawdź czy strona zawiera jakiekolwiek linki
            all_links = soup.find_all('a')
            print(f"🔗 Wszystkich linków na stronie: {len(all_links)}")
            
            # Pokaż pierwsze 5 linków dla diagnostyki
            print("🔍 Pierwsze 5 linków:")
            for i, link in enumerate(all_links[:5]):
                href = link.get('href', 'BRAK')
                text = link.get_text(strip=True)[:50]
                print(f"   {i+1}: {href} -> {text}")
            
            return
        
        # Test pierwszych 3 ofert
        found_addresses = []
        
        for i, link in enumerate(offer_links[:3], 1):
            href = link.get('href')
            if not href or '/d/oferta/' not in href:
                continue
            
            full_url = href if href.startswith('http') else f"https://www.olx.pl{href}"
            title = link.get_text(strip=True)
            
            print(f"\n📄 === OFERTA {i} ===")
            print(f"📝 Tytuł: {title}")
            print(f"🔗 URL: {full_url}")
            
            # Test czy tytuł już zawiera adres
            print(f"🔍 Szukam adresu w tytule...")
            for j, pattern in enumerate(patterns, 1):
                matches = list(re.finditer(pattern, title, re.IGNORECASE))
                if matches:
                    print(f"   ✅ Wzorzec {j} znalazł w tytule: {matches[0].groups()}")
                    found_addresses.append(title)
                    continue
            
            try:
                # Pobierz treść oferty
                print(f"📥 Pobieram treść oferty...")
                response = session.get(full_url, timeout=15)
                print(f"   Status: {response.status_code}, Długość: {len(response.text)}")
                
                if response.status_code != 200:
                    print(f"   ❌ Błąd pobierania: {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Znajdź opis
                desc_selectors = [
                    '[data-cy="ad_description"]',
                    '.css-g5mtl5', 
                    '[data-testid="description"]',
                    '.offer-description'
                ]
                
                description = None
                for selector in desc_selectors:
                    elem = soup.select_one(selector)
                    if elem:
                        description = elem.get_text(strip=True)
                        print(f"   📄 Opis znaleziony ({selector}): {len(description)} znaków")
                        break
                
                if not description:
                    print(f"   ⚠️ Brak opisu - sprawdzam możliwe selektory")
                    # Debug - pokaż dostępne klasy/id
                    divs = soup.find_all('div', string=re.compile(r'.{50,}'))[:3]
                    print(f"   🔍 Znalezionych długich tekstów: {len(divs)}")
                    for div in divs:
                        classes = div.get('class', [])
                        id_attr = div.get('id', '')
                        text_preview = div.get_text(strip=True)[:100]
                        print(f"      - class={classes}, id={id_attr}, text={text_preview}...")
                
                # Przeszukaj pełny tekst
                full_text = f"{title} {description or ''}"
                print(f"🔍 Przeszukuję pełny tekst ({len(full_text)} znaków)...")
                print(f"   Podgląd: {full_text[:150]}...")
                
                found = False
                for j, pattern in enumerate(patterns, 1):
                    matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
                    if matches:
                        for match in matches:
                            street = match.group(1).strip()
                            number = match.group(2)
                            letter = match.group(3) if match.lastindex >= 3 and match.group(3) else ""
                            
                            full_number = number + letter
                            address = f"ul. {street.title()} {full_number}, Lublin"
                            
                            print(f"   ✅ ZNALEZIONO (wzorzec {j}): {address}")
                            found_addresses.append(address)
                            found = True
                            break
                    
                    if found:
                        break
                
                if not found:
                    print(f"   ❌ Brak precyzyjnego adresu")
                
            except Exception as e:
                print(f"   ❌ Błąd przetwarzania: {e}")
            
            print(f"   ⏱️ Czekam 3 sekundy...")
            time.sleep(3)
        
        print(f"\n📊 === PODSUMOWANIE DEBUG ===")
        print(f"🔗 Linków do ofert: {len(offer_links)}")
        print(f"📍 Znalezionych adresów: {len(found_addresses)}")
        
        if found_addresses:
            print(f"✅ SUKCES - znalezione adresy:")
            for addr in found_addresses:
                print(f"   📍 {addr}")
        else:
            print(f"❌ PROBLEM - żadnych adresów nie znaleziono")
            print(f"   Możliwe przyczyny:")
            print(f"   - OLX blokuje GitHub Actions")
            print(f"   - Zmienili strukturę HTML")
            print(f"   - Wzorce adresów nie pasują")
            print(f"   - Brak ofert z precyzyjnymi adresami")
        
        # Stwórz mapę debug
        create_debug_map(found_addresses)
        
    except Exception as e:
        print(f"❌ KRYTYCZNY BŁĄD: {e}")

def create_debug_map(addresses):
    """Tworzy debug mapę"""
    
    os.makedirs('docs', exist_ok=True)
    
    m = folium.Map(location=[51.2465, 22.5684], zoom_start=14)
    
    if addresses:
        # Dodaj markery
        for i, addr in enumerate(addresses):
            lat = 51.2465 + i * 0.01
            lon = 22.5684 + i * 0.01
            
            folium.Marker(
                [lat, lon],
                popup=f"<b>DEBUG:</b><br>{addr}",
                tooltip=addr,
                icon=folium.Icon(color='green', icon='info-sign', prefix='glyphicon')
            ).add_to(m)
    
    # Info panel
    info_html = f'''
    <div style="position: fixed; top: 10px; right: 10px; width: 250px; 
                background: white; padding: 15px; border-radius: 8px; 
                box-shadow: 0 4px 8px rgba(0,0,0,0.1); z-index: 1000;">
        <h4>🐛 DEBUG MODE</h4>
        <p>Znalezionych adresów: <strong>{len(addresses)}</strong></p>
        <p>Test: {datetime.now().strftime('%H:%M:%S')}</p>
        {f"<p>✅ Wzorce działają!</p>" if addresses else "<p>❌ Brak adresów</p>"}
    </div>
    '''
    m.get_root().html.add_child(folium.Element(info_html))
    
    m.save('docs/index.html')
    print(f"🗺️ Debug mapa zapisana: docs/index.html")

if __name__ == "__main__":
    debug_olx_scan()

#!/usr/bin/env python3
"""
Debug script to download and analyze Chaturbate HTML structure
This helps understand why the scraper isn't finding streams
"""

import requests
import sys

def download_and_analyze():
    url = "https://chaturbate.com/"
    
    print("🔍 Downloading Chaturbate homepage...")
    print(f"URL: {url}")
    print("-" * 60)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"✓ Status Code: {response.status_code}")
        print(f"✓ Content Length: {len(response.text)} chars")
        
        if response.status_code != 200:
            print(f"❌ Error: HTTP {response.status_code}")
            return False
        
        html = response.text
        
        # Save to file
        filename = "chaturbate_debug.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✓ Saved HTML to: {filename}")
        
        # Analyze structure
        print("\n📊 HTML Analysis:")
        print("-" * 60)
        
        # Check for common selectors
        selectors_to_check = [
            'room_list_room',
            'data-room',
            'room_title',
            'thumbnail',
            'cams',
            'username',
            'roomlist',
            'list',
        ]
        
        for selector in selectors_to_check:
            count = html.count(selector)
            if count > 0:
                print(f"  ✓ '{selector}' found {count} times")
            else:
                print(f"  ✗ '{selector}' not found")
        
        # Try with BeautifulSoup if available
        try:
            from bs4 import BeautifulSoup
            print("\n🔍 BeautifulSoup Analysis:")
            print("-" * 60)
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try different selectors
            room_list_rooms = soup.find_all('li', class_='room_list_room')
            print(f"  li.room_list_room: {len(room_list_rooms)} found")
            
            data_rooms = soup.find_all(attrs={'data-room': True})
            print(f"  [data-room]: {len(data_rooms)} found")
            
            if data_rooms:
                print(f"\n  First room sample:")
                first_room = data_rooms[0]
                print(f"    Username: {first_room.get('data-room')}")
                
                # Find link
                link = first_room.find('a')
                if link:
                    print(f"    Link: {link.get('href')}")
                
                # Find image
                img = first_room.find('img')
                if img:
                    print(f"    Image: {img.get('src', 'N/A')[:80]}")
            
            # Check for ul.list
            ul_lists = soup.find_all('ul', class_='list')
            print(f"  ul.list: {len(ul_lists)} found")
            
            if ul_lists:
                first_list = ul_lists[0]
                lis = first_list.find_all('li')
                print(f"    - First ul.list has {len(lis)} <li> elements")
                
                if lis:
                    first_li = lis[0]
                    print(f"    - First <li> classes: {first_li.get('class')}")
                    print(f"    - First <li> has data-room: {first_li.get('data-room')}")
            
        except ImportError:
            print("\n⚠️  BeautifulSoup not installed, skipping detailed analysis")
            print("   Install with: pip install beautifulsoup4")
        
        print("\n" + "=" * 60)
        print("✅ Analysis complete!")
        print("=" * 60)
        print(f"\nOpen '{filename}' in a text editor to examine the HTML structure")
        print("Look for room/model elements and their class names/attributes")
        
        return True
        
    except requests.RequestException as e:
        print(f"❌ Network Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = download_and_analyze()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        sys.exit(1)

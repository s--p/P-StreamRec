import requests
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from ..logger import logger


def get_chaturbate_streams(
    page: int = 1,
    limit: int = 90,
    gender: Optional[str] = None,
    region: Optional[str] = None,
    tag: Optional[str] = None
) -> Dict:
    """
    Fetch live Chaturbate streams using web scraping
    
    Args:
        page: Page number (starting from 1)
        limit: Number of results per page (max 90)
        gender: Filter by gender (f=female, m=male, c=couple, t=trans)
        region: Filter by region (north_america, south_america, europe, asia, other)
        tag: Filter by tag
    
    Returns:
        Dict with streams list and metadata
    """
    logger.subsection("Chaturbate Discovery Scraper")
    
    try:
        # Build URL based on filters
        base_url = "https://chaturbate.com"
        
        # Gender mapping
        if gender:
            gender_map = {
                'f': '/female-cams/',
                'm': '/male-cams/',
                'c': '/couple-cams/',
                't': '/trans-cams/'
            }
            url = base_url + gender_map.get(gender, '/')
        elif tag:
            url = f"{base_url}/tag/{tag}/"
        else:
            url = base_url + "/"
        
        # Add page parameter if not page 1
        if page > 1:
            url += f"?page={page}"
        
        logger.progress("Fetching page", url=url, page=page)
        
        # Enhanced headers to bypass 403 Forbidden
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }
        
        # Add cookies from environment if available
        import os
        cookies = {}
        if os.getenv("CB_COOKIE"):
            cookies_str = os.getenv("CB_COOKIE")
            # Parse cookie string
            for cookie in cookies_str.split(';'):
                if '=' in cookie:
                    key, value = cookie.strip().split('=', 1)
                    cookies[key] = value
        
        # Use session for better cookie handling
        session = requests.Session()
        session.headers.update(headers)
        
        response = session.get(url, cookies=cookies, timeout=15, allow_redirects=True)
        
        if response.status_code != 200:
            logger.error("HTTP error", status_code=response.status_code)
            
            error_msg = f"HTTP {response.status_code}"
            if response.status_code == 403:
                error_msg = "Chaturbate blocked the request (403 Forbidden). You need to add a CB_COOKIE environment variable. See DISCOVERY_403_FIX.md for instructions."
            elif response.status_code == 429:
                error_msg = "Too many requests (429). Please wait a few minutes."
            
            return {
                "streams": [],
                "count": 0,
                "page": page,
                "total_pages": 0,
                "error": error_msg
            }
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all room cards - try multiple selectors
        room_cards = soup.find_all('li', class_='room_list_room')
        
        if not room_cards:
            logger.warning("No 'li.room_list_room' found, trying alternative selectors")
            room_cards = soup.find_all('div', class_='room_list_room')
        
        if not room_cards:
            logger.warning("No 'div.room_list_room' found, trying data-room selector")
            room_cards = soup.find_all('li', attrs={'data-room': True})
        
        if not room_cards:
            logger.warning("No data-room found, trying any li in room list")
            room_list = soup.find('ul', class_='list')
            if room_list:
                room_cards = room_list.find_all('li')
        
        logger.debug("Room cards found", count=len(room_cards))
        
        # Debug: save HTML snippet to help troubleshoot
        if len(room_cards) == 0:
            logger.error("No rooms found at all, dumping HTML structure")
            # Find main content areas
            content_divs = soup.find_all('div', class_=re.compile(r'room|content|list'))
            logger.debug("Found content divs", count=len(content_divs), 
                        classes=[div.get('class') for div in content_divs[:5]])
        
        streams = []
        
        for card in room_cards[:limit]:
            try:
                # Extract username - try multiple methods
                username = None
                
                # Method 1: data-room attribute
                username = card.get('data-room')
                
                # Method 2: room_title link
                if not username:
                    username_elem = card.find('a', class_='room_title')
                    if username_elem:
                        username = username_elem.get('href', '').strip('/').split('/')[-1]
                
                # Method 3: any link in the card
                if not username:
                    any_link = card.find('a', href=True)
                    if any_link:
                        href = any_link.get('href', '')
                        if href and '/' in href:
                            username = href.strip('/').split('/')[-1]
                
                if not username or username in ['', 'tag', 'female-cams', 'male-cams', 'couple-cams', 'trans-cams']:
                    continue
                
                # Extract thumbnail
                img_elem = card.find('img')
                thumbnail = img_elem.get('src', '') if img_elem else ''
                if thumbnail.startswith('//'):
                    thumbnail = 'https:' + thumbnail
                
                # Extract viewers
                viewers = 0
                viewers_elem = card.find('li', class_='cams')
                if viewers_elem:
                    viewers_text = viewers_elem.get_text(strip=True)
                    viewers_match = re.search(r'(\d+)', viewers_text)
                    if viewers_match:
                        viewers = int(viewers_match.group(1))
                
                # Extract gender
                gender_elem = card.find('div', class_='gender')
                extracted_gender = ''
                if gender_elem:
                    gender_class = gender_elem.get('class', [])
                    for cls in gender_class:
                        if 'gender' in cls and cls != 'gender':
                            extracted_gender = cls.replace('gender', '')
                
                # Extract room subject
                subject_elem = card.find('li', class_='subject')
                room_subject = subject_elem.get_text(strip=True) if subject_elem else ''
                
                # Extract age
                age_elem = card.find('span', class_='age')
                age = None
                if age_elem:
                    age_text = age_elem.get_text(strip=True)
                    age_match = re.search(r'(\d+)', age_text)
                    if age_match:
                        age = int(age_match.group(1))
                
                # Extract location
                location_elem = card.find('li', class_='location')
                location = location_elem.get_text(strip=True) if location_elem else ''
                
                # Check HD
                is_hd = card.find('li', class_='hd') is not None
                
                # Check NEW
                is_new = card.find('li', class_='new_') is not None
                
                stream = {
                    "username": username,
                    "displayName": username,
                    "age": age,
                    "gender": extracted_gender or gender or '',
                    "location": location,
                    "viewers": viewers,
                    "thumbnail": thumbnail,
                    "thumbnailUrl": thumbnail,
                    "isHd": is_hd,
                    "isNew": is_new,
                    "roomSubject": room_subject,
                    "tags": [],
                    "chatUrl": f"https://chaturbate.com/{username}/",
                    "iframeEmbedUrl": f"https://chaturbate.com/{username}/embed/",
                    "seconds_online": 0
                }
                streams.append(stream)
                
            except Exception as e:
                logger.warning("Error parsing room card", error=str(e))
                continue
        
        # Estimate total pages (Chaturbate typically shows 90 rooms per page)
        total_count = len(streams) + (page - 1) * limit
        if len(streams) == limit:
            total_count += limit  # There's likely more
        
        total_pages = max(1, (total_count + limit - 1) // limit)
        
        logger.success("Streams scraped", 
                      count=len(streams),
                      page=page)
        
        return {
            "streams": streams,
            "count": len(streams),
            "total": total_count,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_more": len(streams) >= limit
        }
        
    except requests.RequestException as e:
        logger.error("Network error", error=str(e), exc_info=True)
        return {
            "streams": [],
            "count": 0,
            "page": page,
            "total_pages": 0,
            "error": str(e)
        }
    except Exception as e:
        logger.error("Unexpected error", error=str(e), exc_info=True)
        return {
            "streams": [],
            "count": 0,
            "page": page,
            "total_pages": 0,
            "error": str(e)
        }


def get_popular_tags() -> List[str]:
    """Get list of popular Chaturbate tags"""
    return [
        "18", "anal", "asian", "bbw", "bdsm", "bigass", "bigboobs", "bigcock",
        "blonde", "blowjob", "brunette", "couples", "cum", "cumshow", "curvy",
        "daddy", "deepthroat", "dirty", "ebony", "feet", "fetish", "french",
        "fuck", "german", "hairy", "joi", "latina", "lesbian", "lovense",
        "mature", "milf", "mistress", "muscle", "natural", "new", "office",
        "oil", "pantyhose", "petite", "pregnant", "private", "pvt", "redhead",
        "roleplay", "slave", "smalltits", "smoke", "spanish", "squirt",
        "stockings", "student", "submissive", "teen", "thick", "tits",
        "tokens", "torture", "toys", "trans", "young"
    ]

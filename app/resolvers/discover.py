import requests
from typing import List, Dict, Optional
from ..logger import logger


def get_chaturbate_streams(
    page: int = 1,
    limit: int = 90,
    gender: Optional[str] = None,
    region: Optional[str] = None,
    tag: Optional[str] = None
) -> Dict:
    """
    Fetch live Chaturbate streams using their public API
    
    Args:
        page: Page number (starting from 1)
        limit: Number of results per page (max 90)
        gender: Filter by gender (f=female, m=male, c=couple, t=trans)
        region: Filter by region (north_america, south_america, europe, asia, other)
        tag: Filter by tag
    
    Returns:
        Dict with streams list and metadata
    """
    logger.subsection("Chaturbate Discovery API")
    
    try:
        # Build API URL
        base_url = "https://chaturbate.com/api/public/affiliates/onlinerooms/"
        
        params = {
            "wm": "dbsOf",  # Watermark parameter
            "limit": min(limit, 90),  # Max 90 per request
            "offset": (page - 1) * limit
        }
        
        # Add filters
        if gender:
            # Map short codes to full names
            gender_map = {
                'f': 'female',
                'm': 'male', 
                'c': 'couple',
                't': 'trans'
            }
            params['genders'] = gender_map.get(gender, gender)
        
        if region:
            params['region'] = region
            
        if tag:
            params['tag'] = tag
        
        logger.progress("Fetching streams", params=params)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        
        response = requests.get(base_url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error("API error", status_code=response.status_code)
            return {
                "streams": [],
                "count": 0,
                "page": page,
                "total_pages": 0
            }
        
        data = response.json()
        
        # Parse results
        results = data.get('results', [])
        streams = []
        
        for room in results:
            try:
                stream = {
                    "username": room.get('username', ''),
                    "displayName": room.get('display_name', room.get('username', '')),
                    "age": room.get('age'),
                    "gender": room.get('gender', ''),
                    "location": room.get('location', ''),
                    "viewers": room.get('num_users', 0),
                    "thumbnail": room.get('image_url', ''),
                    "thumbnailUrl": room.get('image_url_360x270', room.get('image_url', '')),
                    "isHd": room.get('is_hd', False),
                    "isNew": room.get('is_new', False),
                    "roomSubject": room.get('room_subject', ''),
                    "tags": room.get('tags', []),
                    "chatUrl": f"https://chaturbate.com/{room.get('username', '')}/",
                    "iframeEmbedUrl": room.get('iframe_embed', ''),
                    "seconds_online": room.get('seconds_online', 0)
                }
                streams.append(stream)
            except Exception as e:
                logger.warning("Error parsing room", error=str(e))
                continue
        
        total_count = data.get('count', len(streams))
        total_pages = (total_count + limit - 1) // limit
        
        logger.success("Streams fetched", 
                      count=len(streams),
                      total=total_count,
                      page=page,
                      total_pages=total_pages)
        
        return {
            "streams": streams,
            "count": len(streams),
            "total": total_count,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_more": page < total_pages
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

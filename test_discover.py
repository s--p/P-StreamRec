#!/usr/bin/env python3
"""Test script for Discovery feature"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.resolvers.discover import get_chaturbate_streams

def test_discovery():
    print("🔍 Testing Discovery scraper...")
    print("-" * 50)
    
    # Test basic scraping
    print("\n1️⃣ Testing basic scraping (no filters)...")
    result = get_chaturbate_streams(page=1, limit=10)
    
    print(f"   ✓ Streams found: {result['count']}")
    print(f"   ✓ Total: {result.get('total', 'N/A')}")
    print(f"   ✓ Page: {result['page']}")
    print(f"   ✓ Has more: {result.get('has_more', False)}")
    
    if result.get('error'):
        print(f"   ❌ Error: {result['error']}")
        return False
    
    if result['count'] > 0:
        print(f"\n   First stream sample:")
        stream = result['streams'][0]
        print(f"   - Username: {stream['username']}")
        print(f"   - Viewers: {stream['viewers']}")
        print(f"   - Gender: {stream['gender']}")
        print(f"   - HD: {stream['isHd']}")
        print(f"   - Thumbnail: {stream['thumbnail'][:80]}...")
    else:
        print("   ⚠️ No streams found (this might be normal)")
    
    # Test with female filter
    print("\n2️⃣ Testing with female filter...")
    result = get_chaturbate_streams(page=1, limit=5, gender='f')
    print(f"   ✓ Female streams found: {result['count']}")
    
    # Test with tag filter
    print("\n3️⃣ Testing with tag filter (asian)...")
    result = get_chaturbate_streams(page=1, limit=5, tag='asian')
    print(f"   ✓ Tagged streams found: {result['count']}")
    
    print("\n" + "=" * 50)
    print("✅ All tests completed!")
    print("=" * 50)
    return True

if __name__ == "__main__":
    try:
        # Check dependencies
        try:
            from bs4 import BeautifulSoup
            print("✓ BeautifulSoup4 is installed")
        except ImportError:
            print("❌ BeautifulSoup4 is NOT installed")
            print("   Run: pip install beautifulsoup4 lxml")
            sys.exit(1)
        
        try:
            import requests
            print("✓ Requests is installed")
        except ImportError:
            print("❌ Requests is NOT installed")
            print("   Run: pip install requests")
            sys.exit(1)
        
        print()
        success = test_discovery()
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python3
"""
Download Magic: The Gathering card images from Scryfall.
Usage: python download_images.py <set_code>
Example: python download_images.py tla
"""

import requests
import sys
from pathlib import Path


def fetch_set_cards(set_code):
    """
    Fetch all cards from a specific set using Scryfall API.
    """
    print(f"Fetching cards for set: {set_code}")
    
    url = f"https://api.scryfall.com/cards/search"
    params = {
        "q": f"set:{set_code}",
        "unique": "cards"
    }
    
    all_cards = []
    has_more = True
    page = 1
    
    while has_more:
        print(f"  Fetching page {page}...")
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            page_cards = data.get("data", [])
            all_cards.extend(page_cards)
            print(f"  Got {len(page_cards)} cards (total: {len(all_cards)})")
            
            if data.get("has_more"):
                params["page"] = page + 1
                page += 1
            else:
                has_more = False
        except requests.exceptions.Timeout:
            print("  ERROR: Request timed out!")
            raise
        except requests.exceptions.RequestException as e:
            print(f"  ERROR: {e}")
            raise
    
    print(f"Found {len(all_cards)} cards")
    return all_cards


def get_image_url(card):
    """
    Get the image URL for a card.
    Handles normal cards and double-faced cards.
    """
    # For double-faced cards
    if "card_faces" in card:
        # Use the first face
        if card["card_faces"][0].get("image_uris"):
            return card["card_faces"][0]["image_uris"].get("normal")
    
    # For normal cards
    if "image_uris" in card:
        return card["image_uris"].get("normal")
    
    return None


def download_card_image(card, set_code, base_path):
    """
    Download a single card image.
    Returns True if successful, False otherwise.
    """
    collector_number = card.get("collector_number", "")
    image_url = get_image_url(card)
    
    if not image_url:
        print(f"  ⚠ {card.get('name', 'Unknown')} - No image URL available")
        return False
    
    # Determine if this is a token
    type_line = card.get("type_line", "").lower()
    is_token = "token" in type_line
    
    # Create directory structure: setimages/setcode/setcode/ or setimages/setcode/tsetcode/
    set_base = base_path / set_code.lower()
    if is_token:
        set_dir = set_base / f"t{set_code.lower()}"
    else:
        set_dir = set_base / set_code.lower()
    
    set_dir.mkdir(parents=True, exist_ok=True)
    
    # Build file path
    file_path = set_dir / f"{collector_number}.jpg"
    
    # Skip if already exists
    if file_path.exists():
        print(f"  ✓ {collector_number} - Already exists")
        return True
    
    # Download image
    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        with open(file_path, "wb") as f:
            f.write(response.content)
        
        print(f"  ✓ {collector_number} - Downloaded ({len(response.content)} bytes)")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"  ✗ {collector_number} - Failed to download: {e}")
        return False


def download_set_images(set_code):
    """
    Download all images for a set.
    """
    base_path = Path("sets/setimages")
    
    cards = fetch_set_cards(set_code)
    if not cards:
        print(f"No cards found for set: {set_code}")
        return False
    
    print(f"\nDownloading images for {len(cards)} cards...")
    
    successful = 0
    failed = 0
    skipped = 0
    
    for i, card in enumerate(cards, 1):
        card_name = card.get("name", "Unknown")
        print(f"[{i}/{len(cards)}] {card_name}")
        
        if download_card_image(card, set_code, base_path):
            successful += 1
        else:
            # Check if it was skipped (no image) or failed
            if get_image_url(card) is None:
                skipped += 1
            else:
                failed += 1
    
    print(f"\n=== Summary ===")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Skipped (no image): {skipped}")
    print(f"Images saved to: sets/setimages/{set_code.lower()}/")
    
    return failed == 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python download_images.py <set_code>")
        print("Example: python download_images.py tla")
        sys.exit(1)
    
    set_code = sys.argv[1]
    
    try:
        success = download_set_images(set_code)
        sys.exit(0 if success else 1)
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from Scryfall: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

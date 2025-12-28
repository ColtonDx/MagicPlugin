#!/usr/bin/env python3
"""
Fetch Magic: The Gathering cards from Scryfall and format them for Lackey CCG.
Usage: python fetch_set.py <set_code> [--download-images]
Example: python fetch_set.py tla
Example: python fetch_set.py tla --download-images
"""

import requests
import sys
import os
from pathlib import Path

# Output file to write cards to (in ./sets/)
OUTPUT_FILE = None  # Set this to a filename to write to existing file, e.g., "custom.txt"

# Download images by default
DOWNLOAD_IMAGES = False  # Set to True to download images, or use --download-images flag


def convert_mana_cost(cost_string):
    """
    Convert Scryfall mana cost format to Lackey format.
    {2}{w}{u} -> {2}{w}{u}
    """
    if not cost_string:
        return ""
    # Scryfall already uses the format we need, just lowercase the letters
    result = ""
    i = 0
    while i < len(cost_string):
        if cost_string[i] == "{":
            # Find closing bracket
            end = cost_string.index("}", i)
            mana_part = cost_string[i:end+1]
            result += mana_part.lower()
            i = end + 1
        else:
            i += 1
    return result


def get_color_string(colors):
    """
    Convert color array to space-separated string.
    ["W", "U"] -> "W U"
    """
    if not colors:
        return ""
    return " ".join(colors)


def get_color_id(colors):
    """
    Convert color array to WUBRG string.
    ["W", "U"] -> "WU" (or in WUBRG order)
    """
    if not colors:
        return ""
    # WUBRG order
    order = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}
    sorted_colors = sorted(colors, key=lambda x: order.get(x, 5))
    return "".join(sorted_colors)


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


def format_card(card, set_code):
    """
    Format a single card for Lackey CCG output.
    """
    name = card.get("name", "")
    collector_number = card.get("collector_number", "")
    image_file = f"{set_code}/{collector_number}"
    
    colors = card.get("colors", [])
    color_string = get_color_string(colors)
    color_id = get_color_id(colors)
    
    cost = convert_mana_cost(card.get("mana_cost", ""))
    mana_value = card.get("cmc", 0)
    
    type_line = card.get("type_line", "")
    
    power = card.get("power", "")
    toughness = card.get("toughness", "")
    loyalty = card.get("loyalty", "")
    
    rarity = card.get("rarity", "").upper()[0] if card.get("rarity") else ""
    
    # Get oracle text and remove reminder text (text in parentheses)
    oracle_text = card.get("oracle_text", "")
    # Remove reminder text in parentheses
    import re
    oracle_text = re.sub(r'\s*\([^)]*\)\s*', ' ', oracle_text).strip()
    oracle_text = oracle_text.replace("\n", " | ")
    
    # Format: Name, Set, ImageFile, ActualSet, Color, ColorID, Cost, ManaValue, Type, Power, Toughness, Loyalty, Rarity, DraftQualities, Sound, Script, Text
    fields = [
        name,
        set_code,
        image_file,
        set_code,
        color_string,
        color_id,
        cost,
        str(int(mana_value)),
        type_line,
        power,
        toughness,
        loyalty,
        rarity,
        "",  # DraftQualities
        "",  # Sound
        "",  # Script
        oracle_text
    ]
    
    return "\t".join(fields)


def write_set_file(set_code, cards):
    """
    Write formatted cards to a set file.
    If OUTPUT_FILE is set, appends to that file (or creates it).
    Otherwise, creates a new file named {set_code}.txt
    """
    output_dir = Path("sets")
    output_dir.mkdir(exist_ok=True)
    
    # Sort cards by collector number (numerically aware)
    def sort_key(card):
        col_num = card.get("collector_number", "0")
        # Handle numeric sorting: "1", "10", "2" -> 1, 2, 10
        parts = []
        current = ""
        for char in col_num:
            if char.isdigit():
                current += char
            else:
                if current:
                    parts.append((0, int(current)))
                    current = ""
                parts.append((1, char))
        if current:
            parts.append((0, int(current)))
        return parts
    
    cards = sorted(cards, key=sort_key)
    
    # Determine output file
    if OUTPUT_FILE:
        output_file = output_dir / OUTPUT_FILE
    else:
        output_file = output_dir / f"{set_code.lower()}.txt"
    
    # Check if file exists
    file_exists = output_file.exists()
    
    with open(output_file, "a" if file_exists else "w", encoding="utf-8-sig") as f:
        # Write header and blank lines only if creating new file
        if not file_exists:
            header = "Name\tSet\tImageFile\tActualSet\tColor\tColorID\tCost\tManaValue\tType\tPower\tToughness\tLoyalty\tRarity\tDraftQualities\tSound\tScript\tText"
            f.write(header + "\n")
            f.write("\n\n")
        
        # Write cards
        for card in cards:
            f.write(format_card(card, set_code.lower()) + "\n")
    
    if file_exists:
        print(f"Appended {len(cards)} cards to {output_file}")
    else:
        print(f"Created {output_file} with {len(cards)} cards")
    
    return output_file


def update_list_file(set_code):
    """
    Update ListOfCardDataFiles.txt to include the new set file.
    """
    list_file = Path("ListOfCardDataFiles.txt")
    
    set_filename = f"{set_code.lower()}.txt"
    
    with open(list_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if already included
    if f"<filetoinclude>{set_filename}</filetoinclude>" in content:
        print(f"{set_filename} already in ListOfCardDataFiles.txt")
        return
    
    # Add before closing tag
    closing_tag = "</listofcarddatafiles>"
    if closing_tag in content:
        new_entry = f"<filetoinclude>{set_filename}</filetoinclude>\n"
        content = content.replace(closing_tag, new_entry + closing_tag)
        
        with open(list_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"Updated ListOfCardDataFiles.txt to include {set_filename}")


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
        return True
    
    # Download image
    try:
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        with open(file_path, "wb") as f:
            f.write(response.content)
        
        return True
        
    except requests.exceptions.RequestException:
        return False


def download_set_images(set_code, cards):
    """
    Download all images for a set from already-fetched cards.
    """
    base_path = Path("sets/setimages")
    
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
    
    print(f"\n=== Image Download Summary ===")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Skipped (no image): {skipped}")
    print(f"Images saved to: sets/setimages/{set_code.lower()}/")


def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_set.py <set_code> [--download-images]")
        print("Example: python fetch_set.py tla")
        print("Example: python fetch_set.py tla --download-images")
        sys.exit(1)
    
    set_code = sys.argv[1]
    download_images = DOWNLOAD_IMAGES or "--download-images" in sys.argv
    
    try:
        cards = fetch_set_cards(set_code)
        if not cards:
            print(f"No cards found for set: {set_code}")
            sys.exit(1)
        
        write_set_file(set_code, cards)
        update_list_file(set_code)
        
        if download_images:
            download_set_images(set_code, cards)
        
        print("Done!")
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from Scryfall: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

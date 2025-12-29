#!/usr/bin/env python3
"""
Fetch Magic: The Gathering cards from Scryfall and format them for Lackey CCG.
Reads configuration from config.txt in the same folder as this script.
"""

import sys
import os
import time
import logging
from pathlib import Path

# Determine script/executable directory for both Python and PyInstaller
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    script_dir = Path(sys.executable).parent
else:
    # Running as regular Python script
    script_dir = Path(__file__).parent

# Setup logging
log_file = script_dir / "fetch.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Auto-install missing dependencies
required_packages = {
    "requests": "requests",
    "PIL": "Pillow",
}

for module_name, package_name in required_packages.items():
    try:
        __import__(module_name)
    except ImportError:
        print(f"Installing {package_name}...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

import requests
from PIL import Image
from io import BytesIO


def load_config():
    """
    Load configuration from config.txt in the same directory as the script.
    Works with both regular Python and PyInstaller-compiled executables.
    Returns tuple: (output_file, set_codes_list, download_images)
    """
    config_file = script_dir / "config.txt"
    
    # Default values
    output_file = "custom.txt"
    set_codes = []
    download_images = False
    
    if not config_file.exists():
        logger.warning(f"config.txt not found at {config_file}")
        logger.warning("Using default values: output_file=custom.txt, set_codes=[], download_images=False")
        return output_file, set_codes, download_images
    
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue
                
                if "=" not in line:
                    continue
                
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                if key == "output_file":
                    output_file = value
                elif key == "set_codes":
                    # Parse comma-separated set codes
                    set_codes = [code.strip() for code in value.split(",") if code.strip()]
                elif key == "download_images":
                    download_images = value.lower() in ("true", "yes", "1")
    except Exception as e:
        logger.error(f"Error reading config.txt: {e}")
        logger.warning("Using default values")
        return "custom.txt", [], False
    
    return output_file, set_codes, download_images


# Global variables loaded from config
OUTPUT_FILE, SET_CODES, DOWNLOAD_IMAGES = load_config()


def convert_mana_cost(cost_string):
    """
    Convert Scryfall mana cost format to Lackey format.
    {2}{w}{u} -> {2}{W}{U}
    """
    if not cost_string:
        return ""
    # Scryfall already uses the format we need, just uppercase the letters
    result = ""
    i = 0
    while i < len(cost_string):
        if cost_string[i] == "{":
            # Find closing bracket
            end = cost_string.index("}", i)
            mana_part = cost_string[i:end+1]
            result += mana_part.upper()
            i = end + 1
        else:
            i += 1
    return result


def get_color_string(colors):
    """
    Convert color array to string in WUBRG order without spaces.
    ["U", "W"] -> "WU"
    """
    if not colors:
        return ""
    # WUBRG order
    order = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}
    sorted_colors = sorted(colors, key=lambda x: order.get(x, 5))
    return "".join(sorted_colors)


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


def get_script(card, set_code):
    """
    Get script for the card.
    For double-faced cards, creates a script to spawn the other side.
    Format: <s><l>Create other side</l><f>/spawn [set_code] Other Face Name</f></s>
    """
    if "card_faces" not in card or len(card["card_faces"]) < 2:
        return ""
    
    # Get the names of both faces
    face_names = [face.get("name", "") for face in card["card_faces"]]
    
    # Determine which face is current (we format the first face)
    # The script should spawn the second face
    if len(face_names) >= 2:
        other_face_name = face_names[1]
        script = f"<s><l>Create other side</l><f>/spawn [{set_code}] {other_face_name}</f></s>"
        return script
    
    return ""


def get_sound(type_line):
    """
    Get sound based on card type.
    Creature takes priority - if a card is a creature, it always gets creature sound.
    For non-creatures, only sets sound if there is exactly one clear type.
    Returns the type name if found, empty string if unclear or multiple types.
    """
    if not type_line:
        return ""
    
    type_line_lower = type_line.lower()
    
    # Creature takes priority
    if "creature" in type_line_lower:
        return "creature"
    
    sound_types = ["artifact", "instant", "enchantment", "sorcery", "land"]
    
    # Find which types match
    matched_types = []
    for sound_type in sound_types:
        if sound_type in type_line_lower:
            matched_types.append(sound_type)
    
    # Only set sound if exactly one type matched
    if len(matched_types) == 1:
        return matched_types[0]
    
    return ""


def fetch_set_cards(set_code):
    """
    Fetch all cards from a specific set using Scryfall API.
    Uses unique=prints to get all versions with different collector numbers.
    """
    logger.info(f"Fetching cards for set: {set_code}")
    
    url = f"https://api.scryfall.com/cards/search"
    params = {
        "q": f"set:{set_code}",
        "unique": "prints"
    }
    
    all_cards = []
    has_more = True
    page = 1
    
    while has_more:
        logger.info(f"  Fetching page {page}...")
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            page_cards = data.get("data", [])
            all_cards.extend(page_cards)
            logger.info(f"  Got {len(page_cards)} cards (total: {len(all_cards)})")
            
            if data.get("has_more"):
                params["page"] = page + 1
                page += 1
                # Rate limit: 100ms delay between requests (10 requests per second)
                time.sleep(0.1)
            else:
                has_more = False
        except requests.exceptions.Timeout:
            logger.error("  ERROR: Request timed out!")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"  ERROR: {e}")
            raise
    
    logger.info(f"Found {len(all_cards)} cards")
    return all_cards


def format_card(card, set_code):
    """
    Format a single card for Lackey CCG output.
    For double-faced cards, appends 'a' to collector number for front face.
    """
    name = card.get("name", "")
    collector_number = card.get("collector_number", "")
    
    # For double-faced cards, append 'a' to the front face image file
    is_double_faced = "card_faces" in card and len(card["card_faces"]) >= 2
    if is_double_faced:
        image_file = f"{set_code}/{collector_number}a"
        # For double-faced cards, get attributes from the first face
        front_face = card["card_faces"][0]
        colors = front_face.get("colors", [])
        cost = convert_mana_cost(front_face.get("mana_cost", ""))
        type_line = front_face.get("type_line", "")
        power = front_face.get("power", "")
        toughness = front_face.get("toughness", "")
        loyalty = front_face.get("loyalty", "")
        oracle_text = front_face.get("oracle_text", "")
    else:
        image_file = f"{set_code}/{collector_number}"
        # For single-faced cards, get attributes from card root
        colors = card.get("colors", [])
        cost = convert_mana_cost(card.get("mana_cost", ""))
        type_line = card.get("type_line", "")
        power = card.get("power", "")
        toughness = card.get("toughness", "")
        loyalty = card.get("loyalty", "")
        oracle_text = card.get("oracle_text", "")
    
    color_string = get_color_string(colors)
    color_id = get_color_id(colors)
    
    mana_value = card.get("cmc", 0)
    
    rarity = card.get("rarity", "").upper()[0] if card.get("rarity") else ""
    
    # Remove reminder text in parentheses
    import re
    oracle_text = re.sub(r'\s*\([^)]*\)\s*', ' ', oracle_text).strip()
    oracle_text = oracle_text.replace("\n", " | ")
    
    sound = get_sound(type_line)
    script = get_script(card, set_code)
    
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
        sound,  # Sound
        script,  # Script
        oracle_text
    ]
    
    return "\t".join(fields)


def format_back_card(card, set_code):
    """
    Format the back side of a double-faced card.
    Name is prefixed with [set_code].
    Image file uses collector_numberb.
    """
    if "card_faces" not in card or len(card["card_faces"]) < 2:
        return None
    
    back_face = card["card_faces"][1]
    collector_number = card.get("collector_number", "")
    
    # Name with set code prefix
    back_name = f"[{set_code}] {back_face.get('name', '')}"
    image_file = f"{set_code}/{collector_number}b"
    
    # Get colors from back face
    colors = back_face.get("colors", [])
    color_string = get_color_string(colors)
    color_id = get_color_id(colors)
    
    # Back face might have different mana cost
    cost = convert_mana_cost(back_face.get("mana_cost", ""))
    
    # Use original card's mana value (cmc is same for both sides)
    mana_value = card.get("cmc", 0)
    
    type_line = back_face.get("type_line", "")
    
    power = back_face.get("power", "")
    toughness = back_face.get("toughness", "")
    loyalty = back_face.get("loyalty", "")
    
    rarity = card.get("rarity", "").upper()[0] if card.get("rarity") else ""
    
    # Get oracle text from back face
    oracle_text = back_face.get("oracle_text", "")
    import re
    oracle_text = re.sub(r'\s*\([^)]*\)\s*', ' ', oracle_text).strip()
    oracle_text = oracle_text.replace("\n", " | ")
    
    sound = get_sound(type_line)
    
    # Back side doesn't have script (no need to spawn another side)
    script = ""
    
    # Format: Name, Set, ImageFile, ActualSet, Color, ColorID, Cost, ManaValue, Type, Power, Toughness, Loyalty, Rarity, DraftQualities, Sound, Script, Text
    fields = [
        back_name,
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
        sound,  # Sound
        script,  # Script
        oracle_text
    ]
    
    return "\t".join(fields)


def write_set_file(set_code, cards):
    """
    Write formatted cards to the output file specified in config.txt.
    Appends cards from all sets to the same file.
    Returns tuple: (output_file, was_newly_created)
    """
    output_dir = Path("sets")
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / OUTPUT_FILE
    
    # Check if file exists
    file_exists = output_file.exists()
    
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
    
    with open(output_file, "a" if file_exists else "w", encoding="utf-8") as f:
        # Write header and blank lines only if creating new file
        if not file_exists:
            header = "Name\tSet\tImageFile\tActualSet\tColor\tColorID\tCost\tManaValue\tType\tPower\tToughness\tLoyalty\tRarity\tDraftQualities\tSound\tScript\tText"
            f.write(header + "\n")
            f.write("\n\n")
        
        # Write cards
        for card in cards:
            f.write(format_card(card, set_code.lower()) + "\n")
            # Also write back side of double-faced cards
            back_card = format_back_card(card, set_code.lower())
            if back_card:
                f.write(back_card + "\n")
    
    if file_exists:
        logger.info(f"Appended {len(cards)} cards to {output_file}")
    else:
        logger.info(f"Created {output_file} with {len(cards)} cards")
    
    return output_file, not file_exists


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
        logger.info(f"{set_filename} already in ListOfCardDataFiles.txt")
        return
    
    # Add before closing tag
    closing_tag = "</listofcarddatafiles>"
    if closing_tag in content:
        new_entry = f"<filetoinclude>{set_filename}</filetoinclude>\n"
        content = content.replace(closing_tag, new_entry + closing_tag)
        
        with open(list_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"Updated ListOfCardDataFiles.txt to include {set_filename}")


def deduplicate_output_file(output_file):
    """
    Deduplicate lines in the output file, keeping the latest entries.
    Matches on: card name + set code + collector number.
    Preserves header (first line) and blank lines, deduplicates card data.
    """
    with open(output_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    if not lines:
        return
    
    # Preserve header
    header = lines[0]
    
    # Find where the actual card data starts (after blank lines)
    data_start = 1
    blank_lines = []
    while data_start < len(lines) and lines[data_start].strip() == "":
        blank_lines.append(lines[data_start])
        data_start += 1
    
    # Deduplicate card data, keeping latest entries
    # Match on: card name + image_file (which contains set_code/collector_number)
    seen_keys = set()
    unique_cards = []
    for line in reversed(lines[data_start:]):
        parts = line.rstrip('\n').split('\t')
        if len(parts) >= 3:
            name = parts[0]
            image_file = parts[2]  # format: "set_code/collector_number"
            # Create key from name and image_file
            key = (name, image_file)
            
            if key not in seen_keys:
                seen_keys.add(key)
                unique_cards.append(line)
    
    # Reverse back to original order
    unique_cards.reverse()
    
    # Write back
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(header)
        f.writelines(blank_lines)
        f.writelines(unique_cards)
    
    logger.info(f"Deduplicated {output_file}")


def get_image_url(card):
    """
    Get the image URL for a card.
    Handles normal cards and double-faced cards.
    Prefers border_crop version: border_crop > large > normal > small
    """
    # For double-faced cards
    if "card_faces" in card:
        # Use the first face
        if card["card_faces"][0].get("image_uris"):
            image_uris = card["card_faces"][0]["image_uris"]
            return image_uris.get("border_crop") or image_uris.get("large") or image_uris.get("normal") or image_uris.get("small")
    
    # For normal cards
    if "image_uris" in card:
        image_uris = card["image_uris"]
        return image_uris.get("border_crop") or image_uris.get("large") or image_uris.get("normal") or image_uris.get("small")
    
    return None


def download_card_image(card, set_code, base_path):
    """
    Download a single card image.
    For double-faced cards, downloads both sides with 'a' and 'b' suffixes.
    Returns True if successful, False otherwise.
    """
    collector_number = card.get("collector_number", "")
    
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
    
    # Check if this is a double-faced card
    is_double_faced = "card_faces" in card and len(card["card_faces"]) >= 2
    
    if is_double_faced:
        # Download both faces
        success = True
        for i, face in enumerate(card["card_faces"]):
            suffix = chr(97 + i)  # 'a', 'b', 'c', etc.
            image_uris = face.get("image_uris", {})
            # Prefer border_crop version: border_crop > large > normal > small
            image_url = image_uris.get("border_crop") or image_uris.get("large") or image_uris.get("normal") or image_uris.get("small")
            
            if not image_url:
                success = False
                continue
            
            file_path = set_dir / f"{collector_number}{suffix}.jpg"
            
            # Skip if already exists
            if file_path.exists():
                continue
            
            try:
                response = requests.get(image_url, timeout=30)
                response.raise_for_status()
                
                # Download and resize image
                image = Image.open(BytesIO(response.content))
                image = image.resize((312, 445), Image.Resampling.LANCZOS)
                image.save(file_path, "JPEG")
            except requests.exceptions.RequestException:
                success = False
            except Exception:
                success = False
        
        return success
    else:
        # Single-faced card
        image_url = get_image_url(card)
        
        if not image_url:
            return False
        
        # Build file path
        file_path = set_dir / f"{collector_number}.jpg"
        
        # Skip if already exists
        if file_path.exists():
            return True
        
        # Download and resize image
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            image = Image.open(BytesIO(response.content))
            image = image.resize((312, 445), Image.Resampling.LANCZOS)
            image.save(file_path, "JPEG")
            
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
        logger.info(f"[{i}/{len(cards)}] {card_name}")
        
        if download_card_image(card, set_code, base_path):
            successful += 1
        else:
            # Check if it was skipped (no image) or failed
            if get_image_url(card) is None:
                skipped += 1
            else:
                failed += 1
        
        # Rate limit: 100ms delay between image downloads
        if i < len(cards):
            time.sleep(0.1)
    
    logger.info(f"\n=== Image Download Summary ===")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Skipped (no image): {skipped}")
    logger.info(f"Images saved to: sets/setimages/{set_code.lower()}/")


def main():
    """
    Process all set codes from config.txt.
    """
    logger.info("=" * 60)
    logger.info("Magic: The Gathering Card Fetcher - Starting")
    logger.info("=" * 60)
    
    if not SET_CODES:
        logger.error("No set codes defined in config.txt")
        logger.error("Please add set_codes to config.txt (e.g., set_codes=tla,lci)")
        sys.exit(1)
    
    logger.info(f"Fetching {len(SET_CODES)} set(s): {', '.join(SET_CODES)}")
    logger.info(f"Output file: sets/{OUTPUT_FILE}")
    logger.info(f"Download images: {DOWNLOAD_IMAGES}\n")
    
    successful_sets = 0
    failed_sets = 0
    
    for i, set_code in enumerate(SET_CODES, 1):
        logger.info(f"[{i}/{len(SET_CODES)}] Processing {set_code}...")
        logger.info("=" * 50)
        
        try:
            cards = fetch_set_cards(set_code)
            if not cards:
                logger.warning(f"No cards found for set: {set_code}")
                failed_sets += 1
                continue
            
            output_file, was_newly_created = write_set_file(set_code, cards)
            
            # Deduplicate the output file
            deduplicate_output_file(output_file)
            
            # Only update list file if we created a new file
            if was_newly_created:
                update_list_file(set_code)
            
            if DOWNLOAD_IMAGES:
                download_set_images(set_code, cards)
            
            logger.info(f"✓ Completed {set_code}!")
            successful_sets += 1
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching from Scryfall for {set_code}: {e}")
            failed_sets += 1
            continue
        except Exception as e:
            logger.error(f"Error processing {set_code}: {e}", exc_info=True)
            failed_sets += 1
            continue
    
    logger.info("=" * 60)
    logger.info("All sets processed!")
    logger.info(f"Successful: {successful_sets}/{len(SET_CODES)}")
    logger.info(f"Failed: {failed_sets}/{len(SET_CODES)}")
    logger.info(f"Log file: {log_file}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

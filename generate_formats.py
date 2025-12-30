#!/usr/bin/env python3
"""
Generate formats.txt file by querying Scryfall API for legal sets in each format.
Queries Scryfall for all sets legal in Modern, Legacy, Pioneer, and Standard.
"""

import sys
import logging
import argparse
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installing requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Determine script directory
if getattr(sys, 'frozen', False):
    script_dir = Path(sys.executable).parent
else:
    script_dir = Path(__file__).parent


def fetch_sets_for_format(format_name):
    """
    Fetch all set codes legal in a specific format from Scryfall API.
    Returns a list of set codes (lowercase).
    """
    logger.info(f"Fetching sets legal in {format_name}...")
    
    try:
        url = "https://api.scryfall.com/sets"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        sets = data.get("data", [])
        
        # Map of format names to Scryfall format codes
        format_map = {
            "Standard": "standard",
            "Pioneer": "pioneer",
            "Modern": "modern",
            "Legacy": "legacy"
        }
        
        scryfall_format = format_map.get(format_name, format_name.lower())
        
        # Collect all set codes legal in this format
        set_codes = []
        for s in sets:
            # Check if set is legal in this format
            legalities = s.get("legalities", {})
            if legalities.get(scryfall_format) == "legal":
                code = s.get("code")
                if code:
                    set_codes.append(code.lower())
        
        # Sort by release date (sets appear ordered in Scryfall)
        logger.info(f"Found {len(set_codes)} sets legal in {format_name}")
        
        return set_codes
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching sets from Scryfall for {format_name}: {e}")
        return []


def generate_formats_file(output_file=None):
    """
    Generate formats.txt by querying Scryfall for legal sets in each format.
    """
    if output_file is None:
        output_file = script_dir / "formats.txt"
    
    logger.info("=" * 60)
    logger.info("Magic: The Gathering Formats Generator - Starting")
    logger.info("=" * 60)
    
    # Formats to generate, in order
    formats = ["Standard", "Pioneer", "Modern", "Legacy"]
    
    # Fetch sets for each format
    format_sets = {}
    for format_name in formats:
        set_codes = fetch_sets_for_format(format_name)
        if set_codes:
            format_sets[format_name] = set_codes
        else:
            logger.warning(f"No sets found for {format_name}")
    
    # Generate the XML content
    content = "<formatdefinitions>\n\n"
    
    for format_name in formats:
        if format_name not in format_sets:
            continue
        
        set_codes = format_sets[format_name]
        content += f"<format><label>{format_name}</label>\n"
        
        for set_code in set_codes:
            content += f"\t<set>{set_code}</set>\n"
        
        content += "</format>\n\n"
    
    content += "</formatdefinitions>\n"
    
    # Write to file
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"Successfully generated {output_file}")
        logger.info(f"Formats included: {', '.join(format_sets.keys())}")
        
        # Print summary
        for format_name in formats:
            if format_name in format_sets:
                count = len(format_sets[format_name])
                logger.info(f"  {format_name}: {count} sets")
        
        return True
    except Exception as e:
        logger.error(f"Error writing to {output_file}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate formats.txt by querying Scryfall API"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output file path (default: formats.txt in script directory)"
    )
    
    args = parser.parse_args()
    
    output_file = None
    if args.output:
        output_file = Path(args.output)
    
    success = generate_formats_file(output_file)
    
    logger.info("=" * 60)
    if success:
        logger.info("Formats file generated successfully!")
    else:
        logger.error("Failed to generate formats file")
        sys.exit(1)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

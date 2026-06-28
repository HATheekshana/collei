import requests
import json
import time

API = "https://genshin-impact.fandom.com/api.php"

# ----------------------------
# 1. Get all weekly bosses
# ----------------------------
def get_boss_list():
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": "Category:Weekly_Bosses",
        "cmlimit": 500,
        "format": "json"
    }

    r = requests.get(API, params=params)
    data = r.json()

    return [item["title"] for item in data["query"]["categorymembers"]]


# ----------------------------
# 2. Get wiki page content
# ----------------------------
def get_page_content(title):
    params = {
        "action": "query",
        "prop": "revisions",
        "rvprop": "content",
        "titles": title,
        "format": "json"
    }

    r = requests.get(API, params=params)
    pages = r.json()["query"]["pages"]

    for page_id in pages:
        if "revisions" in pages[page_id]:
            return pages[page_id]["revisions"][0]["*"]
    return ""


# ----------------------------
# 3. Extract sections safely
# ----------------------------
def extract_section(text, section_name):
    import re

    pattern = rf"== {section_name} ==(.*?)(==|$)"
    match = re.search(pattern, text, re.S)

    if match:
        return match.group(1).strip()
    return None


# ----------------------------
# 4. Build boss data
# ----------------------------
def build_boss(title):
    print(f"Fetching: {title}")

    content = get_page_content(title)

    boss_data = {
        "name": title,
        "mechanics": extract_section(content, "Mechanics"),
        "strategy": extract_section(content, "Strategy"),
        "resistances": extract_section(content, "Resistance"),
        "drops": extract_section(content, "Rewards"),
    }

    return boss_data


# ----------------------------
# 5. MAIN SCRAPER
# ----------------------------
def main():
    bosses = get_boss_list()

    all_boss_data = []

    for boss in bosses:
        try:
            data = build_boss(boss)
            all_boss_data.append(data)

            time.sleep(1)  # IMPORTANT: avoid API spam

        except Exception as e:
            print("Error with", boss, e)

    # ----------------------------
    # 6. SAVE TO JSON FILE
    # ----------------------------
    with open("bosses.json", "w", encoding="utf-8") as f:
        json.dump(all_boss_data, f, indent=2, ensure_ascii=False)

    print("\n✅ Saved to bosses.json")


# Run script
main()
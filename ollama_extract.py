#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scraper complet Ollama :

1. Récupère tous les modèles depuis https://ollama.com/library
2. Scrape chaque page modèle
3. Extrait toutes les infos :
   - description
   - catégories
   - pulls
   - variantes
   - params_summary
   - vision_support
   - agentic_rl
   - top_benchmark
4. Sauvegarde en CSV + JSON
"""

import requests
import re
import csv
import json
import time
from pathlib import Path
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# ============================================================
# 1. Récupérer tous les modèles
# ============================================================

def get_all_models():

    url = "https://ollama.com/library"

    print("Téléchargement de la liste des modèles...")

    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    html = r.text

    matches = re.findall(r'/library/([a-zA-Z0-9\-\.:]+)', html)

    models = sorted(set(matches))

    print(f"{len(models)} modèles trouvés.\n")

    return models


# ============================================================
# 2. Scraper un modèle
# ============================================================

def extract_model(url):

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print("Erreur:", e)
        return None

    soup = BeautifulSoup(r.text, "lxml")

    data = {
        "model_name": "",
        "description": "",
        "categories": [],
        "pulls": "",
        "updated": "",
        "variants": {},
        "params_summary": "",
        "vision_support": "non",
        "agentic_rl": "non",
        "top_benchmark": "",
        "url": url
    }

    # nom
    if soup.title:
        data["model_name"] = soup.title.text.strip()

    # description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        data["description"] = meta.get("content", "")

    # catégories
    cats = soup.find_all("span")
    for c in cats:
        txt = c.text.strip().lower()
        if txt in ["vision", "tools", "chat", "coding", "reasoning"]:
            data["categories"].append(txt)

    # pulls
    pulls = soup.find(attrs={"x-test-pull-count": True})
    if pulls:
        data["pulls"] = pulls.text.strip()

    # updated
    upd = soup.find(attrs={"x-test-updated": True})
    if upd:
        data["updated"] = upd.text.strip()

    # variantes
    rows = soup.find_all("a", href=re.compile(r'/library/.+:.+'))

    for r in rows:

        href = r.get("href")

        if ":" in href:

            variant = href.split(":")[-1]

            parent = r.find_parent()

            size = ""

            if parent:
                txt = parent.text
                m = re.search(r'(\d+\.?\d*\s*(GB|MB|B))', txt)
                if m:
                    size = m.group(1)

            data["variants"][variant] = size

    # readme
    readme = soup.find(id="readme")

    text = readme.text if readme else soup.text

    # params
    m = re.search(r'(\d+(\.\d+)?B)', text)
    if m:
        data["params_summary"] = m.group(1)

    # vision
    if "vision" in text.lower() or "multimodal" in text.lower():
        data["vision_support"] = "oui"

    # agentic
    if "agentic" in text.lower() or "function calling" in text.lower():
        data["agentic_rl"] = "oui"

    # benchmark
    m = re.search(r'(SWE-bench|GPQA|AIME).*?(\d+\.\d+)%', text)

    if m:
        data["top_benchmark"] = f"{m.group(1)} {m.group(2)}%"

    return data


# ============================================================
# 3. Scraper tout
# ============================================================

def scrape_all():

    models = get_all_models()

    all_data = []

    total = len(models)

    for i, model in enumerate(models):

        url = f"https://ollama.com/library/{model}"

        print(f"[{i+1}/{total}] {model}")

        data = extract_model(url)

        if data:
            all_data.append(data)

        time.sleep(0.5)

    return all_data


# ============================================================
# 4. Save CSV
# ============================================================

def save_csv(all_data, filename="ollama_models.csv"):

    rows = []

    for data in all_data:

        base = {
            "model_name": data["model_name"],
            "description": data["description"],
            "categories": ", ".join(data["categories"]),
            "pulls": data["pulls"],
            "updated": data["updated"],
            "params_summary": data["params_summary"],
            "vision_support": data["vision_support"],
            "agentic_rl": data["agentic_rl"],
            "top_benchmark": data["top_benchmark"],
            "url": data["url"],
            "variant": "",
            "size": ""
        }

        rows.append(base)

        for variant, size in data["variants"].items():

            row = base.copy()

            row["variant"] = variant
            row["size"] = size

            rows.append(row)

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:

        writer = csv.DictWriter(f, fieldnames=rows[0].keys())

        writer.writeheader()

        writer.writerows(rows)

    print(f"\nCSV sauvé: {filename}")


# ============================================================
# 5. Save JSON
# ============================================================

def save_json(all_data, filename="ollama_models.json"):

    with open(filename, "w", encoding="utf-8") as f:

        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print("JSON sauvé:", filename)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    all_data = scrape_all()

    save_csv(all_data)

    save_json(all_data)

    print("\nTerminé.")

"""One-off: probe every candidate read endpoint with a seeded token.

Tells us which reads return 200 standalone, which are empty, which gate on
profile (400), and which need an id chained from a list. Not part of the
harness — a discovery aid for building the read scenarios.
"""

import json
import sys

import requests


BASE = "http://localhost:8000"
fx = json.load(open("fixtures/tokens.json"))
tok = fx["tokens"][0]
uid = tok["user_id"]
H = {"Authorization": f"Bearer {tok['access']}"}

STANDALONE = [
    # recipes
    "/recipes/cuisines/", "/recipes/dietary-preferences/", "/recipes/allergies/",
    "/recipes/meals/", "/recipes/preparation-type/", "/recipes/list/",
    "/recipes/shop-list/", "/recipes/recommended/", "/recipes/trending/", "/recipes/me/",
    # products
    "/products/list/", "/products/me/", "/products/shop-list/", "/products/chatgpt/",
    "/products/ingredient-lookup/?product_title=milk",
    # ingredients (root + /pantry/ mounts)
    "/ingredients/search/?search=chicken", "/ingredients/search/recipe-creation/?search=chicken",
    "/ingredients/list/?search=chicken", "/categories/search/?search=meat",
    "/pantry/ingredients/",
    # pantry (already covered, sanity)
    "/pantry/list/", "/pantry/expiring/", "/pantry/history/",
    # cookbooks
    "/cookbooks/", "/cookbooks/community-cookbooks/",
    # meal-planner
    "/meal-planner/today/", "/meal-planner/meal-frequency/", "/meal-planner/recipes/",
    "/meal-planner/history/", "/meal-planner/weekly-stats/", "/meal-planner/plans/",
    "/meal-planner/recently-eaten/",
    # communications
    "/communications/notifications/", "/communications/notification-preferences/",
    # shop
    "/shop/carts/",
    # users
    "/users/me/", "/users/quick-actions/list/",
    "/users/document-retrieve/?type=privacy_policy",
    f"/users/{uid}/chef-profile/",
]


def hit(path, timeout=30):
    try:
        r = requests.get(BASE + path, headers=H, timeout=timeout)
        n = len(r.content)
        body = ""
        if r.status_code >= 400:
            body = r.text[:120].replace("\n", " ")
        return f"{r.status_code:>3}  {n:>8}B  {path}   {body}"
    except Exception as e:  # noqa: BLE001
        return f"ERR        -  {path}   {type(e).__name__}: {e}"


print("=== STANDALONE ===")
for p in STANDALONE:
    print(hit(p))

# --- chained list -> detail probes -----------------------------------------
print("\n=== CHAINED (list -> detail) ===")


def first_id(path, *keys):
    try:
        r = requests.get(BASE + path, headers=H, timeout=30)
        d = r.json()
        results = d.get("results", d) if isinstance(d, dict) else d
        if isinstance(results, dict):
            results = results.get("results") or results.get("data") or []
        if results:
            item = results[0]
            for k in keys:
                if item.get(k) is not None:
                    return item[k]
    except Exception as e:  # noqa: BLE001
        print(f"  (list {path} failed: {e})")
    return None


rid = first_id("/recipes/list/?page=1", "id")
print("recipe id:", rid)
if rid:
    for sub in ("", "reviews/", "products/", "cook-mode/", "cook-mode/instructions/?serving_size=2",
                "recommended-products/"):
        print(hit(f"/recipes/{rid}/{sub}"))

pid = first_id("/products/list/", "id")
print("product id:", pid)
if pid:
    print(hit(f"/products/{pid}/"))
    print(hit(f"/products/{pid}/swappable-list/"))

ping = first_id("/pantry/ingredients/", "id")
print("pantry-ingredient id:", ping)
if ping:
    print(hit(f"/pantry/ingredient/{ping}/"))

ccb = first_id("/cookbooks/community-cookbooks/", "id")
print("community cookbook id:", ccb)
if ccb:
    print(hit(f"/cookbooks/community-cookbooks/{ccb}/"))

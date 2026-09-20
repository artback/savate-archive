import json
proposed = json.load(open("proposed_wave2.json"))
print(f"proposed: {len(proposed)}")

def find(key):
    return [p for p in proposed
            if key.lower() in p["_review"]["label"].lower()
            or key.lower() in p["source"].lower()]

for key in ["budim", "kup", "download.php", "world championship",
            "world assaut", "varazdin", "slovenia", "page", "news",
            "classement", "ranking"]:
    hits = find(key)
    print(f"\n== {key}: {len(hits)}")
    for p in hits[:8]:
        r = p["_review"]
        print(f"   {p['slug'][:44]:46} {r['label'][:52]:54} "
              f"b={r['stats']['bouts']:3} p={r['stats']['placings']:3} x{r['copies']}")
import httpx
import re

resp = httpx.get("https://varus.ua/", headers={"User-Agent": "Mozilla/5.0"})
scripts = re.findall(r'src="(https://static.varus.ua/[^"]+\.js)"', resp.text)
found = set()
for s in scripts[:20]:
    try:
        txt = httpx.get(s, timeout=5).text
        for m in re.findall(r'["\'](/api/[^"\']+)["\']', txt):
            found.add(m)
    except Exception as e:
        pass
print("Found API endpoints:", found)

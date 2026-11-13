"""Exporter uniquement des données RSS publiques ; aucune watchlist."""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
news=json.loads((root/'dist/data/news.json').read_text())
health=json.loads((root/'dist/data/health.json').read_text())
items=json.loads((root/'state/items.json').read_text()) if (root/'state/items.json').exists() else []
allowed={'id','title','url','source','code','published','excerpt','language','type','paywall'}
payload={'schema':1,'last_success':news['last_success'],'generated_at':health['checked_at'],'health':health,'items':[{k:v for k,v in x.items() if k in allowed} for x in items]}
(root/'public').mkdir(exist_ok=True)
(root/'public/snapshot.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')))
assert len(payload['items'])<=3000
assert all('watch' not in x for x in payload['items'])

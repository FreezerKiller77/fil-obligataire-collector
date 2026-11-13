"""Collecte concurrente : budgets bornés, robots et sauvegardes atomiques."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import time
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlsplit,urljoin
from urllib.robotparser import RobotFileParser
import feedparser
import httpx
import yaml
from core import UTC,normalize,group_items,iso,dt,classify
ROOT=Path(__file__).resolve().parent
UA='FilObligataire/1.0 (personal RSS reader; respects robots.txt)'
MAX_BYTES=1_490_000

def read_json(path: Path,default: object) -> object:
    try: return json.loads(path.read_text())
    except (OSError,ValueError): return default

def write_json(path: Path,data: object) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
    os.replace(temp,path)

async def request(client: httpx.AsyncClient,url: str) -> httpx.Response:
    last: Exception=RuntimeError('Requête non exécutée')
    for _ in range(2):
        try:
            async with asyncio.timeout(15):
                async with client.stream('GET',url) as response:
                    if not response.is_redirect: response.raise_for_status()
                    body=bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body)>4_000_000: raise ValueError('Flux supérieur à 4 Mo')
                    headers=dict(response.headers)
                    # httpx a déjà décompressé le corps.
                    headers.pop('content-encoding',None)
                    headers.pop('content-length',None)
                    return httpx.Response(response.status_code,headers=headers,content=bytes(body),request=response.request)
        except (httpx.HTTPError,TimeoutError,ValueError) as exc: last=exc
    raise last

async def allowed(client: httpx.AsyncClient,url: str,robots: dict,locks: dict) -> bool:
    p=urlsplit(url)
    origin=f'{p.scheme}://{p.netloc}'
    async with locks.setdefault(origin,asyncio.Lock()):
        if origin not in robots:
            try:
                target=origin+'/robots.txt'
                for _ in range(6):
                    response=await request(client,target)
                    if not response.is_redirect: break
                    target=urljoin(target,response.headers['location'])
                if response.is_redirect: raise ValueError('Redirections robots excessives')
                parser=RobotFileParser()
                parser.parse(response.text.splitlines())
                robots[origin]=parser
            except httpx.HTTPStatusError as exc: robots[origin]=exc.response.status_code==404
            except Exception: robots[origin]=False
    policy=robots[origin]
    return policy if isinstance(policy,bool) else policy.can_fetch(UA,url)

async def fetch_one(source: dict,client: httpx.AsyncClient,semaphore: asyncio.Semaphore,
                    robots: dict,locks: dict,now: datetime,rules: dict,watch: list) -> tuple[list,dict]:
    start=time.monotonic()
    health={k:source[k] for k in ('name','code','url','active','type')}
    health.update(checked_at=iso(now),status='KO',recent=0)
    try:
        async with semaphore:
            async with asyncio.timeout(95):
                url=source['url']
                for _ in range(6):
                    if not await allowed(client,url,robots,locks): raise ValueError('robots.txt interdit ou indisponible')
                    response=await request(client,url)
                    if not response.is_redirect: break
                    url=urljoin(url,response.headers['location'])
                if response.is_redirect: raise ValueError('Trop de redirections')
                parsed=feedparser.parse(response.content)
                if not parsed.get('version'): raise ValueError('Réponse non RSS/Atom')
                items=[x for e in parsed.entries if (x:=normalize(e,source,now,rules,watch))]
                health.update(status='OK' if items else 'VIDE',recent=len(items),detail='Flux valide' if items else 'Aucun article daté de moins de 7 jours')
                return items,health
    except Exception as exc:
        health['detail']=f'{type(exc).__name__}: {str(exc)[:180]}'
        return [],health
    finally: health['duration_s']=round(time.monotonic()-start,2)

async def collect(test_all: bool=False,activate: bool=False) -> None:
    start=time.monotonic()
    now=datetime.now(UTC)
    config=ROOT/'sources.yaml'
    sources=yaml.safe_load(config.read_text())
    rules=yaml.safe_load((ROOT/'rules.yaml').read_text())
    watch=yaml.safe_load((ROOT/'watchlist.yaml').read_text())
    codes=[s['code'] for s in sources]
    if len(set(codes))!=len(codes) or any(not 4<=len(c)<=6 for c in codes): raise ValueError('Codes uniques de 4 à 6 caractères requis')
    selected=[s for s in sources if s['active'] or test_all]
    sem=asyncio.Semaphore(20)
    robots: dict={}
    locks: dict={}
    async with httpx.AsyncClient(headers={'User-Agent':UA},follow_redirects=False) as client:
        tasks=[asyncio.create_task(fetch_one(s,client,sem,robots,locks,now,rules,watch)) for s in selected]
        done,pending=await asyncio.wait(tasks,timeout=145) if tasks else (set(),set())
        for task in pending: task.cancel()
        if pending: await asyncio.gather(*pending,return_exceptions=True)
    results=[]
    for source,task in zip(selected,tasks):
        if task in done: results.append(task.result())
        else: results.append(([],{**{k:source[k] for k in ('name','code','url','active','type')},'status':'KO','recent':0,'checked_at':iso(now),'detail':'Budget global 145 s atteint'}))
    health=[h for _,h in results]
    if activate:
        ok={h['code'] for h in health if h['status']=='OK'}
        for source in sources: source['active']=source['code'] in ok
        config.write_text(yaml.safe_dump(sources,allow_unicode=True,sort_keys=False))
        for h in health: h['active']=h['code'] in ok
    active={s['code'] for s in sources if s['active']}
    fresh=[x for entries,_ in results for x in entries if x['code'] in active]
    state=read_json(ROOT/'state/items.json',[])
    by_code={s['code']:s for s in sources}
    old=[x for x in state if x['code'] in active and dt(x['published'])>=now-timedelta(days=7)]
    for item in old:
        item['source']=by_code[item['code']].get('publisher',item['source'])
        item.update(classify(item['title'],item['excerpt'],by_code[item['code']],rules,watch))
    raw=sorted({x['id']:x for x in [*old,*fresh]}.values(),key=lambda x:x['published'],reverse=True)[:3000]
    valid=any(h['active'] and h['status'] in ('OK','VIDE') for h in health)
    data=ROOT/'dist/data'
    if valid:
        groups=group_items(raw,now,rules['dedup_threshold'])
        payload={'generated_at':iso(now),'last_success':iso(now),'items':groups,'truncated':False}
        while len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode())>MAX_BYTES and groups:
            groups.pop()
            payload['truncated']=True
        keep={m['id'] for g in groups for m in g['members']}
        write_json(ROOT/'state/items.json',[x for x in raw if x['id'] in keep])
        write_json(data/'news.json',payload)
        write_json(data/'latest.json',{**payload,'items':[g for g in groups if dt(g['published'])>=now-timedelta(days=1)]})
    elif not (data/'news.json').exists():
        for name in ('news','latest'): write_json(data/f'{name}.json',{'items':[],'last_success':None})
    checked={h['code'] for h in health}
    for source in sources:
        if source['code'] not in checked:
            health.append({**{k:source[k] for k in ('name','code','url','active','type')},'status':'INACTIF','recent':0,'detail':'Désactivé ; consulter l’audit ou lancer le test complet'})
    duration=round(time.monotonic()-start,2)
    report={'checked_at':iso(now),'duration_s':duration,'all_failed':not valid,'sources':health}
    write_json(data/'health.json',report)
    (ROOT/'docs').mkdir(exist_ok=True)
    (ROOT/'docs/sources.md').write_text('# Dernier contrôle des sources\n\nUTC : '+iso(now)+'\n\n| Source | Flux | État | Articles <7j | Diagnostic |\n|---|---|---|---:|---|\n'+'\n'.join(f"| {h['name']} | {h['url']} | {h['status']} | {h['recent']} | {h.get('detail','')} |" for h in health))
    print(json.dumps({'duration_s':duration,'active':len(active),'ok':sum(h['status']=='OK' and h['active'] for h in health),'new_items':len(fresh),'all_failed':not valid}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--test-all',action='store_true')
    parser.add_argument('--activate-verified',action='store_true')
    args=parser.parse_args()
    asyncio.run(collect(args.test_all or args.activate_verified,args.activate_verified))

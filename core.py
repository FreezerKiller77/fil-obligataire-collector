"""Normalisation et règles déterministes sans accès réseau."""
from __future__ import annotations
import calendar
import hashlib
import html
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from rapidfuzz.fuzz import ratio
UTC = timezone.utc

class PlainText(HTMLParser):
    """Ignore le balisage et le contenu script/style."""
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0
    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ('script', 'style'): self.hidden += 1
    def handle_endtag(self, tag: str) -> None:
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden-1)
    def handle_data(self, data: str) -> None:
        if not self.hidden: self.parts.append(data)

def clean(value: str) -> str:
    p = PlainText()
    p.feed(str(value))
    return ' '.join(html.unescape(' '.join(p.parts)).split())

def fold(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))

def mention(text: str, alias: str) -> bool:
    return bool(alias and re.search(r'(?<!\w)'+re.escape(fold(alias))+r'(?!\w)', fold(text)))

def canonical(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username:
        raise ValueError('URL article non HTTP(S)')
    pairs = [(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid','mc_cid','mc_eid')]
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path or '/',urlencode(sorted(pairs)),''))

def iso(date: datetime) -> str:
    return date.astimezone(UTC).isoformat().replace('+00:00','Z')

def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(UTC)

def classify(title: str, excerpt: str, source: dict, rules: dict, watch: list[dict]) -> dict:
    text = fold(title+' '+excerpt)
    categories = {source['category']}
    tags: list[str] = []
    weight = 0
    for category, spec in rules['categories'].items():
        hits = [term for term in spec['terms'] if mention(text,term)]
        patterns = [p for p in spec.get('regex',[]) if re.search(p,text)]
        if hits or patterns:
            categories.add(category)
            weight += spec.get('weight',0)
            tags.extend(hits[:2])
    critical = [term for term in rules['critical'] if mention(text,term)]
    weight += min(35,len(critical)*7)
    names = [w['name'] for w in watch if any(mention(text,a) for a in [w['name'],*w.get('aliases',[]),w.get('ticker','')])]
    if re.search(r'\bUS\b|\bU\.S\.',title+' '+excerpt): categories.add('US')
    decision = source['type']=='primaire' and source['code'] in ('BCEPR','FEDMP','FEDPR') and bool(re.search(r'monetary policy decisions|federal reserve issues fomc statement|decisions de politique monetaire',fold(title)))
    if decision: categories.add('BC')
    return {'categories':sorted(categories-{'AUTRES'} if len(categories)>1 else categories),
            'tags':list(dict.fromkeys(tags))[:6], 'watch':names,
            'base_score':min(85,{'primaire':28,'presse':18,'agrégé':10}[source['type']]+weight),
            'policy_decision':decision}

def normalize(entry: dict, source: dict, now: datetime, rules: dict, watch: list[dict]) -> dict | None:
    stamp = entry.get('published_parsed') or entry.get('updated_parsed')
    if not stamp: return None
    published = datetime.fromtimestamp(calendar.timegm(stamp),UTC)
    if not now-timedelta(days=7)<=published<=now: return None
    try: url = canonical(entry.get('link',''))
    except ValueError: return None
    title = clean(entry.get('title',''))
    if not title: return None
    publisher = clean(entry.get('source',{}).get('title','')) if source['type']=='agrégé' else ''
    if publisher and title.endswith(' - '+publisher): title=title[:-len(publisher)-3].rstrip()
    excerpt = clean(entry.get('summary',''))[:280]
    item = {'id':hashlib.sha256(url.encode()).hexdigest()[:24], 'url':url, 'title':title[:500],
            'source':publisher or source.get('publisher',source['name']), 'code':source['code'],
            'published':iso(published),'excerpt':excerpt,'language':source['language'],
            'type':source['type'],'paywall':source['paywall']}
    return item | classify(title,excerpt,source,rules,watch)

def event_key(item: dict) -> str | None:
    """Même banque, même jour, mouvement et amplitude identiques."""
    text = fold(item['title']+' '+item.get('excerpt',''))
    bank = 'ECB' if re.search(r'\becb\b|\bbce\b|european central bank|banque centrale europeenne',text) else 'FED' if re.search(r'\bfed\b|federal reserve|\bfomc\b',text) else None
    action = 'cut' if re.search(r'\bcut\w*|\blower\w*|\bbaisse\w*|\breduit\w*',text) else 'hike' if re.search(r'\bhik\w*|\brais\w*|\breleve\w*|\bhausse\w*',text) else None
    size = re.search(r'\b(25|50|75|100)\s*(?:bp|basis|points? de base)',text)
    if bank and action and size and re.search(r'\brate|\btaux',text):
        return f"{bank}:{item['published'][:10]}:{action}:{size[1]}"
    return None

def same_story(a: dict,b: dict,threshold: int) -> bool:
    if abs((dt(a['published'])-dt(b['published'])).total_seconds())>86400: return False
    ea,eb=event_key(a),event_key(b)
    if ea and ea==eb: return True
    ta,tb=fold(a['title']),fold(b['title'])
    if re.findall(r'\d+(?:[.,]\d+)?',ta)!=re.findall(r'\d+(?:[.,]\d+)?',tb): return False
    return ratio(ta,tb)>=threshold

def group_items(items: list[dict],now: datetime,threshold: int=88) -> list[dict]:
    unique: dict[str,dict] = {}
    for item in sorted(items,key=lambda x:(x['type']!='primaire',x['published'])):
        if now-timedelta(days=7)<=dt(item['published'])<=now: unique.setdefault(item['id'],item)
    groups: list[list[dict]] = []
    for item in sorted(unique.values(),key=lambda x:x['published'],reverse=True):
        found=next((g for g in groups if same_story(item,g[0],threshold)),None)
        if found is None: groups.append([item])
        else: found.append(item)
    output=[]
    for group in groups:
        group.sort(key=lambda x:(x['type']!='primaire',x['published']))
        first=dict(group[0])
        age=(now-dt(first['published'])).total_seconds()/3600
        publishers=len({x['source'].casefold() for x in group})
        score=min(100,max(x['base_score'] for x in group)+min(15,(publishers-1)*5)+max(0,round(15-age*2)))
        first.update(score=score,urgent=(score>=80 and age<1) or any(x['policy_decision'] for x in group),
                     categories=sorted({c for x in group for c in x['categories']}),
                     watch=sorted({w for x in group for w in x['watch']}),count=publishers,
                     members=[{k:x[k] for k in ('id','title','url','source','code','published','paywall','type')} for x in group])
        if score>=40 or first['policy_decision']: first['categories']=sorted(set(first['categories'])|{'TOP'})
        output.append(first)
    return sorted(output,key=lambda x:x['published'],reverse=True)

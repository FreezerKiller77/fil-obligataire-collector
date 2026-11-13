"""Vérifications métier, sécurité et titres réels conservés de l'audit."""
import json
from datetime import datetime,timedelta
from pathlib import Path
import yaml
from core import UTC,clean,canonical,normalize,classify,group_items,iso,mention
ROOT=Path(__file__).resolve().parent
RULES=yaml.safe_load((ROOT/'rules.yaml').read_text())
WATCH=[{'name':'Altice','aliases':['Altice France','SFR'],'ticker':'ATC'}]
NOW=datetime(2026,11,12,12,tzinfo=UTC)
SOURCE={'name':'BCE','publisher':'BCE','code':'BCEPR','type':'primaire','category':'BC','language':'EN','paywall':False}

def entry(title='Monetary policy decisions',date=NOW-timedelta(minutes=20),url='https://www.ecb.europa.eu/news?a=1&utm_source=x'):
    return {'title':title,'summary':'<b>The ECB cuts rates by 25 basis points.</b>','link':url,'published_parsed':date.utctimetuple()}

def item(title,code,source_type='presse',minutes=20):
    source={**SOURCE,'code':code,'name':code,'publisher':code,'type':source_type}
    return normalize(entry(title,NOW-timedelta(minutes=minutes),'https://example.org/'+code),source,NOW,RULES,WATCH)

def test_html_security():
    assert clean('<b>Inflation</b><script>alert(1)</script> &amp; taux')=='Inflation & taux'

def test_tracking_stable_id():
    assert canonical('https://example.com/a?utm_source=x&b=2#section')=='https://example.com/a?b=2'
    a=normalize(entry(),SOURCE,NOW,RULES,WATCH)
    b=normalize(entry(url='https://www.ecb.europa.eu/news?a=1'),SOURCE,NOW,RULES,WATCH)
    assert a['id']==b['id']

def test_dates_and_unsafe_url():
    for date in [NOW+timedelta(seconds=1),NOW-timedelta(days=8)]:
        assert normalize(entry(date=date),SOURCE,NOW,RULES,WATCH) is None
    e=entry();del e['published_parsed']
    assert normalize(e,SOURCE,NOW,RULES,WATCH) is None
    assert normalize(entry(url='javascript:alert(1)'),SOURCE,NOW,RULES,WATCH) is None

def test_excerpt_and_decision():
    e=entry();e['summary']='A'*500
    x=normalize(e,SOURCE,NOW,RULES,WATCH)
    assert len(x['excerpt'])==280 and x['policy_decision']
    assert group_items([x],NOW)[0]['urgent']

def test_watch_whole_words():
    assert mention('Altice France annonce une émission','Altice')
    assert not mention('Alticement est un mot fictif','Altice')
    assert not mention('Credit information','FR')
    assert classify('Altice restructuring','',SOURCE,RULES,WATCH)['watch']==['Altice']

def test_credit_macro_classification():
    x=classify('Fitch downgrades Altice France; negative outlook','',SOURCE,RULES,WATCH)
    assert 'NOTES' in x['categories'] and 'Altice' in x['watch']
    assert 'MACRO' in classify('Consumer Price Index Summary','CPI inflation',SOURCE,RULES,WATCH)['categories']

def test_bce_and_five_media():
    titles=['ECB cuts rates by 25 basis points','BCE baisse ses taux de 25 points de base','European Central Bank cuts interest rates by 25 basis points','ECB delivers 25 bp rate cut','ECB cuts key rates by 25 basis points']
    media=[item(t,f'MED{i}',minutes=25+i) for i,t in enumerate(titles)]
    groups=group_items([*media,normalize(entry(),SOURCE,NOW,RULES,WATCH)],NOW)
    assert len(groups)==1 and groups[0]['code']=='BCEPR' and groups[0]['count']==6

def test_distinct_numbers_and_dates():
    a=item('ECB cuts rates by 25 basis points','AAAA')
    b=item('ECB cuts rates by 50 basis points','BBBB');b['excerpt']=''
    assert len(group_items([a,b],NOW))==2
    b={**a,'id':'different','published':iso(NOW-timedelta(days=2))}
    assert len(group_items([a,b],NOW))==2

def test_count_publishers():
    a=item('ECB cuts rates by 25 basis points','AAAA')
    b={**a,'id':'different','url':'https://example.org/b'}
    assert group_items([a,b,a],NOW)[0]['count']==1

def test_real_titles():
    fixtures=json.loads((ROOT/'real_titles.json').read_text())
    assert len(fixtures)>=5
    for sample in fixtures:
        x=normalize(entry(title=sample['title'],url=sample['url']),SOURCE,NOW,RULES,WATCH)
        assert x and x['title']==clean(sample['title'])[:500]
        assert len(group_items([x,x],NOW))==1

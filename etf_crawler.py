import requests
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import time

ETF_LIST = {
    '00981A':'統一台灣動能主動ETF',
    '00992A':'野村台灣高股息主動ETF',
    '00987A':'國泰台灣領航主動ETF',
    '00991A':'元大台灣高息動能主動ETF',
    '00985A':'群益台灣精選高息主動ETF',
    '00980A':'富邦台灣主動優選ETF',
    '00984A':'中信台灣智慧主動ETF',
    '00993A':'兆豐台灣晶圓主動ETF',
    '00994A':'復華台灣科技優息主動ETF',
    '00995A':'永豐台灣主動息收ETF',
}
HEADERS = {
    'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language':'zh-TW,zh;q=0.9',
}
DATA_DIR = 'data'
HOLDINGS_FILE = os.path.join(DATA_DIR, 'holdings.json')
HISTORY_FILE  = os.path.join(DATA_DIR, 'history.json')
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_etf_holdings(etf_code):
    try:
        r = requests.get('https://www.twse.com.tw/fund/ETF_portfolio',
                         params={'stockNo': etf_code, 'response': 'json'},
                         headers=HEADERS, timeout=15)
        data = r.json()
        if data.get('stat') == 'OK' and data.get('data'):
            result = []
            for i, row in enumerate(data['data'][:10], 1):
                result.append({
                    'rank': i, 'code': row[0].strip(), 'name': row[1].strip(),
                    'shares': row[2].replace(',',''), 'market_value': row[3].replace(',',''),
                    'weight': float(row[4].replace(',','')) if row[4].strip() else 0,
                })
            return result
    except Exception as e:
        print(f'  TWSE失敗 {etf_code}: {e}')
    try:
        r2 = requests.post('https://mops.twse.com.tw/mops/web/ajax_t05st09',
                           data={'step':'1','firstin':'1','co_id':etf_code},
                           headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r2.text, 'lxml')
        rows = soup.select('table tr')[1:11]
        result = []
        for i, row in enumerate(rows, 1):
            cells = [td.get_text(strip=True) for td in row.select('td')]
            if len(cells) >= 4:
                result.append({
                    'rank': i, 'code': cells[0], 'name': cells[1],
                    'shares': cells[2].replace(',',''), 'market_value': cells[3].replace(',',''),
                    'weight': float(cells[4].replace(',','').replace('%','')) if len(cells)>4 and cells[4].strip() else 0,
                })
        if result:
            return result
    except Exception as e:
        print(f'  MOPS失敗 {etf_code}: {e}')
    return []

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def build_output(today_data, yesterday_data):
    stock_map = {}
    for etf_code, holdings in today_data.items():
        etf_name = ETF_LIST.get(etf_code, etf_code)
        prev = {h['code']: h for h in yesterday_data.get(etf_code, [])}
        today_codes = {h['code'] for h in holdings}
        for h in holdings:
            sc = h['code']
            w_today = h['weight']
            w_prev = prev[sc]['weight'] if sc in prev else None
            is_new = sc not in prev
            wchg = round(w_today - w_prev, 2) if w_prev is not None else None
            rk = h['rank']
            rank_label = 'TOP3' if rk<=3 else 'TOP5' if rk<=5 else 'TOP10' if rk<=10 else ''
            if sc not in stock_map:
                stock_map[sc] = {'code':sc,'name':h['name'],'price':None,'chg':None,
                                 'etfs':[],'total_wchg':0,'cat':'new' if is_new else 'buy'}
            stock_map[sc]['etfs'].append({'etf':etf_code,'etf_name':etf_name,
                'action':'new-in' if is_new else 'add','rank':rank_label,'wchg':wchg,'weight':w_today})
            if wchg is not None:
                stock_map[sc]['total_wchg'] = round(stock_map[sc]['total_wchg']+wchg, 2)
        for sc, h in prev.items():
            if sc not in today_codes:
                if sc not in stock_map:
                    stock_map[sc] = {'code':sc,'name':h['name'],'price':None,'chg':None,
                                     'etfs':[],'total_wchg':0,'cat':'sell'}
                stock_map[sc]['etfs'].append({'etf':etf_code,'etf_name':etf_name,
                    'action':'removed','rank':'','wchg':round(-h['weight'],2),'weight':0})
                stock_map[sc]['total_wchg'] = round(stock_map[sc]['total_wchg']-h['weight'], 2)
                stock_map[sc]['cat'] = 'sell'
    buy, new_in, sell = [], [], []
    for s in stock_map.values():
        if s['cat']=='sell': sell.append(s)
        elif s['cat']=='new' or len(s['etfs'])==1: new_in.append(s)
        else: buy.append(s)
    buy.sort(key=lambda s:(-len(s['etfs']),-abs(s['total_wchg'])))
    new_in.sort(key=lambda s:(-len(s['etfs']),-abs(s['total_wchg'])))
    sell.sort(key=lambda s:s['total_wchg'])
    return buy[:15], new_in[:12], sell[:8]

def main():
    today = datetime.now().strftime('%Y-%m-%d')
    print(f'\n=== ETF爬蟲 {today} ===')
    history = load_history()
    today_data = {}
    for etf_code in ETF_LIST:
        print(f'抓取 {etf_code} ...')
        holdings = fetch_etf_holdings(etf_code)
        if holdings:
            today_data[etf_code] = holdings
            print(f'  成功 {len(holdings)} 筆')
        else:
            print(f'  無資料')
        time.sleep(1)
    history[today] = today_data
    save_history(history)
    dates = sorted(history.keys())
    yesterday = dates[-2] if len(dates)>=2 else dates[0]
    yesterday_data = history.get(yesterday, {})
    print(f'比較基準: {yesterday}')
    buy, new_in, sell = build_output(today_data, yesterday_data)
    output = {'generated_at':today,'compare_date':yesterday,
              'etf_count':len(today_data),'buy':buy,'new':new_in,'sell':sell}
    with open(HOLDINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n完成！買進:{len(buy)} 新進:{len(new_in)} 減碼:{len(sell)}')
    print(f'資料已寫入 {HOLDINGS_FILE}')

if __name__ == '__main__':
    main()

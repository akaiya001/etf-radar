import requests
import json
import os
from datetime import datetime
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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.twse.com.tw/',
    'Origin': 'https://www.twse.com.tw',
}

DATA_DIR = 'data'
HOLDINGS_FILE = os.path.join(DATA_DIR, 'holdings.json')
HISTORY_FILE  = os.path.join(DATA_DIR, 'history.json')
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_twse_openapi(etf_code):
    """TWSE OpenAPI - 不需要特殊權限"""
    url = 'https://openapi.twse.com.tw/v1/ETF/DAM_ETFStockInfo'
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            all_data = r.json()
            # 篩選該ETF的資料
            etf_data = [row for row in all_data if row.get('ETFid', '').strip() == etf_code]
            if etf_data:
                result = []
                for i, row in enumerate(etf_data[:10], 1):
                    try:
                        weight = float(row.get('Percentage', '0').replace(',', '').replace('%', ''))
                    except:
                        weight = 0
                    result.append({
                        'rank': i,
                        'code': row.get('StockID', '').strip(),
                        'name': row.get('StockName', '').strip(),
                        'shares': row.get('Shares', '0').replace(',', ''),
                        'market_value': row.get('Amount', '0').replace(',', ''),
                        'weight': weight,
                    })
                result.sort(key=lambda x: x['weight'], reverse=True)
                for i, r in enumerate(result, 1):
                    r['rank'] = i
                print(f'  TWSE OpenAPI 成功: {len(result)} 筆')
                return result
    except Exception as e:
        print(f'  TWSE OpenAPI 失敗: {e}')
    return []

def fetch_fund_api(etf_code):
    """基金資訊網 API"""
    url = 'https://www.fundclear.com.tw/SmWeb/fund.do'
    params = {'action': 'qryETFCompInfo', 'etfid': etf_code}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if r.status_code == 200 and r.text.strip():
            data = r.json()
            items = data.get('data', data.get('list', []))
            if items:
                result = []
                for i, row in enumerate(items[:10], 1):
                    try:
                        weight = float(str(row.get('pct', row.get('percentage', 0))).replace('%','').replace(',',''))
                    except:
                        weight = 0
                    result.append({
                        'rank': i,
                        'code': str(row.get('stockId', row.get('stockCode', ''))).strip(),
                        'name': str(row.get('stockName', '')).strip(),
                        'shares': str(row.get('shares', '0')).replace(',', ''),
                        'market_value': str(row.get('amount', '0')).replace(',', ''),
                        'weight': weight,
                    })
                if result:
                    print(f'  基金資訊網 成功: {len(result)} 筆')
                    return result
    except Exception as e:
        print(f'  基金資訊網 失敗: {e}')
    return []

def fetch_mops_api(etf_code):
    """公開資訊觀測站"""
    now = datetime.now()
    year = now.year - 1911
    url = f'https://mops.twse.com.tw/mops/web/t146sb03'
    params = {
        'firstin': '1',
        'TYPEK': 'sii',
        'co_id': etf_code,
        'year': str(year),
        'month': str(now.month).zfill(2),
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if r.status_code == 200 and len(r.text) > 500:
            from html.parser import HTMLParser
            class TDParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.rows = []
                    self.current_row = []
                    self.in_td = False
                def handle_starttag(self, tag, attrs):
                    if tag == 'tr': self.current_row = []
                    if tag == 'td': self.in_td = True
                def handle_endtag(self, tag):
                    if tag == 'td': self.in_td = False
                    if tag == 'tr' and self.current_row:
                        self.rows.append(self.current_row[:])
                def handle_data(self, data):
                    if self.in_td: self.current_row.append(data.strip())

            parser = TDParser()
            parser.feed(r.text)
            result = []
            for i, cells in enumerate(parser.rows[1:11], 1):
                if len(cells) >= 4 and cells[0]:
                    try:
                        weight = float(cells[4].replace(',','').replace('%','')) if len(cells) > 4 else 0
                    except:
                        weight = 0
                    result.append({
                        'rank': i,
                        'code': cells[0],
                        'name': cells[1] if len(cells) > 1 else '',
                        'shares': cells[2].replace(',','') if len(cells) > 2 else '0',
                        'market_value': cells[3].replace(',','') if len(cells) > 3 else '0',
                        'weight': weight,
                    })
            if result:
                print(f'  MOPS 成功: {len(result)} 筆')
                return result
    except Exception as e:
        print(f'  MOPS 失敗: {e}')
    return []

def fetch_etf_holdings(etf_code):
    for fn in [fetch_twse_openapi, fetch_fund_api, fetch_mops_api]:
        result = fn(etf_code)
        if result:
            return result
        time.sleep(1)
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
            if not sc: continue
            w_today = h['weight']
            w_prev = prev[sc]['weight'] if sc in prev else None
            is_new = sc not in prev
            wchg = round(w_today - w_prev, 2) if w_prev is not None else None
            rk = h['rank']
            rank_label = 'TOP3' if rk <= 3 else 'TOP5' if rk <= 5 else 'TOP10' if rk <= 10 else ''
            if sc not in stock_map:
                stock_map[sc] = {'code': sc, 'name': h['name'], 'price': None, 'chg': None,
                                 'etfs': [], 'total_wchg': 0, 'cat': 'new' if is_new else 'buy'}
            stock_map[sc]['etfs'].append({
                'etf': etf_code, 'etf_name': etf_name,
                'action': 'new-in' if is_new else 'add',
                'rank': rank_label, 'wchg': wchg, 'weight': w_today
            })
            if wchg is not None:
                stock_map[sc]['total_wchg'] = round(stock_map[sc]['total_wchg'] + wchg, 2)
        for sc, h in prev.items():
            if sc not in today_codes:
                if sc not in stock_map:
                    stock_map[sc] = {'code': sc, 'name': h['name'], 'price': None, 'chg': None,
                                     'etfs': [], 'total_wchg': 0, 'cat': 'sell'}
                stock_map[sc]['etfs'].append({
                    'etf': etf_code, 'etf_name': etf_name,
                    'action': 'removed', 'rank': '',
                    'wchg': round(-h['weight'], 2), 'weight': 0
                })
                stock_map[sc]['total_wchg'] = round(stock_map[sc]['total_wchg'] - h['weight'], 2)
                stock_map[sc]['cat'] = 'sell'

    buy, new_in, sell = [], [], []
    for s in stock_map.values():
        if s['cat'] == 'sell': sell.append(s)
        elif s['cat'] == 'new' or len(s['etfs']) == 1: new_in.append(s)
        else: buy.append(s)
    buy.sort(key=lambda s: (-len(s['etfs']), -abs(s['total_wchg'])))
    new_in.sort(key=lambda s: (-len(s['etfs']), -abs(s['total_wchg'])))
    sell.sort(key=lambda s: s['total_wchg'])
    return buy[:15], new_in[:12], sell[:8]

def main():
    today = datetime.now().strftime('%Y-%m-%d')
    print(f'\n=== ETF爬蟲 {today} ===')
    history = load_history()
    today_data = {}
    for etf_code in ETF_LIST:
        print(f'\n抓取 {etf_code} {ETF_LIST[etf_code]}...')
        holdings = fetch_etf_holdings(etf_code)
        if holdings:
            today_data[etf_code] = holdings
        else:
            print(f'  ⚠ 無資料')
        time.sleep(2)

    print(f'\n成功抓取: {len(today_data)}/{len(ETF_LIST)} 支ETF')
    history[today] = today_data
    save_history(history)

    dates = sorted(history.keys())
    yesterday = dates[-2] if len(dates) >= 2 else dates[0]
    yesterday_data = history.get(yesterday, {})
    print(f'比較基準: {yesterday}')

    buy, new_in, sell = build_output(today_data, yesterday_data)
    output = {
        'generated_at': today,
        'compare_date': yesterday,
        'etf_count': len(today_data),
        'buy': buy, 'new': new_in, 'sell': sell,
    }
    with open(HOLDINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n完成！買進:{len(buy)} 新進:{len(new_in)} 減碼:{len(sell)}')
    print(f'資料寫入 {HOLDINGS_FILE}')

if __name__ == '__main__':
    main()

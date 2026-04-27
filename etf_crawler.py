import requests
import json
import os
import re
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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.etfinfo.tw/',
}

DATA_DIR = 'data'
HOLDINGS_FILE = os.path.join(DATA_DIR, 'holdings.json')
HISTORY_FILE  = os.path.join(DATA_DIR, 'history.json')
os.makedirs(DATA_DIR, exist_ok=True)


def fetch_etfinfo(etf_code):
    """從 etfinfo.tw 爬取持股明細（靜態HTML，不擋海外IP）"""
    all_holdings = []
    page = 1

    while True:
        url = f'https://www.etfinfo.tw/etf/{etf_code}/holdings'
        if page > 1:
            url += f'?page={page}'

        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'lxml')

            # 找持股表格
            table = soup.find('table')
            if not table:
                break

            rows = table.find_all('tr')[1:]  # 跳過 header
            if not rows:
                break

            found_any = False
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 3:
                    continue

                # 第1格：代號 + 名稱
                cell0_text = cells[0].get_text(separator=' ', strip=True)
                code_match = re.search(r'(\d{4,5}[A-Z]?)', cell0_text)
                if not code_match:
                    continue
                code = code_match.group(1)
                name = re.sub(r'^\d+\s*', '', cell0_text).strip()

                # 第2格：漲跌幅 + 收盤價
                cell1_text = cells[1].get_text(separator=' ', strip=True)
                price_match = re.search(r'(\d[\d,]*\.?\d*)\s*$', cell1_text)
                price = float(price_match.group(1).replace(',','')) if price_match else None
                chg_match = re.search(r'([+-]?\d+\.?\d*)%', cell1_text)
                chg = float(chg_match.group(1)) if chg_match else None

                # 第3格：權重 + 股數
                cell2_text = cells[2].get_text(separator=' ', strip=True)
                weight_match = re.search(r'(\d+\.?\d*)%', cell2_text)
                weight = float(weight_match.group(1)) if weight_match else 0
                shares_match = re.search(r'([\d,]+)\s*$', cell2_text)
                shares = shares_match.group(1).replace(',','') if shares_match else '0'

                all_holdings.append({
                    'code': code,
                    'name': name,
                    'price': price,
                    'chg': chg,
                    'weight': weight,
                    'shares': shares,
                })
                found_any = True

            if not found_any:
                break

            # 判斷是否有下一頁
            next_link = soup.find('a', string=re.compile('下一頁|next', re.I))
            if not next_link or 'disabled' in next_link.get('class', []):
                break

            page += 1
            time.sleep(1)

        except Exception as e:
            print(f'  etfinfo.tw 第{page}頁失敗: {e}')
            break

    # 按權重排序，加上排名
    all_holdings.sort(key=lambda x: x['weight'], reverse=True)
    for i, h in enumerate(all_holdings, 1):
        h['rank'] = i

    return all_holdings[:30]  # 最多取前30筆


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
            if not sc:
                continue
            w_today = h['weight']
            w_prev = prev[sc]['weight'] if sc in prev else None
            is_new = sc not in prev
            wchg = round(w_today - w_prev, 2) if w_prev is not None else None

            rk = h['rank']
            rank_label = 'TOP3' if rk <= 3 else 'TOP5' if rk <= 5 else 'TOP10' if rk <= 10 else ''

            if sc not in stock_map:
                stock_map[sc] = {
                    'code': sc,
                    'name': h['name'],
                    'price': h.get('price'),
                    'chg': h.get('chg'),
                    'etfs': [],
                    'total_wchg': 0,
                    'cat': 'new' if is_new else 'buy',
                }
            stock_map[sc]['etfs'].append({
                'etf': etf_code,
                'etf_name': etf_name,
                'action': 'new-in' if is_new else 'add',
                'rank': rank_label,
                'wchg': wchg,
                'weight': w_today,
            })
            if wchg is not None:
                stock_map[sc]['total_wchg'] = round(stock_map[sc]['total_wchg'] + wchg, 2)

        # 全剔除
        for sc, h in prev.items():
            if sc not in today_codes:
                if sc not in stock_map:
                    stock_map[sc] = {
                        'code': sc,
                        'name': h['name'],
                        'price': None,
                        'chg': None,
                        'etfs': [],
                        'total_wchg': 0,
                        'cat': 'sell',
                    }
                stock_map[sc]['etfs'].append({
                    'etf': etf_code,
                    'etf_name': etf_name,
                    'action': 'removed',
                    'rank': '',
                    'wchg': round(-h['weight'], 2),
                    'weight': 0,
                })
                stock_map[sc]['total_wchg'] = round(stock_map[sc]['total_wchg'] - h['weight'], 2)
                stock_map[sc]['cat'] = 'sell'

    buy, new_in, sell = [], [], []
    for s in stock_map.values():
        if s['cat'] == 'sell':
            sell.append(s)
        elif s['cat'] == 'new' or len(s['etfs']) == 1:
            new_in.append(s)
        else:
            buy.append(s)

    buy.sort(key=lambda s: (-len(s['etfs']), -abs(s['total_wchg'])))
    new_in.sort(key=lambda s: (-len(s['etfs']), -abs(s['total_wchg'])))
    sell.sort(key=lambda s: s['total_wchg'])

    return buy[:15], new_in[:12], sell[:8]


def main():
    today = datetime.now().strftime('%Y-%m-%d')
    print(f'\n=== ETF爬蟲 {today} ===')
    print(f'資料來源: etfinfo.tw\n')

    history = load_history()
    today_data = {}

    for etf_code, etf_name in ETF_LIST.items():
        print(f'抓取 {etf_code} {etf_name}...')
        holdings = fetch_etfinfo(etf_code)
        if holdings:
            today_data[etf_code] = holdings
            print(f'  ✓ 成功 {len(holdings)} 筆，前3名: ' +
                  ', '.join(f"{h['name']}({h['weight']}%)" for h in holdings[:3]))
        else:
            print(f'  ✗ 無資料')
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
        'buy': buy,
        'new': new_in,
        'sell': sell,
    }

    with open(HOLDINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\n完成！買進:{len(buy)} 新進:{len(new_in)} 減碼:{len(sell)}')
    print(f'資料寫入 {HOLDINGS_FILE}')


if __name__ == '__main__':
    main()

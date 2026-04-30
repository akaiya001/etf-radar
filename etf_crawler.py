"""
台灣主動ETF完整持股爬蟲 v5
資料來源：etf.idigi.tw（靜態HTML，完整資料）
"""

import requests, json, os, re
from datetime import datetime
from bs4 import BeautifulSoup
import time

ETF_LIST = {
    '00981A': '統一台灣動能主動ETF',
    '00992A': '野村台灣高股息主動ETF',
    '00987A': '國泰台灣領航主動ETF',
    '00991A': '元大台灣高息動能主動ETF',
    '00985A': '群益台灣精選高息主動ETF',
    '00980A': '富邦台灣主動優選ETF',
    '00984A': '中信台灣智慧主動ETF',
    '00993A': '兆豐台灣晶圓主動ETF',
    '00994A': '復華台灣科技優息主動ETF',
    '00995A': '永豐台灣主動息收ETF',
}

INDUSTRY_MAP = {
    '2330':'半導體','2454':'半導體','2303':'半導體','2344':'半導體',
    '2379':'半導體','2408':'半導體','3081':'半導體','2404':'半導體',
    '3711':'半導體封測',
    '2317':'電子製造','2382':'電子製造','2357':'電子製造',
    '2308':'電子零組件','2395':'電子零組件','2301':'電子零組件',
    '3665':'電子零組件','2388':'電子零組件','2327':'被動元件',
    '3034':'IC設計','6770':'IC設計','8299':'IC設計','5274':'IC設計',
    '3008':'光學',
    '2383':'PCB材料','3037':'PCB','2368':'PCB','8046':'PCB',
    '2376':'主機板','3653':'散熱','3017':'散熱','8996':'散熱','6415':'散熱',
    '6669':'伺服器','2345':'網通',
    '4904':'電信','2412':'電信',
    '2881':'金融','2882':'金融','2886':'金融','2891':'金融',
    '2892':'金融','5880':'金融','5871':'租賃金融',
    '1301':'石化','1303':'石化','6505':'石化','1326':'化工',
    '2002':'鋼鐵','2207':'汽車','9910':'汽車零件',
    '1216':'食品','2912':'零售',
    '3105':'砷化鎵','1590':'氣動元件',
    '6274':'PCB材料','6223':'半導體設備','6510':'半導體設備',
    '2313':'PCB','2337':'半導體','2059':'電子零組件',
    '2360':'量測','7769':'工業自動化','6805':'連接器',
    '6515':'連接器','3443':'IC設計','3189':'PCB',
}

STOCK_MAPPING_FILE = '/home/akaiyaab/backtest_data/stock_mapping.csv'

def load_stock_names():
    """從本地 stock_mapping.csv 載入股票代號→名稱對照表"""
    name_map = {}
    try:
        with open(STOCK_MAPPING_FILE, encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('symbol'):
                    continue
                parts = line.split(',', 1)
                if len(parts) == 2:
                    code = parts[0].strip()
                    name = parts[1].strip()
                    name_map[code] = name
        print(f'  ✓ 載入股名對照表：{len(name_map)} 筆')
    except Exception as e:
        print(f'  ⚠ 股名對照表載入失敗：{e}')
    return name_map

STOCK_NAME_MAP = load_stock_names()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*',
    'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
    'Referer': 'https://etf.idigi.tw/',
}

# ── 股票名稱對照表 ────────────────────────────
STOCK_MAPPING_FILE = '/home/akaiyaab/backtest_data/stock_mapping.csv'

def load_stock_mapping():
    """載入本地股票代號→名稱對照表"""
    mapping = {}
    try:
        with open(STOCK_MAPPING_FILE, encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('symbol'):
                    continue
                parts = line.split(',', 1)
                if len(parts) == 2:
                    code, name = parts[0].strip(), parts[1].strip()
                    mapping[code] = name
        print(f'  ✓ 載入股票名稱對照表：{len(mapping)} 筆')
    except Exception as e:
        print(f'  ⚠ 股票名稱對照表載入失敗：{e}')
    return mapping

STOCK_NAMES = load_stock_mapping()

BASE_URL   = 'https://etf.idigi.tw'
DATA_DIR   = '/home/akaiyaab/backtest_data/ETF 持股變化'
GITHUB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
HOLDINGS_FILE = os.path.join(DATA_DIR, 'holdings.json')
HISTORY_FILE  = os.path.join(DATA_DIR, 'history.json')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(GITHUB_DIR, exist_ok=True)


# ══════════════════════════════════════════════
# 1. 從 idigi.tw 主頁抓所有ETF當日持股
# ══════════════════════════════════════════════
def fetch_idigi_main(date_str=None):
    """
    抓取 idigi.tw 主頁，取得所有ETF持股彙整資料
    回傳 dict: {etf_code: [holdings]}  及  stock_list
    """
    url = BASE_URL + '/etf'
    if date_str:
        url += f'?date={date_str}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f'  idigi主頁錯誤：{e}')
        return ''


def parse_idigi_main(html):
    """
    解析 idigi.tw 主頁 HTML
    回傳 stock_map: {stock_code: {name, etfs:[{etf, rank, weight, action, shares_chg}]}}
    """
    soup = BeautifulSoup(html, 'lxml')
    stock_map = {}

    # 每個個股區塊
    # 結構：每個 stock 有 code、name、各ETF的 TOP排名、weight、action
    stock_sections = soup.find_all('a', href=re.compile(r'/etf/stock/\d+'))
    seen = set()

    for link in stock_sections:
        href = link.get('href', '')
        m = re.search(r'/etf/stock/(\d+[A-Z]?)', href)
        if not m:
            continue
        code = m.group(1)
        if code in seen:
            continue
        seen.add(code)

        # 往上找包含所有ETF資訊的容器
        container = link.find_parent('tr') or link.find_parent('li') or link.find_parent('div')
        if not container:
            continue

        text = container.get_text(separator='|', strip=True)
        # 抓個股名稱
        name_tag = container.find(string=re.compile(r'[\u4e00-\u9fff]{2,}'))
        name = name_tag.strip() if name_tag else ''

        stock_map[code] = {
            'code': code,
            'name': name,
            'industry': INDUSTRY_MAP.get(code, '其他'),
            'price': None,
            'chg_pct': None,
            'etfs': [],
            'raw_text': text,
        }

    return stock_map


# ══════════════════════════════════════════════
# 2. 從 idigi.tw 個股頁面抓完整歷史持股
#    並同時抓到當日股價/漲跌幅
# ══════════════════════════════════════════════
def fetch_stock_detail(stock_code):
    """
    抓個股頁面：當日各ETF持股比重、排名、異動、股價
    回傳：{price, chg_pct, date, etf_rows:[{etf, action, rank, weight, shares, shares_chg, date}]}
    """
    url = f'{BASE_URL}/etf/stock/{stock_code}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'lxml')

        # 個股名稱：優先用本地對照表，fallback 用 title 解析
        stock_name = STOCK_NAMES.get(stock_code, '')
        if not stock_name:
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                m = re.match(r'\d+\S*\s+(.+?)\s+[—\-]', title_text)
                if m:
                    stock_name = m.group(1).strip()
                else:
                    for tag in soup.find_all(['div', 'span', 'p']):
                        txt = tag.get_text(strip=True)
                        if txt.startswith(stock_code) and len(txt) < 20:
                            stock_name = txt.replace(stock_code, '').strip()
                            break
        if not stock_name:
            stock_name = stock_code

        # 個股名稱：優先用本地對照表，fallback 解析 title
        stock_name = STOCK_NAME_MAP.get(stock_code, '')
        if not stock_name:
            title_tag = soup.find('title')
            if title_tag:
                import re as _re
                m = _re.match(r'\d+\S*\s+(.+?)\s+[—\-]', title_tag.get_text(strip=True))
                if m:
                    stock_name = m.group(1).strip()
        stock_name = stock_name or stock_code

        # 股價 + 漲跌幅
        price, chg_pct, data_date = None, None, ''
        price_el = soup.find(string=re.compile(r'^\d[\d,]*\.?\d*$'))
        if price_el:
            try:
                price = float(str(price_el).replace(',', ''))
            except:
                pass
        chg_el = soup.find(string=re.compile(r'^[+-]?\d+\.\d+%$'))
        if chg_el:
            try:
                chg_pct = float(str(chg_el).replace('%', ''))
            except:
                pass

        # 最新持股明細表格
        etf_rows = []
        tables = soup.find_all('table')
        for table in tables:
            headers_row = table.find('tr')
            if not headers_row:
                continue
            headers_text = headers_row.get_text()
            if 'ETF' not in headers_text and '排名' not in headers_text:
                continue
            for tr in table.find_all('tr')[1:]:
                cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if len(cells) < 4:
                    continue
                etf_code = cells[0].strip()
                if not re.match(r'\d{5}[A-Z]', etf_code):
                    continue
                action      = cells[1] if len(cells) > 1 else ''
                rank_text   = cells[2] if len(cells) > 2 else ''
                weight_text = cells[3] if len(cells) > 3 else '0'
                shares_text = cells[4] if len(cells) > 4 else '0'
                shares_chg  = cells[5] if len(cells) > 5 else ''
                date_text   = cells[6] if len(cells) > 6 else ''

                try:
                    weight = float(weight_text.replace('%', '').replace(',', ''))
                except:
                    weight = 0

                rk_m = re.search(r'TOP(\d+)', rank_text)
                rank_num = int(rk_m.group(1)) if rk_m else 999

                # 標準化 action
                if '新增' in action or '新進' in action:
                    action_std = 'new-in'
                elif '加碼' in action:
                    action_std = 'add'
                elif '減碼' in action:
                    action_std = 'reduce'
                elif '剔除' in action or '清倉' in action:
                    action_std = 'removed'
                else:
                    action_std = 'hold'

                if not data_date and date_text:
                    data_date = date_text

                etf_rows.append({
                    'etf':        etf_code,
                    'action':     action_std,
                    'rank_num':   rank_num,
                    'rank':       rank_text,
                    'weight':     weight,
                    'shares':     shares_text.replace(',', '').replace('張', ''),
                    'shares_chg': shares_chg,
                    'date':       date_text,
                })
            if etf_rows:
                break

        return {
            'name':      stock_name,
            'price':     price,
            'chg_pct':   chg_pct,
            'date':      data_date,
            'etf_rows':  etf_rows,
        }

    except Exception as e:
        print(f'  個股{stock_code}頁面錯誤：{e}')
        return {'name': stock_code, 'price': None, 'chg_pct': None, 'date': '', 'etf_rows': []}


# ══════════════════════════════════════════════
# 3. 從主頁抓「多檔共同入選」完整清單
# ══════════════════════════════════════════════
def fetch_all_from_main(target_date=None):
    """
    抓 idigi.tw 主頁所有個股，整理成
    per-ETF holdings: {etf_code: [{code,name,rank,weight,action,shares}]}
    """
    print(f'  抓取 idigi.tw 主頁...')
    html = fetch_idigi_main(target_date)
    if not html:
        return {}, [], ''

    soup = BeautifulSoup(html, 'lxml')

    # 取資料日期
    data_date = ''
    for t in soup.stripped_strings:
        m = re.search(r'(\d{4}-\d{2}-\d{2})', t)
        if m:
            data_date = m.group(1)
            break

    # 找所有個股連結
    all_stock_codes = []
    for a in soup.find_all('a', href=re.compile(r'/etf/stock/\d+')):
        m = re.search(r'/etf/stock/(\d+)', a.get('href', ''))
        if m:
            code = m.group(1)
            if code not in all_stock_codes:
                all_stock_codes.append(code)

    print(f'  發現 {len(all_stock_codes)} 支個股')
    return all_stock_codes, data_date


# ══════════════════════════════════════════════
# 4. 組裝 per-ETF 持股結構
# ══════════════════════════════════════════════
def build_etf_holdings(stock_details):
    """
    stock_details: {code: {name, price, chg_pct, etf_rows}}
    回傳: {etf_code: [holding_dict]}
    """
    etf_map = {}
    for code, detail in stock_details.items():
        for row in detail.get('etf_rows', []):
            etf_code = row['etf']
            if etf_code not in ETF_LIST:
                continue
            if etf_code not in etf_map:
                etf_map[etf_code] = []
            etf_map[etf_code].append({
                'code':     code,
                'name':     detail.get('name') or STOCK_NAME_MAP.get(code, code),
                'industry': INDUSTRY_MAP.get(code, '其他'),
                'price':    detail.get('price'),
                'chg_pct':  detail.get('chg_pct'),
                'weight':   row['weight'],
                'shares':   row['shares'],
                'rank':     row['rank_num'],
                'action':   row['action'],
            })

    # 每個ETF按權重排序並重新編排名
    for etf_code in etf_map:
        etf_map[etf_code].sort(key=lambda x: x['weight'], reverse=True)
        for i, h in enumerate(etf_map[etf_code], 1):
            h['rank'] = i

    return etf_map


# ══════════════════════════════════════════════
# 5. 歷史資料 I/O
# ══════════════════════════════════════════════
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_history(history):
    for path in [HISTORY_FILE, os.path.join(GITHUB_DIR, 'history.json')]:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════
# 6. 第5點：判斷ETF是否真的更新
# ══════════════════════════════════════════════
def is_data_fresh(etf_code, today_data, yesterday_data):
    t = today_data.get(etf_code, [])
    y = yesterday_data.get(etf_code, [])
    if not t:
        return False
    if not y:
        return True
    t_set = {(h['code'], round(h['weight'], 2)) for h in t}
    y_set = {(h['code'], round(h['weight'], 2)) for h in y}
    if t_set == y_set:
        print(f'  ⚠ {etf_code} 持股與昨日相同，排除統計')
        return False
    return True


# ══════════════════════════════════════════════
# 7. 計算今昨變化（第5、6、7點）
# ══════════════════════════════════════════════
def build_output(today_data, yesterday_data, fresh_etfs):
    stock_map    = {}
    removed_list = []

    for etf_code in fresh_etfs:
        holdings  = today_data.get(etf_code, [])
        etf_name  = ETF_LIST.get(etf_code, etf_code)
        prev      = {h['code']: h for h in yesterday_data.get(etf_code, [])}
        today_set = {h['code'] for h in holdings}

        for h in holdings:
            sc = h['code']
            if not sc:
                continue
            w_now    = h['weight']
            w_prev   = prev[sc]['weight'] if sc in prev else None
            is_new   = sc not in prev
            wchg     = round(w_now - w_prev, 2) if w_prev is not None else None

            rk = h['rank']
            rank_label = 'TOP3' if rk <= 3 else 'TOP5' if rk <= 5 else 'TOP10' if rk <= 10 else ''

            # action 優先採用 idigi 本身的標記，fallback 用權重計算
            raw_action = h.get('action', '')
            if raw_action == 'new-in' or is_new:
                action = 'new-in'
            elif raw_action == 'reduce' or (wchg is not None and wchg < 0):
                action = 'reduce'
            elif raw_action == 'add' or (wchg is not None and wchg > 0):
                action = 'add'
            else:
                action = 'hold'

            if sc not in stock_map:
                stock_map[sc] = {
                    'code': sc, 'name': h['name'],
                    'industry': h.get('industry', '其他'),
                    'price': h.get('price'), 'chg': None,
                    'chg_pct': h.get('chg_pct'),
                    'etfs': [], 'total_wchg': 0,
                    'cat': 'new' if is_new else 'buy',
                }

            stock_map[sc]['etfs'].append({
                'etf': etf_code, 'etf_name': etf_name,
                'action': action, 'rank': rank_label, 'rank_num': rk,
                'wchg': wchg, 'weight': w_now,
                'prev_weight': w_prev, 'shares': h.get('shares', '0'),
            })

            if wchg is not None:
                stock_map[sc]['total_wchg'] = round(
                    stock_map[sc]['total_wchg'] + wchg, 2)

        # 第6點：完全剔除個股
        for sc, h in prev.items():
            if sc not in today_set:
                removed_list.append({
                    'code': sc, 'name': h.get('name', sc),
                    'industry': h.get('industry', INDUSTRY_MAP.get(sc, '其他')),
                    'etf': etf_code, 'etf_name': etf_name,
                    'prev_weight': h['weight'],
                    'prev_rank': h.get('rank', 0),
                    'wchg': round(-h['weight'], 2),
                    'price': None, 'chg_pct': None,
                })

    buy, new_in, sell = [], [], []
    for s in stock_map.values():
        actions = [e['action'] for e in s['etfs']]
        n = len(s['etfs'])
        if all(a in ['reduce', 'hold'] for a in actions) and any(a == 'reduce' for a in actions):
            s['cat'] = 'sell'
        elif ('new-in' in actions or 'add' in actions) and n == 1:
            s['cat'] = 'new'
        elif n >= 2:
            s['cat'] = 'buy'

        if s['cat'] == 'sell': sell.append(s)
        elif s['cat'] == 'new': new_in.append(s)
        else: buy.append(s)

    buy.sort(key=lambda s: (-len(s['etfs']), -abs(s['total_wchg'])))
    new_in.sort(key=lambda s: (-len(s['etfs']), -abs(s['total_wchg'])))
    sell.sort(key=lambda s: s['total_wchg'])
    removed_list.sort(key=lambda x: -x['prev_weight'])

    return buy[:20], new_in[:15], sell[:10], removed_list


# ══════════════════════════════════════════════
# 8. AI分析摘要文字
# ══════════════════════════════════════════════
def build_ai_summary(buy, new_in, sell, removed, fresh_etfs, today, yesterday):
    lines = [
        f'基準日：{today}，比較日：{yesterday}',
        f'有效更新ETF：{",".join(fresh_etfs)}（共{len(fresh_etfs)}支）\n',
        '【多檔共同買進/加碼】',
    ]
    for s in buy[:10]:
        etf_str = ' | '.join(
            f"{e['etf']} {e['action']} [{e['rank']}] {e['weight']:.2f}%"
            + (f" ({'+' if (e['wchg'] or 0)>0 else ''}{e['wchg']}pp)" if e['wchg'] is not None else '')
            for e in s['etfs']
        )
        lines.append(f"  {s['code']} {s['name']}（{s['industry']}）→ {etf_str}")

    lines += ['\n【新進持股】']
    for s in new_in[:8]:
        lines.append(f"  {s['code']} {s['name']}（{s['industry']}）← {','.join(e['etf'] for e in s['etfs'])}")

    lines += ['\n【減碼個股】']
    for s in sell[:6]:
        etf_str = ' | '.join(f"{e['etf']} {e['wchg']}pp" for e in s['etfs'] if e['wchg'] is not None)
        lines.append(f"  {s['code']} {s['name']}（{s['industry']}）→ {etf_str}")

    lines += ['\n【完全剔除】']
    for r in removed[:6]:
        lines.append(f"  {r['code']} {r['name']}（{r['industry']}）← {r['etf']} 原{r['prev_weight']}%")

    # 產業統計
    industry_cnt = {}
    for s in buy + new_in:
        ind = s.get('industry', '其他')
        industry_cnt[ind] = industry_cnt.get(ind, 0) + len(s['etfs'])
    top_inds = sorted(industry_cnt.items(), key=lambda x: -x[1])[:6]
    lines += ['\n【今日ETF買進產業強度（涉及ETF次數）】']
    for ind, cnt in top_inds:
        lines.append(f"  {ind}：{cnt}次")

    return '\n'.join(lines)


# ══════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════
def main():
    today = datetime.now().strftime('%Y-%m-%d')
    print(f'\n{"="*55}')
    print(f'  台灣主動ETF爬蟲 v5（idigi.tw）  {today}')
    print(f'{"="*55}\n')

    history = load_history()

    # ── Step 1: 從主頁取得所有個股代號 ──────
    print('▶ Step1：抓取主頁個股清單...')
    all_stock_codes, data_date = fetch_all_from_main()
    if not all_stock_codes:
        print('❌ 無法取得個股清單，中止')
        return
    print(f'  ✓ 共{len(all_stock_codes)}支個股  資料日期:{data_date}')

    # ── Step 2: 逐一抓個股詳情頁 ────────────
    print(f'\n▶ Step2：抓取各個股詳情頁...')
    stock_details = {}
    for i, code in enumerate(all_stock_codes, 1):
        print(f'  [{i}/{len(all_stock_codes)}] {code}', end=' ', flush=True)
        detail = fetch_stock_detail(code)
        detail['name'] = detail.get('name', code)

        # 從 etf_rows 過濾只保留我們追蹤的ETF
        detail['etf_rows'] = [
            row for row in detail.get('etf_rows', [])
            if row['etf'] in ETF_LIST
        ]

        if detail['etf_rows']:
            stock_details[code] = detail
            print(f"✓ {len(detail['etf_rows'])}個ETF持有")
        else:
            print('跳過')
        time.sleep(0.8)

    print(f'\n  ✓ 有效個股：{len(stock_details)}支')

    # ── Step 3: 組裝 per-ETF 持股資料 ───────
    print('\n▶ Step3：組裝ETF持股資料...')
    today_data = build_etf_holdings(stock_details)
    all_codes  = set(stock_details.keys())
    data_dates = {code: data_date for code in today_data}
    print(f'  ✓ 涵蓋ETF：{list(today_data.keys())}')

    # ── Step 4: 存歷史 ───────────────────────
    history[today] = today_data
    save_history(history)

    # ── Step 5: 判斷哪些ETF有真實更新 ───────
    dates          = sorted(history.keys())
    yesterday      = dates[-2] if len(dates) >= 2 else dates[0]
    yesterday_data = history.get(yesterday, {})

    fresh_etfs, stale_etfs = [], []
    for code in today_data:
        if is_data_fresh(code, today_data, yesterday_data):
            fresh_etfs.append(code)
        else:
            stale_etfs.append(code)

    print(f'\n  ✓ 有更新：{fresh_etfs}')
    if stale_etfs:
        print(f'  ⚠ 未更新（排除）：{stale_etfs}')

    # ── Step 6: 計算變化 ─────────────────────
    buy, new_in, sell, removed = build_output(
        today_data, yesterday_data, fresh_etfs)

    # ── Step 7: ETF完整持股明細（第8點） ────
    etf_detail = {}
    for code, holdings in today_data.items():
        etf_detail[code] = {
            'etf_name':  ETF_LIST.get(code, code),
            'data_date': data_dates.get(code, today),
            'is_fresh':  code in fresh_etfs,
            'total':     len(holdings),
            'holdings':  holdings,
        }

    # ── Step 8: AI分析摘要 ───────────────────
    ai_summary = build_ai_summary(
        buy, new_in, sell, removed, fresh_etfs, today, yesterday)

    output = {
        'generated_at':    today,
        'compare_date':    yesterday,
        'etf_count':       len(today_data),
        'fresh_etf_count': len(fresh_etfs),
        'fresh_etfs':      fresh_etfs,
        'stale_etfs':      stale_etfs,
        'stock_count':     len(all_codes),
        'buy':             buy,
        'new':             new_in,
        'sell':            sell,
        'removed':         removed,
        'etf_detail':      etf_detail,
        'ai_summary':      ai_summary,
    }

    for path in [HOLDINGS_FILE, os.path.join(GITHUB_DIR, 'holdings.json')]:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f'  ✓ 寫入：{path}')

    print(f'\n{"="*55}')
    print(f'  買進:{len(buy)} 新進:{len(new_in)} 減碼:{len(sell)} 剔除:{len(removed)}')
    print(f'{"="*55}\n')


if __name__ == '__main__':
    main()

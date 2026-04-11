"""
1688工厂搜索API代理服务 (Playwright版)
- 使用Playwright浏览器引擎模拟真实访问1688
- 提取工厂/供应商信息并返回结构化JSON
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import re
import time
import traceback
from urllib.parse import quote
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from playwright.sync_api import sync_playwright

app = Flask(__name__, static_folder='.')
CORS(app)

# ========== 全局浏览器实例 ==========
pw = None
browser = None
context = None


def get_browser_context():
    """获取或创建浏览器上下文(复用实例避免每次启动)"""
    global pw, browser, context
    if context is None:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        # 预热: 访问1688首页获取cookies
        try:
            page = context.new_page()
            page.goto('https://www.1688.com/', wait_until='domcontentloaded', timeout=15000)
            time.sleep(2)
            page.close()
        except:
            pass
    return context


def search_1688_factories(keyword, page_size=30):
    """
    使用Playwright抓取1688工厂搜索结果
    - 搜索公司/供应商页面
    - 提取工厂详细信息
    """
    factories = []
    seen_names = set()
    ctx = get_browser_context()
    encoded_kw = quote(keyword)

    # === 阶段1: 搜索公司页面 ===
    try:
        page = ctx.new_page()
        url = f'https://s.1688.com/company/company_search.htm?keywords={encoded_kw}&button_click=top&n=y'
        print(f"  [Step 1] Company search: {url}")
        page.goto(url, wait_until='domcontentloaded', timeout=20000)
        time.sleep(3)

        # 等待内容加载
        try:
            page.wait_for_selector('.sm-company, .company-item, [class*="company"], [class*="offer"]', timeout=8000)
        except:
            pass

        # 提取页面文本 + HTML
        html = page.content()
        factories_from_page = extract_factories_from_html(html, keyword)
        for f in factories_from_page:
            if f['name'] not in seen_names:
                seen_names.add(f['name'])
                factories.append(f)

        # 从JS脚本数据中提取
        try:
            js_data = page.evaluate('''() => {
                try {
                    if (window.__INIT_DATA__) return JSON.stringify(window.__INIT_DATA__);
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        if (s.textContent && s.textContent.includes('companyName')) {
                            const m = s.textContent.match(/window\\.__INIT_DATA__\\s*=\\s*(\\{.+?\\});/s);
                            if (m) return m[1];
                        }
                    }
                } catch(e) {}
                return null;
            }''')
            if js_data:
                js_factories = parse_init_data(js_data, keyword)
                for f in js_factories:
                    if f['name'] not in seen_names:
                        seen_names.add(f['name'])
                        factories.append(f)
        except:
            pass

        page.close()
    except Exception as e:
        print(f"  [WARN] Company search error: {e}")
        try: page.close()
        except: pass

    # === 阶段2: 商品搜索页面提取卖家 ===
    if len(factories) < page_size:
        try:
            page = ctx.new_page()
            url = f'https://s.1688.com/selloffer/offer_search.htm?keywords={encoded_kw}&n=y&netType=1%2C11&sortType=booked&beginPage=1'
            print(f"  [Step 2] Product search: {url}")
            page.goto(url, wait_until='domcontentloaded', timeout=20000)
            time.sleep(3)

            try:
                page.wait_for_selector('[class*="offer"], [class*="card"], [class*="item"]', timeout=8000)
            except:
                pass

            html = page.content()
            prod_factories = extract_sellers_from_product_page(html, keyword)
            for f in prod_factories:
                if f['name'] not in seen_names:
                    seen_names.add(f['name'])
                    factories.append(f)

            # JS数据提取
            try:
                js_data = page.evaluate('''() => {
                    try {
                        if (window.__INIT_DATA__) return JSON.stringify(window.__INIT_DATA__);
                        if (window.__page_data__) return JSON.stringify(window.__page_data__);
                    } catch(e) {}
                    return null;
                }''')
                if js_data:
                    js_factories = parse_init_data(js_data, keyword)
                    for f in js_factories:
                        if f['name'] not in seen_names:
                            seen_names.add(f['name'])
                            factories.append(f)
            except:
                pass

            # 翻到第二页获取更多
            if len(factories) < page_size:
                try:
                    url2 = f'https://s.1688.com/selloffer/offer_search.htm?keywords={encoded_kw}&n=y&netType=1%2C11&sortType=booked&beginPage=2'
                    page.goto(url2, wait_until='domcontentloaded', timeout=20000)
                    time.sleep(3)
                    html2 = page.content()
                    more = extract_sellers_from_product_page(html2, keyword)
                    for f in more:
                        if f['name'] not in seen_names:
                            seen_names.add(f['name'])
                            factories.append(f)
                except:
                    pass

            page.close()
        except Exception as e:
            print(f"  [WARN] Product search error: {e}")
            try: page.close()
            except: pass

    # === 阶段3: 对信息不完整的工厂，访问详情页补全 ===
    enriched = 0
    for i, f in enumerate(factories[:page_size]):
        if enriched >= 15:
            break
        if f['staffCount'] == 0 and f['area'] == 0 and not f['certifications']:
            try:
                enriched_factory = enrich_with_detail_page(ctx, f)
                factories[i] = enriched_factory
                enriched += 1
            except:
                pass

    # 排名
    for i, f in enumerate(factories[:page_size]):
        f['rank'] = i + 1

    return factories[:page_size]


def extract_factories_from_html(html, keyword):
    """从公司搜索页面HTML中提取工厂信息"""
    from bs4 import BeautifulSoup
    factories = []
    soup = BeautifulSoup(html, 'lxml')

    # 尝试多种选择器找到公司卡片
    cards = soup.select('.sm-company-item, .company-item, [class*="company-card"], [class*="companyItem"]')

    # 如果没找到卡片结构,尝试从整个页面提取公司名
    if not cards:
        cards = soup.select('[class*="company"], [class*="seller"], [data-company]')

    for card in cards:
        try:
            # 提取公司名
            name = ''
            for selector in ['.company-name', '.sm-company-name', 'a[title]', '.title', '[class*="companyName"]', '[class*="company-name"]', 'h3', 'h4']:
                el = card.select_one(selector)
                if el:
                    name = (el.get('title') or el.get_text()).strip()
                    if name and len(name) >= 4 and not name.startswith('http'):
                        break
                    name = ''

            if not name or len(name) < 4:
                continue
            # 过滤非公司名
            if any(x in name for x in ['1688', 'alibaba', '登录', '注册', '首页', '搜索']):
                continue

            factory = build_factory_from_card_soup(card, name, keyword)
            factories.append(factory)

        except Exception as e:
            continue

    return factories


def extract_sellers_from_product_page(html, keyword):
    """从商品搜索页面HTML中提取卖家/工厂信息"""
    from bs4 import BeautifulSoup
    factories = []
    seen = set()
    soup = BeautifulSoup(html, 'lxml')

    # 提取所有公司名链接
    for a_tag in soup.find_all('a'):
        href = a_tag.get('href', '')
        title = a_tag.get('title', '')
        text = a_tag.get_text(strip=True)

        company_name = ''
        if 'company' in href and title and len(title) >= 4:
            company_name = title
        elif text and len(text) >= 4 and ('公司' in text or '有限' in text or '工厂' in text or '厂' in text[-1:]):
            company_name = text

        if company_name and company_name not in seen:
            if any(x in company_name for x in ['1688', 'alibaba', '登录', '注册', '首页', '搜索', '查看更多']):
                continue
            seen.add(company_name)
            factories.append(build_factory_from_name(company_name, keyword))

    # 从脚本数据提取
    for script in soup.find_all('script'):
        if not script.string:
            continue
        for m in re.finditer(r'"companyName"\s*:\s*"([^"]{4,60})"', script.string):
            name = m.group(1).replace('\\u', '').strip()
            try:
                name = name.encode().decode('unicode_escape')
            except:
                pass
            if name and len(name) >= 4 and name not in seen:
                if any(x in name for x in ['1688', 'alibaba']):
                    continue
                seen.add(name)
                factories.append(build_factory_from_name(name, keyword))

    return factories


def parse_init_data(js_data_str, keyword):
    """解析页面嵌入的__INIT_DATA__中的工厂数据"""
    factories = []
    try:
        data = json.loads(js_data_str) if isinstance(js_data_str, str) else js_data_str

        # 递归查找所有包含companyName的对象
        company_items = []
        find_companies(data, company_items)

        for item in company_items:
            name = item.get('companyName', '').strip()
            if not name or len(name) < 4:
                continue

            staff_str = str(item.get('employeeCount', item.get('staffCount', '')))
            staff_count = parse_staff_count(staff_str)

            year_str = str(item.get('yearEstablished', item.get('registYear', item.get('establishYear', ''))))
            year_founded = parse_year(year_str)

            area_str = str(item.get('factoryArea', ''))
            area = parse_area(area_str)

            location = item.get('location', item.get('area', ''))
            province, city = parse_location(str(location)) if location else ('', '')

            certs = []
            cert_data = item.get('certifications', item.get('certificates', []))
            if isinstance(cert_data, list):
                for c in cert_data:
                    if isinstance(c, dict):
                        certs.append(c.get('name', ''))
                    elif isinstance(c, str):
                        certs.append(c)

            if not province and not city:
                province, city = guess_location_from_name(name)

            factories.append({
                'name': name,
                'province': province,
                'city': city,
                'staffCount': staff_count,
                'staffScale': 'large' if staff_count >= 200 else ('medium' if staff_count >= 50 else 'small'),
                'yearFounded': year_founded,
                'yearsInBusiness': (2026 - year_founded) if year_founded else 0,
                'area': area,
                'certifications': certs[:8],
                'mainProducts': keyword,
            })
    except:
        pass
    return factories


def find_companies(data, result, depth=0):
    """递归查找含companyName的对象"""
    if depth > 10:
        return
    if isinstance(data, dict):
        if 'companyName' in data and data['companyName']:
            result.append(data)
        for v in data.values():
            find_companies(v, result, depth + 1)
    elif isinstance(data, list):
        for item in data:
            find_companies(item, result, depth + 1)


def enrich_with_detail_page(ctx, factory):
    """访问工厂在1688上的搜索详情页补全信息"""
    name = factory['name']
    page = ctx.new_page()
    try:
        url = f'https://s.1688.com/company/company_search.htm?keywords={quote(name)}'
        page.goto(url, wait_until='domcontentloaded', timeout=12000)
        time.sleep(1.5)

        text = page.evaluate('() => document.body ? document.body.innerText : ""')
        if not text:
            return factory

        # 补全人员规模
        if factory['staffCount'] == 0:
            m = re.search(r'(\d+)\s*[-~到至]\s*(\d+)\s*人', text)
            if m:
                factory['staffCount'] = (int(m.group(1)) + int(m.group(2))) // 2
            else:
                m = re.search(r'(\d+)\s*人(?:以上)?', text)
                if m:
                    factory['staffCount'] = int(m.group(1))
            factory['staffScale'] = 'large' if factory['staffCount'] >= 200 else ('medium' if factory['staffCount'] >= 50 else 'small')

        # 补全面积
        if factory['area'] == 0:
            m = re.search(r'(\d[\d,]*)\s*(?:平方米|m2|m²|㎡|平米)', text)
            if m:
                factory['area'] = int(m.group(1).replace(',', ''))

        # 补全成立年份
        if factory['yearFounded'] == 0:
            m = re.search(r'((?:19|20)\d{2})\s*(?:年|成立)', text)
            if m:
                factory['yearFounded'] = int(m.group(1))
                factory['yearsInBusiness'] = 2026 - factory['yearFounded']

        # 补全认证
        if not factory['certifications']:
            factory['certifications'] = extract_certifications(text)

        # 补全地区
        if not factory['province']:
            province, city = parse_location(text[:500])
            factory['province'] = province
            factory['city'] = city

    except Exception as e:
        print(f"  [WARN] Enrich error for {name}: {e}")
    finally:
        page.close()

    return factory


def build_factory_from_card_soup(card, name, keyword):
    """从BeautifulSoup卡片元素构建工厂数据"""
    text = card.get_text(' ', strip=True)

    # 人员规模
    staff_count = 0
    m = re.search(r'(\d+)\s*[-~到至]\s*(\d+)\s*人', text)
    if m:
        staff_count = (int(m.group(1)) + int(m.group(2))) // 2
    else:
        m = re.search(r'(\d+)\s*人(?:以上)?', text)
        if m:
            staff_count = int(m.group(1))

    # 成立年份
    year_founded = 0
    m = re.search(r'((?:19|20)\d{2})\s*(?:年|成立)', text)
    if m:
        year_founded = int(m.group(1))

    # 工厂面积
    area = 0
    m = re.search(r'(\d[\d,]*)\s*(?:平方米|m2|m²|㎡|平米)', text)
    if m:
        area = int(m.group(1).replace(',', ''))

    # 认证
    certs = extract_certifications(text)

    # 地区
    province, city = '', ''
    for selector in ['.location', '.area', '.address', '[class*="location"]', '[class*="region"]', '[class*="address"]']:
        loc_el = card.select_one(selector)
        if loc_el:
            province, city = parse_location(loc_el.get_text(strip=True))
            if province:
                break

    if not province:
        province, city = guess_location_from_name(name)

    return {
        'name': name,
        'province': province,
        'city': city,
        'staffCount': staff_count,
        'staffScale': 'large' if staff_count >= 200 else ('medium' if staff_count >= 50 else 'small'),
        'yearFounded': year_founded,
        'yearsInBusiness': (2026 - year_founded) if year_founded else 0,
        'area': area,
        'certifications': certs[:8],
        'mainProducts': keyword,
    }


def build_factory_from_name(name, keyword):
    """仅从公司名构建基础工厂数据"""
    province, city = guess_location_from_name(name)
    return {
        'name': name,
        'province': province,
        'city': city,
        'staffCount': 0,
        'staffScale': 'small',
        'yearFounded': 0,
        'yearsInBusiness': 0,
        'area': 0,
        'certifications': [],
        'mainProducts': keyword,
    }


# ========== 解析辅助函数 ==========

def parse_staff_count(s):
    if not s or s in ('None', '0', ''):
        return 0
    m = re.search(r'(\d+)\s*[-~到至]\s*(\d+)', s)
    if m:
        return (int(m.group(1)) + int(m.group(2))) // 2
    m = re.search(r'(\d+)', s)
    return int(m.group(1)) if m else 0


def parse_year(s):
    if not s or s in ('None', '0', ''):
        return 0
    m = re.search(r'((?:19|20)\d{2})', s)
    return int(m.group(1)) if m else 0


def parse_area(s):
    if not s or s in ('None', '0', ''):
        return 0
    m = re.search(r'(\d[\d,]*)', s)
    return int(m.group(1).replace(',', '')) if m else 0


def parse_location(s):
    if not s:
        return ('', '')
    provinces = {
        '广东': '广东省', '浙江': '浙江省', '江苏': '江苏省', '福建': '福建省',
        '山东': '山东省', '上海': '上海市', '北京': '北京市', '天津': '天津市',
        '重庆': '重庆市', '安徽': '安徽省', '河北': '河北省', '湖北': '湖北省',
        '湖南': '湖南省', '四川': '四川省', '河南': '河南省', '江西': '江西省',
        '广西': '广西壮族自治区', '云南': '云南省', '辽宁': '辽宁省', '陕西': '陕西省',
        '吉林': '吉林省', '黑龙江': '黑龙江省', '山西': '山西省', '甘肃': '甘肃省',
    }
    province = ''
    city = ''
    for key, full_name in provinces.items():
        if key in s:
            province = full_name
            break
    m = re.search(r'([\u4e00-\u9fa5]{2,4}(?:市|县|区))', s)
    if m and m.group(1) != province:
        city = m.group(1)
    return (province, city)


def guess_location_from_name(name):
    hints = {
        '深圳': ('广东省', '深圳市'), '东莞': ('广东省', '东莞市'), '广州': ('广东省', '广州市'),
        '佛山': ('广东省', '佛山市'), '中山': ('广东省', '中山市'), '惠州': ('广东省', '惠州市'),
        '珠海': ('广东省', '珠海市'), '揭阳': ('广东省', '揭阳市'), '汕头': ('广东省', '汕头市'),
        '潮州': ('广东省', '潮州市'), '江门': ('广东省', '江门市'), '肇庆': ('广东省', '肇庆市'),
        '义乌': ('浙江省', '义乌市'), '杭州': ('浙江省', '杭州市'), '宁波': ('浙江省', '宁波市'),
        '温州': ('浙江省', '温州市'), '金华': ('浙江省', '金华市'), '台州': ('浙江省', '台州市'),
        '嘉兴': ('浙江省', '嘉兴市'), '绍兴': ('浙江省', '绍兴市'), '慈溪': ('浙江省', '慈溪市'),
        '苏州': ('江苏省', '苏州市'), '南京': ('江苏省', '南京市'), '无锡': ('江苏省', '无锡市'),
        '常州': ('江苏省', '常州市'), '南通': ('江苏省', '南通市'), '扬州': ('江苏省', '扬州市'),
        '厦门': ('福建省', '厦门市'), '泉州': ('福建省', '泉州市'), '福州': ('福建省', '福州市'),
        '莆田': ('福建省', '莆田市'), '漳州': ('福建省', '漳州市'),
        '青岛': ('山东省', '青岛市'), '济南': ('山东省', '济南市'), '临沂': ('山东省', '临沂市'),
        '烟台': ('山东省', '烟台市'), '潍坊': ('山东省', '潍坊市'),
        '上海': ('上海市', '上海市'), '北京': ('北京市', '北京市'), '天津': ('天津市', '天津市'),
        '武汉': ('湖北省', '武汉市'), '成都': ('四川省', '成都市'), '重庆': ('重庆市', '重庆市'),
        '合肥': ('安徽省', '合肥市'), '郑州': ('河南省', '郑州市'), '长沙': ('湖南省', '长沙市'),
        '南昌': ('江西省', '南昌市'), '石家庄': ('河北省', '石家庄市'), '保定': ('河北省', '保定市'),
    }
    for hint, (prov, city) in hints.items():
        if hint in name:
            return (prov, city)
    return ('', '')


def extract_certifications(text):
    cert_keywords = [
        'ISO9001', 'ISO14001', 'ISO45001', 'ISO13485', 'IATF16949',
        'CE', 'FDA', 'UL', 'FCC', 'RoHS', 'REACH', 'BSCI', 'SEDEX',
        'GS', 'SAA', 'PSE', 'KC', 'CCC', '3C', 'SGS', 'TUV',
        'BV', 'LFGB', 'ETL', 'CB', 'GOST', 'SASO',
    ]
    found = []
    upper_text = text.upper()
    for cert in cert_keywords:
        if cert.upper() in upper_text:
            found.append(cert)
    return found[:8]


# ========== API路由 ==========

@app.route('/')
def index():
    return send_from_directory('.', 'factory-dashboard.html')


@app.route('/api/search', methods=['GET'])
def api_search():
    keyword = request.args.get('keyword', '').strip()
    page_size = min(int(request.args.get('size', 30)), 50)

    if not keyword:
        return jsonify({'success': False, 'message': 'Missing keyword', 'data': []})

    print(f"\n{'='*50}")
    print(f"[SEARCH] keyword='{keyword}', size={page_size}")
    start_time = time.time()

    try:
        factories = search_1688_factories(keyword, page_size=page_size)
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()
        factories = []

    elapsed = round(time.time() - start_time, 1)
    print(f"[RESULT] Found {len(factories)} factories in {elapsed}s")

    return jsonify({
        'success': True,
        'keyword': keyword,
        'total': len(factories),
        'elapsed': elapsed,
        'data': factories
    })


# ========== 启动 ==========

if __name__ == '__main__':
    print("=" * 60)
    print("  1688 Factory Search Dashboard (Playwright)")
    print("  URL: http://localhost:5688")
    print("  Press Ctrl+C to stop")
    print("=" * 60)
    print("  Initializing browser engine...")

    # 预初始化浏览器
    try:
        get_browser_context()
        print("  Browser ready!")
    except Exception as e:
        print(f"  [WARN] Browser init failed: {e}")
        print("  Will try again on first search request")

    print("=" * 60)
    app.run(host='0.0.0.0', port=5688, debug=False, threaded=True)

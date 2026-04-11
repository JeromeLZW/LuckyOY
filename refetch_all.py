#!/usr/bin/env python3
"""
全量重新采集广交会供应商数据 — 扩展维度版
采集全部 54000+ 条记录，提取所有可用字段
"""

import json, time, sys, urllib.request, urllib.parse, ssl, os, re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BASE_URL = "https://www.cantonfair.org.cn/b2bshop/api/themeRos/public/shopSearch/searchByVariables"
INDUSTRY_SITE_ID = "461110967833538560"
OUT_PATH = os.path.join(os.path.dirname(__file__), "canton_fair_data_v2.json")
PAGE_SIZE = 100
MAX_RETRIES = 3

def fetch_page(page_num, page_size=PAGE_SIZE):
    params = {
        'industrySiteId': INDUSTRY_SITE_ID,
        'unbox': 'true',
        'size': str(page_size),
        'page': str(page_num),
    }
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.cantonfair.org.cn/',
    })
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                shops = data.get('_embedded', {}).get('b2b:shops', [])
                page_info = data.get('page', {})
                return shops, page_info
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"  [FAIL] page {page_num}: {e}", file=sys.stderr)
                return [], {}

def extract_products_from_desc(desc):
    """从公司简介中提取主营产品关键词"""
    if not desc:
        return ""
    patterns = [
        r'(?:主要|主营|经营|生产|制造|加工|专业生产|专注于|主要产品[为是包括有：:]*|主营产品[为是包括有：:]*|主要经营[：:]*|产品[包括有涵盖涉及：:]*)([\u4e00-\u9fff、，,/\w\s]+?)(?:[。.；;！!]|$)',
        r'(?:从事|致力于)([\u4e00-\u9fff、，,/\w]+?)(?:的研发|的生产|的制造|的设计|等)',
        r'(?:产品远销|出口|销往)([\u4e00-\u9fff]+).*?(?:主要产品|产品包括)([\u4e00-\u9fff、，,/\w]+)',
    ]
    results = []
    for pat in patterns:
        matches = re.findall(pat, desc[:800])
        for m in matches:
            if isinstance(m, tuple):
                for item in m:
                    results.append(item.strip())
            else:
                results.append(m.strip())

    # Clean up
    cleaned = []
    for r in results:
        # Split by common delimiters
        parts = re.split(r'[、，,/]+', r)
        for p in parts:
            p = p.strip()
            if 2 <= len(p) <= 20 and not re.match(r'^(公司|企业|工厂|有限|集团|市场|客户|国内外|国际|多年)', p):
                cleaned.append(p)

    # Deduplicate while preserving order
    seen = set()
    final = []
    for c in cleaned:
        if c not in seen:
            seen.add(c)
            final.append(c)

    return ','.join(final[:8])  # Max 8 terms

def extract_shop_info(shop):
    """提取全部可用字段"""
    udfs = shop.get('udfs', {}) or {}
    site_trader = udfs.get('siteTrader', {}) or {}
    address = shop.get('address', {}) or {}
    desc = shop.get('description', '') or ''

    main_products = udfs.get('mainProducts', '') or ''

    # If mainProducts is empty, try to extract from description
    desc_products = ''
    if not main_products.strip() and desc.strip():
        desc_products = extract_products_from_desc(desc)

    return {
        'code': shop.get('code', ''),
        'name': shop.get('name', ''),
        'address': address.get('fullAddress', ''),
        'province': (address.get('province') or {}).get('name', '') or '',
        'city': (address.get('city') or {}).get('name', '') or '',
        'contact': udfs.get('contactPerson', '') or '',
        'email': udfs.get('email', '') or '',
        'phone': udfs.get('telephone', '') or '',
        'mobile': udfs.get('mobilePhone', '') or '',
        'fax': udfs.get('fax', '') or '',
        'website': udfs.get('website', '') or '',
        'type': udfs.get('typeOfCompany', '') or site_trader.get('typeOfCompany', '') or '',
        'year_established': udfs.get('yearOfEstablishment', '') or '',
        'scale': udfs.get('companyScale', '') or site_trader.get('enterpriseSize', '') or '',
        'capital_wan': udfs.get('registeredCapitalTenThousandRMB', '') or '',
        'trade_forms': ', '.join(udfs.get('tradeForms', []) or []),
        'target_customers': ', '.join(site_trader.get('targetCustomers', []) or []),
        'enterprise_attr': udfs.get('enterpriseAttributes', '') or '',
        'is_brand': site_trader.get('isBrandEnterprise', '') or '',
        'is_new_exhibition': site_trader.get('isNewExhibition', '') or '',
        'is_high_tech': site_trader.get('isNewHighTechEnterprise', '') or '',
        'is_time_honored': site_trader.get('isChinatimeHonoredBrand', '') or '',
        'is_specialized': site_trader.get('isSpecializedSpecializedSpecialNewEnterprise', '') or '',
        'is_green': site_trader.get('isGreenAward', '') or '',
        'is_aeo': site_trader.get('isAeo', '') or '',
        'main_products': main_products,
        'desc_products': desc_products,  # Products extracted from description
        'description': desc[:500] if desc else '',  # Truncate to save space
        'keywords': udfs.get('keyWords', '') or '',
    }

def resolve_province_from_address(info):
    """从fullAddress中提取省份（当province为空时）"""
    if info['province']:
        return
    addr = info['address']
    if not addr:
        return
    provinces = [
        '北京', '天津', '上海', '重庆', '河北', '山西', '辽宁', '吉林', '黑龙江',
        '江苏', '浙江', '安徽', '福建', '江西', '山东', '河南', '湖北', '湖南',
        '广东', '广西', '海南', '四川', '贵州', '云南', '陕西', '甘肃', '青海',
        '内蒙古', '西藏', '宁夏', '新疆',
    ]
    for p in provinces:
        if p in addr:
            info['province'] = p
            break

if __name__ == "__main__":
    print("=" * 60)
    print("全量采集广交会供应商数据 (扩展维度版)")
    print("=" * 60)

    # Get total count first
    _, page_info = fetch_page(0, 1)
    total = page_info.get('totalElements', 0)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    print(f"API总记录数: {total}, 需采集 {total_pages} 页")

    all_data = []
    failed_pages = []

    for pg in range(total_pages):
        shops, pi = fetch_page(pg, PAGE_SIZE)
        if not shops:
            failed_pages.append(pg)
            continue

        for s in shops:
            info = extract_shop_info(s)
            resolve_province_from_address(info)
            all_data.append(info)

        if (pg + 1) % 20 == 0 or pg == total_pages - 1:
            pct = len(all_data) / total * 100
            print(f"  进度: {pg+1}/{total_pages} 页 | 已采集: {len(all_data)} ({pct:.1f}%)")

        time.sleep(0.25)

    # Retry failed pages
    if failed_pages:
        print(f"\n重试 {len(failed_pages)} 个失败页...")
        time.sleep(3)
        for pg in failed_pages:
            shops, _ = fetch_page(pg, PAGE_SIZE)
            for s in shops:
                info = extract_shop_info(s)
                resolve_province_from_address(info)
                all_data.append(info)
            time.sleep(0.5)

    # Stats
    has_products = sum(1 for e in all_data if e['main_products'].strip())
    has_desc_products = sum(1 for e in all_data if e['desc_products'].strip())
    has_any_products = sum(1 for e in all_data if e['main_products'].strip() or e['desc_products'].strip())
    has_province = sum(1 for e in all_data if e['province'].strip())

    print(f"\n{'='*60}")
    print(f"采集完成!")
    print(f"总记录: {len(all_data)}")
    print(f"有mainProducts的: {has_products}")
    print(f"从简介提取产品的: {has_desc_products}")
    print(f"有任意产品信息的: {has_any_products} ({has_any_products/len(all_data)*100:.1f}%)")
    print(f"仍缺失产品信息的: {len(all_data)-has_any_products}")
    print(f"有省份信息的: {has_province}")
    print(f"{'='*60}")

    output = {
        'total_in_db': total,
        'fetched_count': len(all_data),
        'fetch_date': time.strftime('%Y-%m-%d %H:%M'),
        'exhibitors': all_data,
    }

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=1)

    size_mb = os.path.getsize(OUT_PATH) / 1024 / 1024
    print(f"已保存至 {OUT_PATH} ({size_mb:.1f} MB)")

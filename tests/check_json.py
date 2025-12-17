
import json
import re
import os

file_path = r'c:\Users\Simone\Documents\Code Projects\ScrapingStore\data\dashboard.html'

if not os.path.exists(file_path):
    print(f"File not found: {file_path}")
    exit(1)

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    patterns = {
        'products-data': r'<script id="products-data" type="application/json">([\s\S]*?)</script>',
        'kpi-data': r'<script id="kpi-data" type="application/json">([\s\S]*?)</script>',
    }
    
    for name, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            json_str = match.group(1).strip()
            data = json.loads(json_str)
            if name == 'products-data':
                print(f"📦 products-data: {len(data)} items")
                if len(data) > 0:
                    print(f"   First item: {data[0]['name']} (Price: {data[0].get('price')})")
                    print(f"   Last item: {data[-1]['name']} (Price: {data[-1].get('price')})")
            elif name == 'kpi-data':
                print(f"📊 kpi-data: {json.dumps(data, indent=2)}")

except Exception as e:
    print(f"Error: {e}")

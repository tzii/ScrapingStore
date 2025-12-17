
import os

file_path = r'c:\Users\Simone\Documents\Code Projects\ScrapingStore\data\dashboard.html'
if not os.path.exists(file_path):
    print("File not found")
    exit(1)

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

idx_data = content.find('id="products-data"')
idx_logic = content.find('const productsData = JSON.parse')

print(f"Data inject index: {idx_data}")
print(f"Logic parse index: {idx_logic}")

if idx_data != -1 and idx_logic != -1 and idx_data < idx_logic:
    print("✅ PASS: Data scripts appear BEFORE parsing logic.")
else:
    print("❌ FAIL: Data scripts appear AFTER parsing logic or are missing.")

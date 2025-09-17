import json
with open('./schema.json', 'r') as f:
    data = json.load(f)
    print("JSON is valid!")
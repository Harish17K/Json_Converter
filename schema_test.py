import json
with open('./old_schema.json', 'r') as f:
    data = json.load(f)
    print("JSON is valid!")
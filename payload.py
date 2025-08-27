
import json
import os

xml_dir = "/Users/cultistsid/Desktop/Test Folder"
xml_files = [f for f in os.listdir(xml_dir) if f.endswith(".xml")]

payload = {"xmlFiles": []}

for xml_file in xml_files:
    with open(os.path.join(xml_dir, xml_file), "r") as f:
        content = f.read()
        payload["xmlFiles"].append({"name": xml_file, "content": content})

print(json.dumps(payload))

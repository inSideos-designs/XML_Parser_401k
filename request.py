import json
import os
import requests

xml_dir = "/Users/cultistsid/Desktop/Test Folder"
xml_files = [f for f in os.listdir(xml_dir) if f.endswith(".xml")]

payload = {"xmlFiles": []}

for xml_file in xml_files:
    with open(os.path.join(xml_dir, xml_file), "r") as f:
        content = f.read()
        payload["xmlFiles"].append({"name": xml_file, "content": content})

response = requests.post("http://localhost:5173/process-local", json=payload)

with open("output.json", "w") as f:
    json.dump(response.json(), f, indent=4)

print("Successfully fetched data and saved to output.json")
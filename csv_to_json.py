
import csv
import json

def csv_to_json(csv_file_path):
    data = []
    with open(csv_file_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            data.append(row)
    
    file_names = header[5:-1]
    prompts = []
    for row in data:
        prompt_text = row[2]
        values = {}
        for i, file_name in enumerate(file_names):
            values[file_name] = row[i+5]
        prompts.append({"promptText": prompt_text, "values": values})

    return {"fileNames": file_names, "rows": prompts}


csv_file = '/Users/cultistsid/Desktop/Test Folder/plan_express_filled_batch.csv'
json_data = csv_to_json(csv_file)

with open('/Users/cultistsid/Desktop/ai-xml-prompt-filler/expected_output.json', 'w') as f:
    json.dump(json_data, f, indent=4)

print("Successfully converted CSV to JSON and saved as expected_output.json")

import json
import difflib

with open('output.json', 'r') as f:
    output_data = json.load(f)

with open('expected_output.json', 'r') as f:
    expected_data = json.load(f)

output_str = json.dumps(output_data, indent=4, sort_keys=True)
expected_str = json.dumps(expected_data, indent=4, sort_keys=True)

diff = difflib.unified_diff(
    expected_str.splitlines(keepends=True),
    output_str.splitlines(keepends=True),
    fromfile='expected_output.json',
    tofile='output.json',
)

for line in diff:
    print(line, end='')
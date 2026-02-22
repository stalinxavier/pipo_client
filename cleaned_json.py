import re

filename = "_temp\\result1.json"     
output = "yourfile_cleaned.json"

with open(filename, encoding="utf-8") as f:
    content = f.read()


content = re.sub(r'\\([^"\\nrtu])', r'\\\1', content)


lines = []
for line in content.splitlines():
    if not line.strip().startswith('//'):  
        lines.append(line)

clean_content = "\n".join(lines)

with open(output, "w", encoding="utf-8") as f:
    f.write(clean_content)


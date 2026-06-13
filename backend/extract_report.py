import json

with open('./transcript_full.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        if 'Backend Codebase Audit Report' in line:
            d = json.loads(line)
            if 'tool_calls' in d:
                msg = d['tool_calls'][0]['args']['Message']
                with open('./audit_report.md', 'w', encoding='utf-8') as out:
                    out.write(msg)
                print("Extracted.")
                break

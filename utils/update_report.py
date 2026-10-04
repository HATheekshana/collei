"""Safe rich update reports and content-only comparisons."""
from html import escape

def changes(before, after):
    keys = (set(before) | set(after)) - {"source_version"}
    return sorted(k for k in keys if before.get(k) != after.get(k))

def entry(identity, data, fields=None, reason=None):
    result = {"id": str(identity), "name": str(data.get("name") or data.get("enName") or identity)}
    if fields: result["fields"] = fields
    if reason: result["reason"] = reason
    return result

def pages(results):
    blocks = ["<h2>🌿 Data update report</h2>"]
    for section, result in results:
        blocks.append(f"<h3>{escape(section)}</h3>")
        if "error" in result:
            blocks.append(f"<p>Section failed: {escape(result['error'])}. Existing records were retained.</p>")
            continue
        blocks.append(f"<p>Version: {escape(str(result['version']))}</p>"
                      "<table bordered><tr><th>Added</th><th>Changed</th><th>Unchanged</th><th>Failed</th><th>Saved total</th></tr>"
                      f"<tr><td>{result['added']}</td><td>{result['updated']}</td><td>{result.get('unchanged',0)}</td>"
                      f"<td>{result['failed']}</td><td>{result['total']}</td></tr></table>")
        for key, label in (("added_records","Newly added"),("changed_records","Changed"),("failures","Failed")):
            records = result.get(key, [])
            if not records:
                blocks.append(f"<p>{label}: none</p>")
            for start in range(0, len(records), 15):
                lines = []
                for item in records[start:start+15]:
                    suffix = item.get("reason") or ", ".join(item.get("fields", []))
                    lines.append(f"<li><b>{escape(item['name'])}</b> · {escape(item['id'])}"
                                 + (f" — {escape(suffix)}" if suffix else "") + "</li>")
                blocks.append(f"<details><summary>{escape(section)} · {label} ({start+1}–{min(start+15,len(records))} of {len(records)})</summary><ul>"
                              + "".join(lines) + "</ul></details>")
        for warning in result.get("warnings", []):
            blocks.append(f"<p>{escape(warning)}</p>")
    blocks.append("<p>Failed records keep their previous data. Upstream datasets may include unreleased content.</p>")
    output, current = [], ""
    for block in blocks:
        if current and len(current)+len(block)>18000:
            output.append(current);current=""
        current += block
    if current:output.append(current)
    return output

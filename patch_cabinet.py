import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Find the cluster case block and add cabinet before it
cluster_start = html.find('case "cluster":')
if cluster_start < 0:
    print("ERROR: cluster case not found")
    exit(1)

# Find end of cluster case
i = cluster_start + len('case "cluster":')
depth = 0
found_break = -1
while i < len(html):
    c = html[i]
    if c == '{':
        depth += 1
    elif c == '}':
        depth -= 1
    elif depth == 0 and html[i:i+6] == 'break;':
        found_break = i + 6
        break
    i += 1

cabinet_case = '''    case "cabinet":
      host.innerHTML = `<div id="cabinet-list-${pid}"><div class="empty">Loading…</div></div>`;
      const refreshCabinet = () => {
        get("clusters").then(r=>{
          const cls = r.clusters || [];
          if(!cls.length){ $(`#cabinet-list-${pid}`).innerHTML=`<div class="empty">No clusters yet. Send text to create some.</div>`; return; }
          $(`#cabinet-list-${pid}`).innerHTML = cls.map(c=>`<div class="card" style="border-left:3px solid var(--blue);cursor:pointer" onclick="$(this).querySelector('.cab-detail-${pid}-${c.id}').style.display = this.querySelector('.cab-detail-${pid}-${c.id}').style.display==='none'?'block':'none'">
            <strong>${esc(c.name)}</strong> <span style="color:var(--muted);font-size:10px">${c.member_count} members</span>
            <div class="cab-detail-${pid}-${c.id}" style="display:none;margin-top:6px;font-size:10px;color:var(--muted)">
              <div>tags: ${(c.tags||[]).map(t=>"#"+esc(t)).join(" ")||"none"}</div>
              <div>metadata: ${Object.entries(c.metadata||{}).map(([k,v])=>esc(k)+": "+esc(v)).join(", ")||"none"}</div>
            </div>
          </div>`).join("");
        }).catch(()=>{});
      };
      refreshCabinet();
      on("data:input", refreshCabinet);
      break;
'''

new_html = html[:cluster_start] + cabinet_case + html[cluster_start:]
with open('static/index.html', 'w', encoding='utf-8') as f:
    f.write(new_html)

print(f"Done! Added cabinet case. New file: {len(new_html)} chars")

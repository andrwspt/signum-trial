import re

with open('static/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Find the topology case block
start = html.find('case "topology":')
if start < 0:
    print("ERROR: topology case not found")
    exit(1)

# Find end of case (next break; at top level)
i = start + len('case "topology":')
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

old_block = html[start:found_break]

new_topo = '''    case "topology":
      host.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:300px;color:var(--muted)">3D Topography<br><small>Send data to populate</small></div>`;
      const refreshTopo = () => {
        get("topology").then(r=>{
          if(!r.points||!r.points.length) return;
          let scale=1, offX=0, offY=0, dragging=false, lastX=0, lastY=0;
          let rotX=0.5, rotY=0.5, rotating=false;
          let tooltip = null;
          const renderView = () => {
            const W = 700, H = 300;
            const h = `<div style="font-size:11px;color:var(--muted);display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
              <span>${r.points.length} points · ${(r.clusters||[]).length} clusters · zoom ${(scale*100).toFixed(0)}%</span>
              <span><button id="topo-reset-${pid}" style="background:transparent;border:1px solid var(--border);color:var(--muted);border-radius:3px;padding:1px 6px;font-size:10px;cursor:pointer">reset</button></span>
            </div>
            <div style="position:relative;width:100%;height:300px;">
              <canvas id="topo-canvas-${pid}" style="width:100%;height:300px;background:#0a0a0f;border-radius:4px;cursor:grab;touch-action:none"></canvas>
              <div id="topo-tip-${pid}" style="position:absolute;display:none;background:#1a1a24;border:1px solid var(--accent);border-radius:4px;padding:6px 8px;font-size:10px;color:var(--fg);max-width:200px;pointer-events:none;z-index:10"></div>
            </div>`;
            host.innerHTML = h;
            const cv = document.getElementById(`topo-canvas-${pid}`);
            cv.width = cv.offsetWidth || 600;
            cv.height = 300;
            const ctx = cv.getContext("2d");
            const colors=["#6C63FF","#FF6584","#43B581","#FFA94D","#6B9BD2","#845EF7"];
            // Compute ranges
            let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity,minZ=Infinity,maxZ=-Infinity;
            r.points.forEach(pt=>{ minX=Math.min(minX,pt.x3||0); maxX=Math.max(maxX,pt.x3||0); minY=Math.min(minY,pt.y3||0); maxY=Math.max(maxY,pt.y3||0); minZ=Math.min(minZ,pt.z3||0); maxZ=Math.max(maxZ,pt.z3||0); });
            const rangeX=(maxX-minX)||1, rangeY=(maxY-minY)||1, rangeZ=(maxZ-minZ)||1;
            // Rotate 3D point around X and Y axes
            const project = (x,y,z) => {
              const rx = (x-minX)/rangeX*2-1;
              const ry = (y-minY)/rangeY*2-1;
              const rz = (z-minZ)/rangeZ*2-1;
              // Rotate around Y axis
              const cosY=Math.cos(rotY), sinY=Math.sin(rotY);
              const x1 = rx*cosY - rz*sinY;
              const z1 = rx*sinY + rz*cosY;
              // Rotate around X axis
              const cosX=Math.cos(rotX), sinX=Math.sin(rotX);
              const y1 = ry*cosX - z1*sinX;
              const z2 = ry*sinX + z1*cosX;
              // Perspective
              const fov = 3;
              const persp = fov/(fov-z2);
              return {px: x1*persp, py: y1*persp, z: z2, persp};
            };
            const screen = (x,y) => [cv.width/2 + offX + x*80*scale, cv.height/2 + offY + y*80*scale];
            const draw = () => {
              ctx.save(); ctx.setTransform(1,0,0,1,0,0);
              ctx.fillStyle="#0a0a0f"; ctx.fillRect(0,0,cv.width,cv.height);
              // Project all points and sort by z (back to front)
              const projected = r.points.map((pt,idx)=>{
                const p = project(pt.x3||0,pt.y3||0,pt.z3||0);
                const [sx,sy] = screen(p.px,p.py);
                return {sx,sy,z:p.z,persp:p.persp,pt,idx};
              });
              projected.sort((a,b)=>a.z-b.z);
              // Draw
              projected.forEach(p=>{
                const radius = Math.max(2, Math.min(8, 5/p.persp/scale*0.8));
                ctx.beginPath(); ctx.arc(p.sx,p.sy,radius,0,Math.PI*2);
                const alpha = Math.max(0.4, Math.min(1, (1-p.z)/1.5+0.3));
                ctx.fillStyle = colors[(p.pt.cluster||0)%colors.length];
                ctx.globalAlpha = alpha;
                ctx.fill();
                ctx.globalAlpha = 1;
              });
              ctx.restore();
            };
            draw();
            // Hover tooltip
            cv.onmousemove = (e) => {
              if(dragging) return;
              const rect = cv.getBoundingClientRect();
              const mx = e.clientX - rect.left;
              const my = e.clientY - rect.top;
              // Find nearest point within 15px
              let nearest = null, minDist = 15;
              r.points.forEach((pt)=>{
                const p = project(pt.x3||0,pt.y3||0,pt.z3||0);
                const [sx,sy] = screen(p.px,p.py);
                const d = Math.hypot(sx-mx, sy-my);
                if(d < minDist){ minDist = d; nearest = pt; }
              });
              const tip = document.getElementById(`topo-tip-${pid}`);
              if(nearest){
                tip.style.display = 'block';
                tip.style.left = Math.min(cv.offsetWidth-210, mx+15)+'px';
                tip.style.top = my+10+'px';
                tip.innerHTML = `<strong>chunk ${nearest.chunk_id.slice(0,8)}</strong><br>${(nearest.text||'').slice(0,120)}<br><span style="color:var(--muted)">cluster ${nearest.cluster??-1} · ${nearest.tags.join(',')||'no tags'}</span>`;
              } else {
                tip.style.display = 'none';
              }
            };
            cv.onmouseleave = () => { document.getElementById(`topo-tip-${pid}`).style.display='none'; };
            // Mouse wheel zoom
            cv.onwheel = (e) => {
              e.preventDefault();
              const rect = cv.getBoundingClientRect();
              const mx = e.clientX-rect.left-cv.width/2;
              const my = e.clientY-rect.top-cv.height/2;
              const factor = e.deltaY > 0 ? 0.85 : 1.18;
              const newScale = Math.max(0.3, Math.min(15, scale*factor));
              offX = mx-(mx-offX)*(newScale/scale);
              offY = my-(my-offY)*(newScale/scale);
              scale = newScale;
              draw();
            };
            // Drag to pan or rotate
            cv.onmousedown = (e) => { 
              dragging=true; lastX=e.clientX; lastY=e.clientY; 
              cv.style.cursor='grabbing'; 
            };
            const onMove = (e) => { 
              if(!dragging) return; 
              if(e.shiftKey){
                // Shift+drag = rotate
                rotY += (e.clientX-lastX)*0.01;
                rotX += (e.clientY-lastY)*0.01;
              } else {
                offX+=e.clientX-lastX; offY+=e.clientY-lastY; 
              }
              lastX=e.clientX; lastY=e.clientY; 
              draw(); 
            };
            const onUp = () => { dragging=false; cv.style.cursor='grab'; };
            window.addEventListener("mousemove", onMove);
            window.addEventListener("mouseup", onUp);
            cv.ontouchstart = (e) => { if(e.touches.length===1){ dragging=true; lastX=e.touches[0].clientX; lastY=e.touches[0].clientY; }};
            cv.ontouchmove = (e) => { if(!dragging||e.touches.length!==1) return; e.preventDefault(); offX+=e.touches[0].clientX-lastX; offY+=e.touches[0].clientY-lastY; lastX=e.touches[0].clientX; lastY=e.touches[0].clientY; draw(); };
            cv.ontouchend = () => { dragging=false; };
            $(`#topo-reset-${pid}`).onclick = () => { scale=1; offX=0; offY=0; rotX=0.5; rotY=0.5; draw(); };
          };
          renderView();
        }).catch(()=>{});
      };
      refreshTopo();
      on("data:input", refreshTopo);
      break;'''

new_html = html[:start] + new_topo + html[found_break:]
with open('static/index.html', 'w', encoding='utf-8') as f:
    f.write(new_html)

print(f"Done! Patched topology block. New file: {len(new_html)} chars")

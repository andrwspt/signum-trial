"""Fix .after() calls — vanilla JS doesn't have .after() on querySelector elements"""
p = 'static/index.html'
s = open(p, encoding='utf-8').read()

# Replace $.el.after(html) with el.insertAdjacentHTML('afterend', html)
# But we need to handle the jQuery selector properly

# Fix 1: $("#topbar .spacer").after(...)
s = s.replace(
    '$("#topbar .spacer").after(`<div id="panel-add-bar" style="display:flex;gap:4px;align-items:center"></div>`);',
    'document.querySelector("#topbar .spacer").insertAdjacentHTML("afterend", `<div id="panel-add-bar" style="display:flex;gap:4px;align-items:center"></div>`);'
)

# Fix 2: $("#workspace").after(...)
s = s.replace(
    '$("#workspace").after(`<div id="groups-host" style="padding:8px;overflow:auto;max-height:20vh;flex-shrink:0"></div>`);',
    'document.querySelector("#workspace").insertAdjacentHTML("afterend", `<div id="groups-host" style="padding:8px;overflow:auto;max-height:20vh;flex-shrink:0"></div>`);'
)

open(p, 'w', encoding='utf-8').write(s)
print('Fixed .after() calls')

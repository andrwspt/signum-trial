"""Fix dead code in renderer functions - move event handlers after return into setTimeout"""
import re

p = 'static/index.html'
with open(p, encoding='utf-8') as f:
    s = f.read()

# Pattern: match each broken renderer and fix it
# The pattern is: function renderXPanel(p) { return `...`; $($("#id")).onclick = ...; }
# Fix: wrap onclick assignments in setTimeout(() => { ... }, 10); BEFORE the return

renderers = [
    'renderSearchPanel',
    'renderParsePanel',
    'renderClusterPanel',
    'renderFilesPanel',
    'renderChunksPanel',
    'renderDashboardPanel',
    'renderWikiPanel',
    'renderTimelinePanel',
    'renderWordCloudPanel',
    'renderCabinetPanel',
]

fixed = []
for name in renderers:
    # Match: function renderXPanel(p) { return `...`; <code with $().onclick> }
    # We need to extract the code after return and wrap it
    pattern = rf'function {name}\(p\) \{{\n  return `[^`]+`;\n(.+?)\n\}}'
    m = re.search(pattern, s, re.DOTALL)
    if m:
        code_after_return = m.group(1)
        # Wrap in setTimeout
        replacement = f'function {name}(p) {{\n  setTimeout(() => {{\n{code_after_return}\n  }}, 10);\n  return `{m.group(0).split("`")[1]}`;\n}}'
        # Actually, simpler: just add setTimeout wrapper
        old = m.group(0)
        # Extract the return part and the code part
        lines = old.split('\n')
        # Find the line with return `
        return_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith('return `'):
                return_idx = i
                break
        if return_idx is not None:
            before_return = '\n'.join(lines[:return_idx+1])
            after_return = '\n'.join(lines[return_idx+1:])
            # Remove trailing }
            if after_return.rstrip().endswith('}'):
                after_return = after_return.rstrip()[:-1]
            new = before_return + '\n  setTimeout(() => {\n' + after_return + '\n  }, 10);\n}'
            s = s.replace(old, new)
            fixed.append(name)

with open(p, 'w', encoding='utf-8') as f:
    f.write(s)

print(f"Fixed: {fixed}")

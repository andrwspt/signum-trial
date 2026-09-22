// @schema
// {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
//  "properties": {
//    "cluster_id": {"type": "integer"},
//    "cluster_name": {"type": "string"},
//    "member_count": {"type": "integer"},
//    "centroid": {"type": "array", "items": {"type": "number"}},
//    "color": {"type": "string"},
//    "object_type": {"type": "string", "enum": ["tree"]},
//    "size": {"type": "number"},
//    "animation_speed": {"type": "number"},
//    "position_offset": {"type": "array", "items": {"type": "number"}}
//  }}
//
// Forest skin — clusters become trees.
// Tree size ∝ member_count.
// Color = foliage (green palette, varied by cluster).
// Label = cluster_name.
// Arranged by PCA centroid position.
// Gentle sway animation.

var FOREST_COLORS = [
    "#15803d", "#166534", "#14532d", "#1a7f37",
    "#065f46", "#047857", "#365314", "#1d4ed8",
    "#7c3aed", "#0e7490", "#b54708", "#be123c",
];

function forestColor(cluster_id) {
    return FOREST_COLORS[cluster_id % FOREST_COLORS.length];
}

function forestRender(ctx, clusters, proj, t, W, H) {
    var pad = 40;
    var drawW = W - pad * 2;
    var drawH = H - pad * 2;

    // sky / forest floor gradient
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#0f172a");
    g.addColorStop(0.6, "#0a111c");
    g.addColorStop(1, "#04110f");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    // distant haze
    ctx.fillStyle = "#0a142266";
    ctx.fillRect(0, H * 0.7, W, H * 0.3);

    if (!clusters || clusters.length === 0) {
        ctx.fillStyle = "#6b7684";
        ctx.font = "13px ui-monospace, Consolas, monospace";
        ctx.textAlign = "center";
        ctx.fillText("No clusters yet", W / 2, H / 2);
        return;
    }

    var xs = [];
    var zs = [];
    for (var c = 0; c < clusters.length; c++) {
        var cent = clusters[c].centroid;
        if (cent && cent.length >= 2) {
            xs.push(cent[0]);
            zs.push(cent[1] || cent[2] || 0);
        } else {
            xs.push(0);
            zs.push(0);
        }
    }
    var xMin = Math.min.apply(null, xs);
    var xMax = Math.max.apply(null, xs);
    var zMin = Math.min.apply(null, zs);
    var zMax = Math.max.apply(null, zs);
    if (xMax === xMin) { xMax = xMin + 1; }
    if (zMax === zMin) { zMax = zMin + 1; }

    for (var c = 0; c < clusters.length; c++) {
        var cl = clusters[c];
        var xFrac = (xs[c] - xMin) / (xMax - xMin);
        var zFrac = (zs[c] - zMin) / (zMax - zMin);
        var bx = pad + xFrac * drawW;
        var by = pad + zFrac * drawH;

        var treeH = 30 + cl.member_count * 4;
        treeH = Math.min(treeH, 120);
        var canopyR = 10 + cl.member_count * 1.5;
        canopyR = Math.min(canopyR, 40);
        var color = forestColor(cl.cluster_id);
        var name = cl.name || ("Cluster " + cl.cluster_id);

        // trunk
        ctx.fillStyle = "#5c4033";
        ctx.fillRect(bx - 2, by - treeH * 0.45, 4, treeH * 0.45);

        // canopy — layered circles
        var sway = Math.sin(t * 0.8 + c * 1.3) * 2;
        ctx.fillStyle = color + "cc";
        ctx.beginPath();
        ctx.arc(bx + sway, by - treeH * 0.5, canopyR, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = color + "99";
        ctx.beginPath();
        ctx.arc(bx + sway + 4, by - treeH * 0.55, canopyR * 0.7, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = "#f0fdf466";
        ctx.beginPath();
        ctx.arc(bx + sway - 3, by - treeH * 0.48, canopyR * 0.4, 0, Math.PI * 2);
        ctx.fill();

        // glow
        ctx.fillStyle = color + "33";
        ctx.beginPath();
        ctx.arc(bx + sway, by - treeH * 0.5, canopyR * 1.4, 0, Math.PI * 2);
        ctx.fill();

        // label
        ctx.fillStyle = "#fef9c3";
        ctx.font = "9px ui-monospace, Consolas, monospace";
        ctx.textAlign = "center";
        ctx.fillText(name, bx + sway, by - treeH * 0.5 - canopyR - 6);

        // member count
        ctx.fillStyle = "#a8a29e";
        ctx.font = "8px ui-monospace, Consolas, monospace";
        ctx.fillText(cl.member_count + " trees", bx + sway, by - treeH * 0.5 - canopyR - 18);
    }
}

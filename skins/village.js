// @schema
// {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
//  "properties": {
//    "cluster_id": {"type": "integer"},
//    "cluster_name": {"type": "string"},
//    "member_count": {"type": "integer"},
//    "centroid": {"type": "array", "items": {"type": "number"}},
//    "color": {"type": "string"},
//    "object_type": {"type": "string", "enum": ["house"]},
//    "size": {"type": "number"},
//    "animation_speed": {"type": "number"},
//    "position_offset": {"type": "array", "items": {"type": "number"}}
//  }}
//
// Village skin — clusters become houses in a village.
// House size ∝ member_count, clustered around centroid.
// Color = roof color by cluster.
// Label = cluster_name on a signpost.
// Gentle twinkle on house lights.

var VILLAGE_ROOF_COLORS = [
    "#b45309", "#1d4ed8", "#15803d", "#b91c1c",
    "#7c3aed", "#c2410c", "#0e7490", "#a21caf",
    "#d97706", "#0891b2", "#9333ea", "#be123c",
];

var VILLAGE_WALL_COLORS = [
    "#fef3c7", "#fef9c3", "#f5f5f4", "#fefce8",
    "#fff7ed", "#faf5ff", "#ecfeff", "#fdf2f8",
    "#fffbeb", "#e0f2fe", "#f3e8ff", "#fce7f3",
];

function villageColor(cluster_id) {
    return VILLAGE_ROOF_COLORS[cluster_id % VILLAGE_ROOF_COLORS.length];
}

function villageWall(cluster_id) {
    return VILLAGE_WALL_COLORS[cluster_id % VILLAGE_WALL_COLORS.length];
}

function villageRender(ctx, clusters, proj, t, W, H) {
    var pad = 40;
    var drawW = W - pad * 2;
    var drawH = H - pad * 2;

    // warm night
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, "#1e1b4b");
    g.addColorStop(0.5, "#171432");
    g.addColorStop(1, "#0f0a1f");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    // moon
    ctx.fillStyle = "#fef9c3cc";
    ctx.beginPath();
    ctx.arc(W - 50, 45, 14, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#1e1b4b";
    ctx.beginPath();
    ctx.arc(W - 44, 40, 12, 0, Math.PI * 2);
    ctx.fill();

    // stars
    ctx.fillStyle = "#fef9c3";
    for (var s = 0; s < 40; s++) {
        var sx = ((s * 137 + 43) % W);
        var sy = ((s * 89 + 11) % (H * 0.5));
        var sb = 0.3 + 0.7 * Math.abs(Math.sin(t * 0.5 + s));
        ctx.globalAlpha = sb;
        ctx.fillRect(sx, sy, 1.5, 1.5);
    }
    ctx.globalAlpha = 1;

    if (!clusters || clusters.length === 0) {
        ctx.fillStyle = "#a8a29e";
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
        var cx = pad + xFrac * drawW;
        var cy = pad + zFrac * drawH;

        var houseW = 20 + cl.member_count * 1.2;
        houseW = Math.min(houseW, 46);
        var houseH = 22 + cl.member_count * 0.8;
        houseH = Math.min(houseH, 40);
        var roofColor = villageColor(cl.cluster_id);
        var wallColor = villageWall(cl.cluster_id);
        var name = cl.name || ("Cluster " + cl.cluster_id);

        // house body
        ctx.fillStyle = wallColor;
        ctx.fillRect(cx - houseW / 2, cy - houseH, houseW, houseH);

        // roof
        ctx.fillStyle = roofColor;
        ctx.beginPath();
        ctx.moveTo(cx - houseW / 2 - 4, cy - houseH);
        ctx.lineTo(cx, cy - houseH - 14);
        ctx.lineTo(cx + houseW / 2 + 4, cy - houseH);
        ctx.closePath();
        ctx.fill();

        // door
        ctx.fillStyle = "#78350f";
        ctx.fillRect(cx - 4, cy - 8, 8, 8);

        // windows with warm light
        ctx.fillStyle = "#fde68a";
        var ww = 4, wh = 5;
        ctx.fillRect(cx - houseW / 2 + 3, cy - houseH + 4, ww, wh);
        ctx.fillRect(cx + houseW / 2 - 7, cy - houseH + 4, ww, wh);
        ctx.fillRect(cx - houseW / 2 + 3, cy - 13, ww, wh);
        ctx.fillRect(cx + houseW / 2 - 7, cy - 13, ww, wh);

        // twinkle
        var tw = 0.6 + 0.4 * Math.sin(t * 2 + c * 3);
        ctx.fillStyle = "#fde68acc";
        ctx.globalAlpha = tw;
        ctx.fillRect(cx - houseW / 2 + 3, cy - houseH + 4, ww, wh);
        ctx.fillRect(cx + houseW / 2 - 7, cy - houseH + 4, ww, wh);
        ctx.globalAlpha = 1;

        // path to door
        ctx.strokeStyle = "#a8323b33";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx, cy + 12 + (c % 3) * 4);
        ctx.stroke();

        // signpost with cluster name
        var signY = cy - houseH - 22;
        ctx.fillStyle = "#5c4033";
        ctx.fillRect(cx - 1, signY - 2, 2, 10);
        ctx.fillStyle = "#fef3c7";
        ctx.font = "8px ui-monospace, Consolas, monospace";
        ctx.textAlign = "center";
        ctx.fillText(name, cx, signY - 4);

        // member count on ground
        ctx.fillStyle = "rgba(255,243,199,0.4)";
        ctx.font = "7px ui-monospace, Consolas, monospace";
        ctx.fillText(cl.member_count + " houses", cx, cy + 16 + (c % 3) * 4);
    }
}

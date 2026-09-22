// @schema
// {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
//  "properties": {
//    "cluster_id": {"type": "integer"},
//    "cluster_name": {"type": "string"},
//    "member_count": {"type": "integer"},
//    "centroid": {"type": "array", "items": {"type": "number"}},
//    "color": {"type": "string"},
//    "object_type": {"type": "string", "enum": ["building"]},
//    "size": {"type": "number"},
//    "animation_speed": {"type": "number"},
//    "position_offset": {"type": "array", "items": {"type": "number"}}
//  }}
//
// City skin — clusters become buildings.
// Building height ∝ member_count.
// Color = cluster color.
// Label = cluster_name.
// Arranged in a grid by PCA centroid position.
// Idle bob animation.

var CITY_COLORS = [
    "#c2410c", "#1570ef", "#12a150", "#b42318",
    "#7839ee", "#b54708", "#0e7490", "#7c2d12",
    "#f59e0b", "#8b5cf6", "#06b6d4", "#ec4899",
];

function cityColor(cluster_id) {
    return CITY_COLORS[cluster_id % CITY_COLORS.length];
}

function cityRender(ctx, clusters, proj, t, W, H) {
    var pad = 40;
    var drawW = W - pad * 2;
    var drawH = H - pad * 2;

    // ground
    ctx.fillStyle = "#1c1f2b";
    ctx.fillRect(0, 0, W, H);

    // subtle grid
    ctx.strokeStyle = "#2a2f3e";
    ctx.lineWidth = 1;
    for (var gx = 0; gx < W; gx += 40) {
        ctx.beginPath();
        ctx.moveTo(gx, 0);
        ctx.lineTo(gx, H);
        ctx.stroke();
    }
    for (var gy = 0; gy < H; gy += 40) {
        ctx.beginPath();
        ctx.moveTo(0, gy);
        ctx.lineTo(W, gy);
        ctx.stroke();
    }

    if (!clusters || clusters.length === 0) {
        ctx.fillStyle = "#6b7684";
        ctx.font = "13px ui-monospace, Consolas, monospace";
        ctx.textAlign = "center";
        ctx.fillText("No clusters yet", W / 2, H / 2);
        return;
    }

    // layout: spread clusters across the ground by PCA position
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
        var bz = pad + zFrac * drawH;

        var height = 8 + cl.member_count * 3;
        var height = Math.min(height, 90);
        var color = cityColor(cl.cluster_id);
        var name = cl.name || ("Cluster " + cl.cluster_id);

        // building body
        var bwo = 14;
        ctx.fillStyle = color + "cc";
        ctx.fillRect(bx - bwo / 2, bz - height, bwo, height);

        // roof
        ctx.fillStyle = color + "88";
        ctx.beginPath();
        ctx.moveTo(bx - bwo / 2 - 3, bz - height);
        ctx.lineTo(bx, bz - height - 10);
        ctx.lineTo(bx + bwo / 2 + 3, bz - height);
        ctx.closePath();
        ctx.fill();

        // windows
        ctx.fillStyle = "#fde68a";
        var winRows = Math.max(1, Math.floor(height / 12));
        var winCols = 2;
        for (var r = 0; r < winRows; r++) {
            for (var cc = 0; cc < winCols; cc++) {
                var wx = bx - bwo / 2 + 3 + cc * (bwo - 6) / (winCols - 1 || 1);
                var wy = bz - 6 - r * 11;
                ctx.fillRect(wx, wy, 3, 4);
            }
        }

        // glow at top
        ctx.fillStyle = color + "44";
        ctx.fillRect(bx - bwo / 2, bz - height - 6, bwo, 4);

        // label
        ctx.fillStyle = "#f1f5f9";
        ctx.font = "9px ui-monospace, Consolas, monospace";
        ctx.textAlign = "center";
        ctx.fillText(name, bx, bz - height - 10);

        // member count pill
        ctx.fillStyle = "#0f172a";
        ctx.font = "8px ui-monospace, Consolas, monospace";
        ctx.fillText(cl.member_count + " units", bx, bz - height - 22);
    }
}

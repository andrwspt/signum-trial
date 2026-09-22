// @schema
// {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
//  "properties": {
//    "cluster_id": {"type": "integer"},
//    "cluster_name": {"type": "string"},
//    "member_count": {"type": "integer"},
//    "centroid": {"type": "array", "items": {"type": "number"}},
//    "color": {"type": "string"},
//    "object_type": {"type": "string", "enum": ["blob"]},
//    "size": {"type": "number"},
//    "animation_speed": {"type": "number"},
//    "position_offset": {"type": "array", "items": {"type": "number"}}
//  }}
//
// Planet skin — clusters become continent blobs on a sphere.
// Spherical coords from PCA centroid.
// Color = region color by cluster.
// Label = cluster_name on the surface.
// Slow rotation.

var PLANET_REGION_COLORS = [
    "#d97706", "#0891b2", "#059669", "#dc2626",
    "#7c3aed", "#c2410c", "#0e7490", "#a21caf",
    "#ca8a04", "#0284c7", "#047857", "#e11d48",
];

var PLANET_OCEAN = "#0c4a6e";
var PLANET_CLOUD = "rgba(255,255,255,0.06)";

function planetColor(cluster_id) {
    return PLANET_REGION_COLORS[cluster_id % PLANET_REGION_COLORS.length];
}

function planetRender(ctx, clusters, proj, t, W, H) {
    var cx = W / 2;
    var cy = H / 2;
    var R = Math.min(W, H) * 0.38;

    // backdrop
    var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.6);
    g.addColorStop(0, "#0f172a");
    g.addColorStop(1, "#020617");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    // stars
    ctx.fillStyle = "#fef9c3";
    for (var s = 0; s < 80; s++) {
        var sx = ((s * 173 + 59) % W);
        var sy = ((s * 103 + 23) % H);
        var sr = 0.5 + (s % 3) * 0.4;
        var sb = 0.3 + 0.7 * Math.abs(Math.sin(t * 0.3 + s * 1.7));
        ctx.globalAlpha = sb;
        ctx.beginPath();
        ctx.arc(sx, sy, sr, 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.globalAlpha = 1;

    // planet glow
    var rg = ctx.createRadialGradient(cx, cy, R * 0.7, cx, cy, R * 1.3);
    rg.addColorStop(0, "#38bdf866");
    rg.addColorStop(1, "rgba(56,189,248,0)");
    ctx.fillStyle = rg;
    ctx.beginPath();
    ctx.arc(cx, cy, R * 1.3, 0, Math.PI * 2);
    ctx.fill();

    if (!clusters || clusters.length === 0) {
        ctx.fillStyle = "#6b7684";
        ctx.font = "13px ui-monospace, Consolas, monospace";
        ctx.textAlign = "center";
        ctx.fillText("No clusters yet", cx, cy + R + 20);
        return;
    }

    // ocean sphere
    ctx.fillStyle = PLANET_OCEAN + "cc";
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.fill();

    // atmosphere rim
    ctx.strokeStyle = "rgba(56,189,248,0.4)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.stroke();

    // rotation angle
    var rot = t * 0.18;

    // cluster blobs
    var xs = [];
    var ys = [];
    var zs = [];
    for (var c = 0; c < clusters.length; c++) {
        var cent = clusters[c].centroid;
        if (cent && cent.length >= 3) {
            xs.push(cent[0]);
            ys.push(cent[1]);
            zs.push(cent[2]);
        } else if (cent && cent.length >= 2) {
            xs.push(cent[0]);
            ys.push(cent[1]);
            zs.push(0);
        } else {
            xs.push(0);
            ys.push(0);
            zs.push(0);
        }
    }
    var xMin = Math.min.apply(null, xs);
    var xMax = Math.max.apply(null, xs);
    var yMin = Math.min.apply(null, ys);
    var yMax = Math.max.apply(null, ys);
    var zMin = Math.min.apply(null, zs);
    var zMax = Math.max.apply(null, zs);
    if (xMax === xMin) { xMax = xMin + 1; }
    if (yMax === yMin) { yMax = yMin + 1; }
    if (zMax === zMin) { zMax = zMin + 1; }

    for (var c = 0; c < clusters.length; c++) {
        var cl = clusters[c];
        var xFrac = (xs[c] - xMin) / (xMax - xMin) * 2 - 1;
        var yFrac = (ys[c] - yMin) / (yMax - yMin) * 2 - 1;
        var zFrac = (zs[c] - zMin) / (zMax - zMin) * 2 - 1;
        zFrac = Math.max(-1, Math.min(1, zFrac));

        // back/front based on z
        var zWorld = zFrac;
        if (zWorld < 0) continue; // back side — skip for now (could draw dimmer)

        // 3D position on sphere (rotate around Y)
        var cosA = Math.cos(rot);
        var sinA = Math.sin(rot);
        var px = xFrac * R;
        var py = yFrac * R;
        var pz = zFrac * R * 0.6;
        var rx = px * cosA - pz * sinA;
        var rz = px * sinA + pz * cosA;

        // on-screen position from perspective
        var dist = R + 40;
        var ox = cx + rx * (dist / (dist + rz));
        var oy = cy - py * (dist / (dist + rz));
        var depthScale = dist / (dist + rz);

        if (ox < cx - R - 20 || ox > cx + R + 20 || oy < cy - R - 20 || oy > cy + R + 20) continue;

        var size = 8 + cl.member_count * 2;
        size = Math.min(size, 40) * depthScale;
        var color = planetColor(cl.cluster_id);
        var name = cl.name || ("Region " + cl.cluster_id);

        // blob shape — irregular using sin/cos
        var blobR = Math.max(4, size);
        ctx.fillStyle = color + Math.round(180 * depthScale).toString(16).padStart(2, "0");
        ctx.beginPath();
        var pts = 12;
        for (var p = 0; p <= pts; p++) {
            var ang = (p / pts) * Math.PI * 2;
            var rvar = blobR * (0.7 + 0.3 * Math.sin(ang * 3 + c * 2 + t * 0.2));
            var bx = ox + Math.cos(ang) * rvar;
            var by = oy + Math.sin(ang) * rvar * 0.8;
            if (p === 0) ctx.moveTo(bx, by);
            else ctx.lineTo(bx, by);
        }
        ctx.closePath();
        ctx.fill();

        // highlight
        ctx.fillStyle = "rgba(255,255,255,0.15)";
        ctx.beginPath();
        ctx.ellipse(ox - blobR * 0.25, oy - blobR * 0.25, blobR * 0.3, blobR * 0.2, -0.5, 0, Math.PI * 2);
        ctx.fill();

        // label on surface
        var labelDist = Math.sqrt(ox - cx, oy - cy);
        if (labelDist < R * 1.1 && labelDist > R * 0.3) {
            ctx.fillStyle = "#f8fafc";
            ctx.font = (8 + 1 * depthScale) + "px ui-monospace, Consolas, monospace";
            ctx.textAlign = "center";
            ctx.fillText(name, ox, oy - blobR - 6 * depthScale);
            ctx.fillStyle = "rgba(248,250,252,0.5)";
            ctx.font = (7 + 0.5 * depthScale) + "px ui-monospace, Consolas, monospace";
            ctx.fillText(cl.member_count + " units", ox, oy - blobR - 16 * depthScale);
        }
    }

    // cloud wisps
    ctx.fillStyle = PLANET_CLOUD;
    for (var cw = 0; cw < 6; cw++) {
        var ccx = cx + Math.cos(t * 0.1 + cw * 1.2) * R * 0.9;
        var ccy = cy + Math.sin(t * 0.08 + cw * 1.7) * R * 0.6;
        var ccr = R * (0.5 + 0.3 * Math.sin(t * 0.15 + cw));
        ctx.beginPath();
        ctx.ellipse(ccx, ccy, ccr * 0.6, ccr * 0.15, 0, 0, Math.PI * 2);
        ctx.fill();
    }

    // ring display
    ctx.fillStyle = "#f8fafc";
    ctx.font = "10px ui-monospace, Consolas, monospace";
    ctx.textAlign = "center";
    ctx.fillText("PLANET SCALE", cx, cy + R + 24);
    ctx.font = "8px ui-monospace, Consolas, monospace";
    ctx.fillStyle = "#94a3b8";
    var totalUnits = 0;
    for (var tc = 0; tc < clusters.length; tc++) totalUnits += clusters[tc].member_count;
    ctx.fillText(totalUnits + " total units", cx, cy + R + 38);
}

function planetRender(ctx, clusters, proj, t, W, H) {
    var cx = W / 2;
    var cy = H / 2;
    var R = Math.min(W, H) * 0.38;

    var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.6);
    g.addColorStop(0, "#0f172a");
    g.addColorStop(1, "#020617");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    ctx.fillStyle = "#fef9c3";
    for (var s = 0; s < 80; s++) {
        var sx = ((s * 173 + 59) % W);
        var sy = ((s * 103 + 23) % H);
        var sr = 0.5 + (s % 3) * 0.4;
        var sb = 0.3 + 0.7 * Math.abs(Math.sin(t * 0.3 + s * 1.7));
        ctx.globalAlpha = sb;
        ctx.beginPath();
        ctx.arc(sx, sy, sr, 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.globalAlpha = 1;

    var rg = ctx.createRadialGradient(cx, cy, R * 0.7, cx, cy, R * 1.3);
    rg.addColorStop(0, "#38bdf866");
    rg.addColorStop(1, "rgba(56,189,248,0)");
    ctx.fillStyle = rg;
    ctx.beginPath();
    ctx.arc(cx, cy, R * 1.3, 0, Math.PI * 2);
    ctx.fill();

    if (!clusters || clusters.length === 0) {
        ctx.fillStyle = "#6b7684";
        ctx.font = "13px ui-monospace, Consolas, monospace";
        ctx.textAlign = "center";
        ctx.fillText("No clusters yet", cx, cy + R + 20);
        return;
    }

    ctx.fillStyle = PLANET_OCEAN + "cc";
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = "rgba(56,189,248,0.4)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.stroke();

    var rot = t * 0.18;

    var xs = [], ys = [], zs = [];
    for (var c = 0; c < clusters.length; c++) {
        var cent = clusters[c].centroid;
        if (cent && cent.length >= 3) {
            xs.push(cent[0]); ys.push(cent[1]); zs.push(cent[2]);
        } else if (cent && cent.length >= 2) {
            xs.push(cent[0]); ys.push(cent[1]); zs.push(0);
        } else { xs.push(0); ys.push(0); zs.push(0); }
    }
    var xMin = Math.min.apply(null, xs), xMax = Math.max.apply(null, xs);
    var yMin = Math.min.apply(null, ys), yMax = Math.max.apply(null, ys);
    var zMin = Math.min.apply(null, zs), zMax = Math.max.apply(null, zs);
    if (xMax === xMin) { xMax = xMin + 1; }
    if (yMax === yMin) { yMax = yMin + 1; }
    if (zMax === zMin) { zMax = zMin + 1; }

    for (var c = 0; c < clusters.length; c++) {
        var cl = clusters[c];
        var xFrac = (xs[c] - xMin) / (xMax - xMin) * 2 - 1;
        var yFrac = (ys[c] - yMin) / (yMax - yMin) * 2 - 1;
        var zFrac = (zs[c] - zMin) / (zMax - zMin) * 2 - 1;
        zFrac = Math.max(-1, Math.min(1, zFrac));
        var zWorld = zFrac;
        if (zWorld < 0) continue;
        var cosA = Math.cos(rot), sinA = Math.sin(rot);
        var px = xFrac * R, py = yFrac * R, pz = zFrac * R * 0.6;
        var rx = px * cosA - pz * sinA;
        var rz = px * sinA + pz * cosA;
        var dist = R + 40;
        var ox = cx + rx * (dist / (dist + rz));
        var oy = cy - py * (dist / (dist + rz));
        var depthScale = dist / (dist + rz);
        if (ox < cx - R - 20 || ox > cx + R + 20 || oy < cy - R - 20 || oy > cy + R + 20) continue;
        var size = 8 + cl.member_count * 2;
        size = Math.min(size, 40) * depthScale;
        var color = planetColor(cl.cluster_id);
        var name = cl.name || ("Region " + cl.cluster_id);
        var blobR = Math.max(4, size);
        ctx.fillStyle = color + (180 * depthScale | 0).toString(16).padStart(2, "0");
        ctx.beginPath();
        var pts = 12;
        for (var p = 0; p <= pts; p++) {
            var ang = (p / pts) * Math.PI * 2;
            var rvar = blobR * (0.7 + 0.3 * Math.sin(ang * 3 + c * 2 + t * 0.2));
            var bx = ox + Math.cos(ang) * rvar;
            var by = oy + Math.sin(ang) * rvar * 0.8;
            if (p === 0) ctx.moveTo(bx, by); else ctx.lineTo(bx, by);
        }
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,0.15)";
        ctx.beginPath();
        ctx.ellipse(ox - blobR * 0.25, oy - blobR * 0.25, blobR * 0.3, blobR * 0.2, -0.5, 0, Math.PI * 2);
        ctx.fill();
        var labelDist = Math.sqrt((ox - cx) ** 2 + (oy - cy) ** 2);
        if (labelDist < R * 1.1 && labelDist > R * 0.3) {
            ctx.fillStyle = "#f8fafc";
            ctx.font = (8 + 1 * depthScale) + "px ui-monospace, Consolas, monospace";
            ctx.textAlign = "center";
            ctx.fillText(name, ox, oy - blobR - 6 * depthScale);
            ctx.fillStyle = "rgba(248,250,252,0.5)";
            ctx.font = (7 + 0.5 * depthScale) + "px ui-monospace, Consolas, monospace";
            ctx.fillText(cl.member_count + " units", ox, oy - blobR - 16 * depthScale);
        }
    }

    ctx.fillStyle = PLANET_CLOUD;
    for (var cw = 0; cw < 6; cw++) {
        var ccx = cx + Math.cos(t * 0.1 + cw * 1.2) * R * 0.9;
        var ccy = cy + Math.sin(t * 0.08 + cw * 1.7) * R * 0.6;
        var ccr = R * (0.5 + 0.3 * Math.sin(t * 0.15 + cw));
        ctx.beginPath();
        ctx.ellipse(ccx, ccy, ccr * 0.6, ccr * 0.15, 0, 0, Math.PI * 2);
        ctx.fill();
    }

    ctx.fillStyle = "#f8fafc";
    ctx.font = "10px ui-monospace, Consolas, monospace";
    ctx.textAlign = "center";
    ctx.fillText("PLANET SCALE", cx, cy + R + 24);
    ctx.font = "8px ui-monospace, Consolas, monospace";
    ctx.fillStyle = "#94a3b8";
    var totalUnits = 0;
    for (var tc = 0; tc < clusters.length; tc++) totalUnits += clusters[tc].member_count;
    ctx.fillText(totalUnits + " total units", cx, cy + R + 38);
}

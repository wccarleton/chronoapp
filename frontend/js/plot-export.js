// Export the rendered vector scene, never a screenshot, for SVG and PDF.
const NS = "http://www.w3.org/2000/svg";
const FONT = "DejaVu Sans";
let fontsPromise, pdfPromise;

function svgNode(tag, attributes = {}, text) {
  const node = document.createElementNS(NS, tag);
  Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
  if (text !== undefined) node.textContent = text;
  return node;
}
function base64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}
async function loadFonts() {
  fontsPromise ??= Promise.all(["DejaVuSans.ttf", "DejaVuSans-Bold.ttf"].map(async (file, index) => {
    const response = await fetch(new URL(`../vendor/${file}`, import.meta.url));
    if (!response.ok) throw new Error("Could not load the bundled export font. Reload and try again.");
    const buffer = await response.arrayBuffer();
    const face = new FontFace(FONT, buffer, { weight: index ? "700" : "400" });
    await face.load();
    document.fonts.add(face);
    return { file, encoded: base64(buffer), weight: index ? "bold" : "normal" };
  })).catch(error => { fontsPromise = null; throw error; });
  return fontsPromise;
}
function loadScript(file) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = new URL(`../vendor/${file}`, import.meta.url).href;
    script.onload = resolve;
    script.onerror = () => { script.remove(); reject(new Error("Could not load the bundled PDF exporter. Reload and try again.")); };
    document.head.append(script);
  });
}
async function loadPdf() {
  pdfPromise ??= (async () => {
    if (!window.jspdf) await loadScript("jspdf.umd.min.js");
    if (!window.jspdf.jsPDF.API.svg) await loadScript("svg2pdf.umd.min.js");
    return window.jspdf.jsPDF;
  })().catch(error => { pdfPromise = null; throw error; });
  return pdfPromise;
}

function styleSnapshot(snapshot, overlay) {
  const styles = {
    grid: { stroke: "#e2e8eb", "stroke-width": .8 },
    axis: { stroke: "#9aaeb7", "stroke-width": 1 },
    "density-fill": { fill: "#c8e2de", "fill-opacity": overlay ? .65 : 1 },
    "data-line": { fill: "none", stroke: "#176e73", "stroke-width": 1.7, "stroke-linejoin": "round" },
    "curve-band": { fill: "#d9ebea" },
    "overlay-curve-band": { fill: "#eadfcf", "fill-opacity": .75 },
    "overlay-curve-line": { fill: "none", stroke: "#967349", "stroke-width": 1.3 },
    "right-axis": { stroke: "#967349", "stroke-width": 1 },
    "right-axis-label": { fill: "#765836" },
  };
  for (const node of snapshot.querySelectorAll("*")) {
    if (node.tagName === "text") {
      node.setAttribute("fill", "#435964");
      node.setAttribute("font-family", FONT);
      node.setAttribute("font-size", "11");
    }
    if (node.tagName === "circle") node.setAttribute("fill", "#176e73");
    for (const [className, attributes] of Object.entries(styles)) {
      if (!node.classList.contains(className)) continue;
      Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
    }
    node.removeAttribute("class");
  }
  snapshot.removeAttribute("class");
  // A temporary export DOM must not resolve clipping IDs in the live chart.
  const prefix = `export-${crypto.randomUUID()}-`;
  for (const node of snapshot.querySelectorAll("[id]")) {
    const old = node.id;
    node.id = prefix + old;
    for (const target of snapshot.querySelectorAll("[clip-path]")) {
      if (target.getAttribute("clip-path") === `url(#${old})`) target.setAttribute("clip-path", `url(#${node.id})`);
    }
  }
}
function wrapText(value, width, size, bold = false) {
  const context = document.createElement("canvas").getContext("2d");
  context.font = `${bold ? "bold " : ""}${size}px "${FONT}"`;
  const lines = [];
  let line = "";
  for (const character of value) {
    if (line && context.measureText(line + character).width > width) { lines.push(line); line = ""; }
    line += character;
  }
  if (line) lines.push(line);
  return lines;
}
function buildSvg(snapshot, { title, subtitle, overlay, legend, note, radiocarbonSubtitle, summary, calendar = true }, fonts) {
  styleSnapshot(snapshot, overlay);
  const [,, plotWidth, plotHeight] = snapshot.getAttribute("viewBox").split(/\s+/).map(Number);
  const width = plotWidth + 48;
  const output = svgNode("svg", { width, "font-family": FONT });
  output.append(svgNode("title", {}, title));
  output.append(svgNode("desc", {}, "Chronologer plot exported from the current view. Paths and text remain vector objects."));
  output.append(svgNode("style", {}, fonts.map(font => `@font-face {font-family:'${FONT}';font-style:normal;font-weight:${font.weight};src:url(data:font/ttf;base64,${font.encoded}) format('truetype');}`).join("\n")));
  let cursor = 28;
  function lines(value, size, color, bold = false) {
    for (const line of wrapText(value, width - 48, size, bold)) {
      output.append(svgNode("text", { x: 24, y: cursor, fill: color, "font-family": FONT, "font-size": size, "font-weight": bold ? "bold" : "normal" }, line));
      cursor += size + 6;
    }
  }
  lines(title, 16, "#243943", true);
  lines(subtitle, 11, radiocarbonSubtitle ? "#765836" : "#435964");
  if (overlay) {
    const [calibrated, ...radiocarbon] = legend.split(" · ");
    lines(calibrated, 10, "#435964");
    lines(radiocarbon.join(" · "), 10, "#765836");
  }
  if (summary) lines(summary, 11, "#176e73");
  const plot = svgNode("g", { transform: `translate(24 ${cursor})`, "data-layer": "plot" });
  plot.append(...snapshot.childNodes);
  output.append(plot);
  cursor += plotHeight + 14;
  lines(calendar ? "Calendar age · cal BP (before AD 1950) · Older ← → Younger" : "Scale / standard deviation · years", 11, "#435964");
  lines(note ?? "Chronologer · Current view · Engine calibration values preserved", 9, "#667984");
  const height = cursor + 12;
  output.setAttribute("height", height);
  output.setAttribute("viewBox", `0 0 ${width} ${height}`);
  output.insertBefore(svgNode("rect", { width, height, fill: "#ffffff" }), output.firstChild);
  return { svg: output, width, height };
}
function download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  // Keep the URL alive long enough for browser download handling.
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

export async function exportPlot(svg, metadata, format) {
  if (!["svg", "png", "pdf"].includes(format)) throw new Error("Unsupported export format.");
  // Snapshot before asynchronous font/library loads: exporting never changes the
  // live view, and later interactions cannot change the requested figure.
  const snapshot = svg.cloneNode(true);
  const fonts = await loadFonts();
  const { svg: figure, width, height } = buildSvg(snapshot, metadata, fonts);
  const filename = (metadata.title.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").replace(/[. ]+$/, "").slice(0, 100) || "chronologer-plot") + `.${format}`;
  const blob = new Blob([new XMLSerializer().serializeToString(figure)], { type: "image/svg+xml;charset=utf-8" });
  if (format === "svg") { download(blob, filename); return; }
  if (format === "png") {
    const url = URL.createObjectURL(blob);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(width * 3);
      canvas.height = Math.ceil(height * 3);
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      const png = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
      if (!png) throw new Error("The browser could not create this PNG.");
      download(png, filename);
    } finally { URL.revokeObjectURL(url); }
    return;
  }
  const Pdf = await loadPdf();
  // SVG CSS pixels -> PDF points (96 px = 72 pt), retaining vector paths/text.
  const pdf = new Pdf({ orientation: width > height ? "landscape" : "portrait", unit: "pt", format: [width * .75, height * .75], putOnlyUsedFonts: true, compress: true });
  for (const font of fonts) {
    pdf.addFileToVFS(font.file, font.encoded);
    pdf.addFont(font.file, FONT, font.weight);
  }
  pdf.setProperties({ title: metadata.title, subject: metadata.subtitle, creator: "Chronologer" });
  const host = document.createElement("div");
  host.style.cssText = "position:fixed;left:-100000px;top:0;pointer-events:none";
  host.append(figure);
  document.body.append(host);
  try {
    await pdf.svg(figure, { x: 0, y: 0, width: width * .75, height: height * .75 });
    download(pdf.output("blob"), filename);
  } finally { host.remove(); }
}

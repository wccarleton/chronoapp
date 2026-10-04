import { bindPlotInteractions, moveView } from "./plot-interactions.js";
import { exportPlot } from "./plot-export.js";

// Presentation of engine-provided arrays. Stacked peak scaling is visual only.
const NS = "http://www.w3.org/2000/svg";
const number = value => new Intl.NumberFormat("en", { maximumFractionDigits: 6 }).format(value);
const summaryNumber = value => new Intl.NumberFormat("en", { maximumFractionDigits: 1 }).format(value);
function calibratedSummary(result) {
  const mean = `Calibrated mean: ${summaryNumber(-result.posterior_mean)} cal BP`;
  const intervals = result.hdi_intervals?.map(([older, younger]) => `${summaryNumber(-older)}–${summaryNumber(-younger)}`).join("; ");
  return `${mean} · 95% HDI: ${intervals ? `${intervals} cal BP` : "unavailable"}`;
}
const copyView = view => ({ x: [...view.x], y: [...view.y] });
let nextPlotId = 0;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function svgElement(tag, attributes = {}, text) {
  const node = document.createElementNS(NS, tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  if (text !== undefined) node.textContent = text;
  return node;
}
function button(label, action, title = label) {
  const node = element("button", "button secondary plot-button", label);
  node.type = "button";
  node.title = title;
  node.setAttribute("aria-label", title);
  node.addEventListener("click", action);
  return node;
}
function path(points) {
  return points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}
function ticks(low, high, count = 5) {
  const rough = (high - low) / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].find(n => n * power >= rough) * power;
  const first = Math.ceil(low / step) * step;
  const values = [];
  for (let i = 0; i < count + 2; i++) {
    const value = first + step * i;
    if (value > high) break;
    values.push(Math.abs(value) < step * 1e-8 ? 0 : value);
  }
  return values;
}
function axisNumber(value, span) {
  return value !== 0 && (span < .001 || Math.abs(value) >= 1e8)
    ? value.toExponential(2) : number(value);
}

// Explicit domains are conventional cal BP; the plot uses engine coordinates.
function domainControls(label, apply, actionLabel = "Apply", calendar = true, units = calendar ? "cal BP" : "years") {
  const form = element("form", "domain-controls");
  form.noValidate = true;
  form.setAttribute("aria-label", label);
  const inputs = (calendar ? ["Older", "Younger"] : ["Minimum", "Maximum"]).map((name, i) => {
    const wrapper = element("label", "domain-label", `${name} ${units}`);
    const input = element("input", i ? "domain-younger" : "domain-older");
    input.type = "number";
    input.step = "any";
    input.inputMode = "decimal";
    input.placeholder = "Auto";
    input.setAttribute("aria-label", `${label}: ${name.toLowerCase()} ${units}`);
    wrapper.append(input);
    form.append(wrapper);
    return input;
  });
  const applyButton = button(actionLabel, () => {});
  applyButton.type = "submit";
  form.append(applyButton);
  const error = element("p", "domain-error");
  error.id = `domain-error-${nextPlotId++}`;
  error.setAttribute("role", "alert");
  error.hidden = true;
  inputs.forEach(input => input.setAttribute("aria-describedby", error.id));
  form.append(error);
  form.addEventListener("submit", event => {
    event.preventDefault();
    const values = inputs.map(input => input.value.trim() === "" ? NaN : Number(input.value));
    const [older, younger] = calendar ? values : values.map(v => -v);
    const valid = values.every(Number.isFinite) && older > younger
      && older - younger >= .001 && older - younger <= 1e7
      && values.every(value => Math.abs(value) <= 1e9);
    error.hidden = valid;
    inputs.forEach(input => input.setAttribute("aria-invalid", String(!valid)));
    if (!valid) {
      error.textContent = `Enter finite limits with ${calendar ? "Older greater than Younger" : "Maximum greater than Minimum"} (span: 0.001–10,000,000 years; limits within ±1 billion).`;
      inputs[0].focus();
      return;
    }
    apply([-older, -younger]);
  });
  return {
    node: form,
    set(domain) {
      inputs.forEach((input, i) => {
        input.value = domain ? String(Number(((calendar ? -1 : 1) * domain[i]).toFixed(6))) : "";
        input.removeAttribute("aria-invalid");
      });
      error.hidden = true;
    },
    add(node) { form.insertBefore(node, error); },
  };
}

export function resultDomain(results) {
  const first = Math.min(...results.map(result => result.t_values[0]));
  const last = Math.max(...results.map(result => result.t_values.at(-1)));
  const padding = Math.max((last - first) * .04, 1);
  return [first - padding, last + padding];
}

class InteractivePlot {
  constructor(container, { title, subtitle = "", label, xLabel = null, domainUnits = undefined, visualLegend = null, base, height, draw, domainApplied, useGlobal, overlayRows = null, determination = null, rowTicks = null, fitAll = null, exportNote = null, calendar = true, interactive = true }) {
    this.base = copyView(base);
    this.view = copyView(base);
    this.container = container;
    this.height = height;
    this.drawData = draw;
    this.label = label;
    this.xLabel = xLabel ?? (calendar ? "Calendar age (cal BP)" : "Scale / standard deviation (years)");
    this.visualLegend = visualLegend;
    this.calendar = calendar;
    this.overlayRows = overlayRows;
    this.showCurve = false;
    this.determination = determination;
    this.showUncalibrated = false;
    this.overlayReference = null;
    this.rowTicks = rowTicks;
    this.status = element("span", "plot-view-status", "Configured view");
    this.controls = domainControls(title, domain => domainApplied(domain), "Apply", calendar, domainUnits);
    const actions = element("div", "plot-actions");
    actions.append(
      button("+", () => this.zoom(.8), `Zoom in: ${title}`),
      button("−", () => this.zoom(1.25), `Zoom out: ${title}`),
      button("Reset view", () => this.reset(), `Reset view: ${title}`),
    );
    if (useGlobal) actions.append(button("Use global", useGlobal, `Use global domain: ${title}`));
    if (fitAll) actions.append(button("Fit all data", fitAll, `Fit all data: ${title}`));
    if (rowTicks) actions.append(
      button("Expand rows", () => this.zoomRows(.5), "Zoom vertically to separate rows; calendar domain stays fixed"),
      button("Compress rows", () => this.zoomRows(2), "Zoom out vertically; calendar domain stays fixed"),
    );
    this.controls.add(actions);
    this.controls.add(this.status);
    if (interactive) container.append(this.controls.node);

    const tools = element("div", "plot-tools");
    if (overlayRows || determination) {
      const layers = element("fieldset", "plot-layers");
      layers.append(element("legend", "sr-only", `Layers: ${title}`));
      const name = `plot-layer-${nextPlotId++}`;
      const modes = [["density", "Density only"]];
      if (overlayRows) modes.push(["curve", "Density + curve"]);
      if (determination) modes.push(["uncalibrated", "Density + uncalibrated"]);
      if (overlayRows && determination) modes.push(["both", "Density + curve + uncalibrated"]);
      for (const [value, caption] of modes) {
        const label = element("label");
        const radio = element("input");
        radio.type = "radio";
        radio.name = name;
        radio.value = value;
        radio.checked = value === "density";
        radio.addEventListener("change", () => {
          this.showCurve = ["curve", "both"].includes(radio.value);
          this.showUncalibrated = ["uncalibrated", "both"].includes(radio.value);
          this.overlayReference = null;
          this.overlayLegend.hidden = !(this.showCurve || this.showUncalibrated);
          this.overlayLegend.replaceChildren(
            document.createTextNode("Teal: calibrated density (left axis) · "),
            element("span", "radiocarbon-text", this.layerLegend().split(" · ").slice(1).join(" · ")),
          );
          this.render();
        });
        label.append(radio, document.createTextNode(caption));
        if (value !== "density") label.classList.add("radiocarbon-text");
        layers.append(label);
      }
      tools.append(layers);
    }
    const exportControls = element("div", "plot-export-controls");
    const format = element("select", "plot-export-format");
    format.setAttribute("aria-label", `Export format: ${title}`);
    for (const [value, caption] of [["svg", "SVG · vector"], ["png", "PNG · 3×"], ["pdf", "PDF · vector"]]) format.append(new Option(caption, value));
    const exportStatus = element("span", "plot-export-status");
    exportStatus.setAttribute("role", "status");
    const exportButton = button("Export", async () => {
      exportButton.disabled = true;
      format.disabled = true;
      exportStatus.textContent = "Preparing export…";
      exportStatus.classList.remove("export-error");
      try {
        await exportPlot(this.svg, { title, subtitle, overlay: this.showCurve || this.showUncalibrated,
          legend: this.layerLegend(), note: exportNote, calendar: this.calendar, xLabel: this.xLabel,
          radiocarbonSubtitle: Boolean(determination), summary: determination ? calibratedSummary(determination) : null }, format.value);
        exportStatus.textContent = `${format.value.toUpperCase()} downloaded`;
      } catch (error) {
        exportStatus.textContent = error.message || "Export failed. Please try again.";
        exportStatus.classList.add("export-error");
      } finally {
        exportButton.disabled = false;
        format.disabled = false;
      }
    }, `Export current view: ${title}`);
    exportButton.classList.add("plot-export-button");
    exportControls.append(format, exportButton);
    tools.append(exportControls, exportStatus);
    container.append(tools);
    this.overlayLegend = element("p", "overlay-legend", "Teal: calibration output (left axis) · Ochre: curve mean ±1σ (right axis). Both layers share calendar age.");
    this.overlayLegend.hidden = true;
    container.append(this.overlayLegend);
    if (determination) container.append(element("p", "calibrated-summary", calibratedSummary(determination)));

    this.svg = svgElement("svg", {
      class: "chart interactive-chart", role: "group", tabindex: "0",
      "aria-label": `${title}. Drag to pan; scroll or pinch to zoom. Arrow keys pan, plus and minus zoom, Home resets.`,
    });
    const clipId = `plot-clip-${nextPlotId++}`;
    const defs = svgElement("defs");
    const clip = svgElement("clipPath", { id: clipId });
    this.clipRect = svgElement("rect");
    clip.append(this.clipRect);
    defs.append(clip);
    this.axes = svgElement("g");
    this.legend = svgElement("g", { "data-layer": "visual-legend" });
    this.background = svgElement("g", { "clip-path": `url(#${clipId})`, "data-layer": "calibration-curve" });
    this.uncalibrated = svgElement("g", { "clip-path": `url(#${clipId})`, "data-layer": "uncalibrated-density" });
    this.data = svgElement("g", { "clip-path": `url(#${clipId})`, "data-layer": rowTicks ? "stacked-densities" : overlayRows ? "calibration-output" : "curve" });
    // Keep the same SVG element throughout gestures so pointer capture survives.
    this.svg.append(svgElement("title", {}, title), defs, this.axes, this.background, this.data, this.uncalibrated, this.legend);
    container.append(this.svg);
    if (!interactive) {
      this.svg.removeAttribute("tabindex");
      this.svg.setAttribute("aria-label", title);
      this.svg.classList.remove("interactive-chart");
    }
    if (interactive) bindPlotInteractions(this.svg, {
      point: (clientX, clientY) => {
        const rect = this.svg.getBoundingClientRect();
        return {
          x: ((clientX - rect.left) / rect.width * this.width - this.left) / (this.right - this.left),
          y: ((clientY - rect.top) / rect.height * this.height - this.top) / (this.bottom - this.top),
        };
      },
      getView: () => this.view,
      setView: view => this.setView(view),
      reset: () => this.reset(),
    });
    this.observer = new ResizeObserver(() => this.render());
    this.observer.observe(container);
    this.controls.set(this.view.x);
    this.render();
  }
  setBase(view, status = "Configured view") {
    this.base = copyView(view);
    this.resetLabel = status;
    this.reset();
  }
  reset() {
    this.overlayReference = null;
    this.setView(copyView(this.base), this.resetLabel ?? "Configured view");
  }
  setView(view, status = "Adjusted view") {
    this.view = view;
    this.status.textContent = status;
    this.controls.set(view.x);
    this.render();
  }
  zoom(factor) {
    this.setView(moveView(this.view, { x: .5, y: .5 }, { x: .5, y: .5 }, factor));
  }
  zoomRows(factor) {
    const next = moveView(this.view, { x: .5, y: .5 }, { x: .5, y: .5 }, factor);
    this.setView({ x: [...this.view.x], y: next.y });
  }
  dispose() { this.observer.disconnect(); }
  layerLegend() {
    const layers = [];
    if (this.showCurve) layers.push("curve mean ±1σ");
    if (this.showUncalibrated) layers.push("uncalibrated Gaussian (sideways, width scaled for display)");
    return layers.length ? `Teal: calibrated density (left axis) · Ochre: ${layers.join(" and ")} (right axis, ¹⁴C BP).` : "";
  }
  render() {
    if (!this.container.clientWidth) return; // Hidden tab: preserve its view.
    this.width = Math.max(this.container.clientWidth, 250);
    this.left = this.rowTicks ? Math.min(180, Math.max(95, this.width * .24)) : 78;
    this.right = this.width - (this.showCurve || this.showUncalibrated ? 78 : 20);
    this.top = 30;
    this.bottom = this.height - (this.visualLegend ? 150 : 58);
    this.svg.setAttribute("viewBox", `0 0 ${this.width} ${this.height}`);
    const { x: domain, y: range } = this.view;
    const x = value => this.left + (value - domain[0]) / (domain[1] - domain[0]) * (this.right - this.left);
    const y = value => this.bottom - (value - range[0]) / (range[1] - range[0]) * (this.bottom - this.top);
    for (const [key, value] of Object.entries({ x: this.left, y: this.top, width: this.right - this.left, height: this.bottom - this.top })) {
      this.clipRect.setAttribute(key, value);
    }
    this.axes.replaceChildren();
    const addText = (xx, yy, value, anchor = "start") => this.axes.append(svgElement("text", { x: xx, y: yy, "text-anchor": anchor }, value));
    for (const value of ticks(domain[0], domain[1], this.width < 500 ? 3 : 6)) {
      this.axes.append(svgElement("line", { x1: x(value), x2: x(value), y1: this.top, y2: this.bottom, class: "grid" }));
      addText(x(value), this.bottom + 20, axisNumber(this.calendar ? -value : value, domain[1] - domain[0]), "middle");
    }
    if (this.rowTicks) {
      let lastLabelY = -Infinity;
      for (const tick of this.rowTicks) {
        const screenY = y(tick.value);
        if (screenY < this.top || screenY > this.bottom) continue;
        this.axes.append(svgElement("line", { x1: this.left, x2: this.right, y1: screenY, y2: screenY, class: "grid" }));
        if (screenY - lastLabelY < 17) continue;
        const maxLength = Math.floor((this.left - 20) / 6.5);
        const label = tick.label.length > maxLength ? `${tick.label.slice(0, maxLength - 1)}…` : tick.label;
        const node = svgElement("text", { x: this.left - 9, y: screenY + 4, "text-anchor": "end", class: "stacked-row-label" }, label);
        node.append(svgElement("title", {}, tick.detail));
        this.axes.append(node);
        lastLabelY = screenY;
      }
    } else {
      for (const value of ticks(range[0], range[1], 3)) {
        this.axes.append(svgElement("line", { x1: this.left, x2: this.right, y1: y(value), y2: y(value), class: "grid" }));
        addText(this.left - 9, y(value) + 4, axisNumber(value, range[1] - range[0]), "end");
      }
    }
    if (this.rowTicks) {
      addText(this.left, 16, this.label);
    } else {
      const labelY = (this.top + this.bottom) / 2;
      this.axes.append(svgElement("text", {
        x: 12, y: labelY, "text-anchor": "middle", class: "axis-title",
        transform: `rotate(-90 12 ${labelY})`,
      }, this.label));
    }
    this.axes.append(svgElement("text", {
      x: (this.left + this.right) / 2, y: this.bottom + 43,
      "text-anchor": "middle", class: "axis-title",
    }, this.xLabel));
    this.legend.replaceChildren();
    if (this.visualLegend) {
      const entries = [
        ["mean", this.visualLegend.mean],
        ["interval", "95% credible interval (pointwise)"],
        ...(this.visualLegend.events ? [["events", "Posterior event-date densities"]] : []),
      ];
      entries.forEach(([kind, caption], index) => {
        const row = svgElement("g", { transform: `translate(12 ${this.bottom + 65 + index * 25})` });
        if (kind === "events") {
          for (const offset of [0, 16]) row.append(svgElement("path", {
            d: `M${offset},8 v-3 h5 v-6 h5 v-7 h5 v5 h5 v7 h5 v4 Z`,
            fill: "currentColor", "fill-opacity": .16, stroke: "currentColor", "stroke-opacity": .35, "stroke-width": .8,
          }));
        } else {
          row.append(svgElement("path", { d: "M0,5 Q20,-16 42,-2 L42,7 Q20,-3 0,10 Z", class: "curve-band" }));
          if (kind === "mean") row.append(svgElement("path", { d: "M0,8 Q20,-9 42,3", class: "data-line" }));
        }
        row.append(svgElement("text", { x: 54, y: 5 }, caption));
        this.legend.append(row);
      });
      if (this.visualLegend.events) this.legend.append(svgElement("text", {
        x: 66, y: this.bottom + 138,
      }, "Peaks scaled to 20% for display only"));
    }
    this.axes.append(svgElement("line", { x1: this.left, x2: this.right, y1: this.bottom, y2: this.bottom, class: "axis" }));
    this.background.replaceChildren();
    this.uncalibrated.replaceChildren();
    this.data.classList.toggle("with-curve-overlay", this.showCurve || this.showUncalibrated);
    if (this.showCurve || this.showUncalibrated) {
      // Anchor the secondary scale when enabling/resetting the overlay. Both
      // vertical axes then follow the same pan/zoom transform; calendar x is
      // always shared. These are display coordinates, not calibrated values.
      if (!this.overlayReference) {
        let bounds = this.showCurve ? curveView(this.overlayRows, domain).y : [Infinity, -Infinity];
        if (this.showUncalibrated) {
          const { age, error } = this.determination;
          bounds = [Math.min(bounds[0], age - 4.5 * error), Math.max(bounds[1], age + 4.5 * error)];
        }
        this.overlayReference = { output: [...range], curve: bounds };
      }
      const reference = this.overlayReference;
      const curveValue = value => reference.curve[0] + (value - reference.output[0])
        / (reference.output[1] - reference.output[0]) * (reference.curve[1] - reference.curve[0]);
      const curveRange = range.map(curveValue);
      const curveY = value => this.bottom - (value - curveRange[0]) / (curveRange[1] - curveRange[0]) * (this.bottom - this.top);
      if (this.showCurve) drawCurveLayer(this.background, this.overlayRows, x, curveY, domain, true);
      if (this.showUncalibrated) {
        // A Gaussian from the submitted measurement, drawn orthogonally to
        // calendar time. Width is peak-scaled screen space, not calendar age.
        const { age, error } = this.determination;
        const width = (this.right - this.left) * .24;
        const points = Array.from({ length: 241 }, (_, i) => {
          const z = -4.5 + i * 9 / 240;
          return [this.right - width * Math.exp(-.5 * z * z), curveY(age + z * error)];
        });
        this.uncalibrated.append(svgElement("title", {}, `Uncalibrated: ${number(age)} ± ${number(error)} ¹⁴C BP (1σ)`));
        this.uncalibrated.append(svgElement("path", {
          d: `${path([[this.right, points[0][1]], ...points, [this.right, points.at(-1)[1]]])} Z`, class: "overlay-curve-band",
        }));
        this.uncalibrated.append(svgElement("path", { d: path(points), class: "overlay-curve-line" }));
      }
      this.axes.append(svgElement("line", { x1: this.right, x2: this.right, y1: this.top, y2: this.bottom, class: "right-axis" }));
      for (const value of ticks(curveRange[0], curveRange[1], 3)) {
        this.axes.append(svgElement("text", { x: this.right + 8, y: curveY(value) + 4, class: "right-axis-label" }, axisNumber(value, curveRange[1] - curveRange[0])));
      }
      const labelX = this.width - 10, labelY = (this.top + this.bottom) / 2;
      this.axes.append(svgElement("text", {
        x: labelX, y: labelY, "text-anchor": "middle", class: "right-axis-label",
        transform: `rotate(-90 ${labelX} ${labelY})`,
      }, "¹⁴C age · BP"));
    }
    this.data.replaceChildren();
    this.drawData(this.data, x, y, domain);
  }
}

export function createSummaryPlot(container, result, title) {
  const process = result.model === 'ippp_gp';
  const phase = result.model === 'phase';
  const curve = process ? { ...result.intensity, pdf_values: result.intensity.rate_values } : result.density;
  const { t_values: times, pdf_values: mean, lower_values: low, upper_values: high } = curve;
  if (!Array.isArray(times) || times.length < 2 || !times.every(Number.isFinite)
      || times.some((t, i) => i && t <= times[i - 1])
      || ![mean, low, high].every(a => Array.isArray(a) && a.length === times.length && a.every(v => Number.isFinite(v) && v >= 0))
      || low.some((v, i) => v > high[i]) || !(Math.max(...high, ...mean) > 0)) {
    throw new Error("The engine returned invalid density data.");
  }
  const base = { x: [times[0], times.at(-1)], y: [0, Math.max(...high, ...mean) * 1.08] };
  const parameters = element("div", "summary-parameter-plots");
  if (result.marginals?.parameters?.length) container.append(parameters);
  const modelNote = process
    ? 'Posterior mean event intensity and pointwise 95% credible interval across the declared observation period. Units: events per year; no area normalization. Translucent event-date posteriors are peak-scaled to 20% of the intensity curve for display only. Inspect MCMC diagnostics and sensitivity to the observation window, GP priors and grid.'
    : "Posterior mean model density and pointwise 95% credible interval, integrating location and scale uncertainty. Translucent event-date posteriors share the calendar axis, each peak scaled to 20% of the model curve peak (display only). Inspect MCMC diagnostics before interpretation.";
  const note = `${modelNote} Dates are expressed in years using the BP1950 datum (before AD 1950). Where radiocarbon determinations are used, they are calibrated as part of modelling using each event’s selected calibration curve.`;
  container.append(element("h3", "", process ? 'Event intensity and posterior event dates · BP1950' : "Model density and posterior event dates · BP1950"));
  const plot = new InteractivePlot(container, {
    title, subtitle: `${phase ? `${result.distribution === 'uniform' ? 'Uniform' : 'Normal'} phase` : process ? 'GP IPPP' : result.model === "gaussian_mixture" ? "Gaussian mixture" : "Truncated-normal radiocarbon hierarchy"} · Years (BP1950)`, label: process ? 'Event intensity (events/year)' : "Model density (1/year)", base, height: 510,
    xLabel: "Years (BP1950)", domainUnits: "years (BP1950)",
    visualLegend: { mean: process ? "Posterior mean event intensity" : "Posterior mean model density", events: Boolean(result.marginals?.events?.length) },
    exportNote: `${note} ${result.divergences} divergences.`,
    domainApplied: domain => plot.setBase({ x: domain, y: base.y }),
    draw(group, x, y) {
      const upper = times.map((t, i) => [x(t), y(high[i])]);
      const lower = times.map((t, i) => [x(t), y(low[i])]).reverse();
      group.append(svgElement("path", { d: `${path([...upper, ...lower])} Z`, class: "curve-band" }));
      for (const event of result.marginals?.events ?? []) {
        const scale = .2 * Math.max(...mean) / Math.max(...event.pdf_values);
        const points = event.t_values.map((t, i) => [x(t), y(event.pdf_values[i] * scale)]);
        const shape = svgElement("path", {
          d: `${path([[points[0][0], y(0)], ...points, [points.at(-1)[0], y(0)]])} Z`,
          fill: "currentColor", "fill-opacity": .16, stroke: "currentColor", "stroke-opacity": .35, "stroke-width": .8,
          "data-event-index": event.index,
        });
        shape.append(svgElement("title", {}, `${event.id}: model-conditioned event-date posterior; peak scaled for display`));
        group.append(shape);
      }
      group.append(svgElement("path", { d: path(times.map((t, i) => [x(t), y(mean[i])])), class: "data-line" }));
    },
  });
  plot.data.dataset.layer = process ? 'process-intensity' : "summary-density";
  container.append(element("p", "help", note));
  const plots = [plot];
  for (const parameter of result.marginals?.parameters ?? []) {
    const section = element("section", "summary-parameter-plot");
    section.dataset.parameter = parameter.name;
    const caption = parameter.label.replace(/cal BP/g, "BP1950");
    section.append(element("h3", "", caption));
    parameters.append(section);
    const times = parameter.t_values, values = parameter.pdf_values;
    const base = { x: [times[0], times.at(-1)], y: [0, Math.max(...values) * 1.1] };
    const marginalPlot = new InteractivePlot(section, {
      title: `${title} — ${caption}`, subtitle: `Marginal posterior: ${parameter.name}`,
      label: process ? 'Posterior density' : "Posterior density / year", calendar: parameter.calendar, height: 190, base, interactive: false,
      xLabel: parameter.calendar ? "Years (BP1950)" : caption, domainUnits: parameter.calendar ? "years (BP1950)" : undefined,
      exportNote: phase ? 'Histogram of retained phase posterior draws. Scale is full width for uniform phases and sigma for normal phases.' : process ? 'Histogram of retained GP IPPP posterior draws.' : "Histogram of retained posterior draws. Location and scale are truncated-normal parameters, not the truncated distribution's actual moments.",
      domainApplied: domain => marginalPlot.setBase({ x: domain, y: base.y }),
      draw(group, x, y) {
        const points = times.map((t, i) => [x(t), y(values[i])]);
        group.append(svgElement("path", { d: `${path([[x(times[0]), y(0)], ...points, [x(times.at(-1)), y(0)]])} Z`, class: "curve-band" }));
        group.append(svgElement("path", { d: path(points), class: "data-line" }));
      },
    });
    plots.push(marginalPlot);
  }
  if (result.marginals?.parameters?.length) container.append(element("p", "help", phase ? 'Parameter panels show phase center and full width (uniform) or mean and sigma (normal). Ordered downstream centers are derived from the selected quantiles and delta.' : process ? 'Parameter panels show the baseline log rate, GP amplitude and temporal length scale, and the integrated intensity (expected count over the declared period).' : "Parameter panels show marginal posterior histograms. Location (μ) and scale (σ) describe the underlying normal; truncation can make the model’s actual mean and SD differ."));
  return { dispose() { plots.forEach(p => p.dispose()); } };
}

function distributionRenderer(result, { baseline = 0, scale = 1 } = {}) {
  const segments = [];
  const times = result.t_values;
  let step = Infinity;
  for (let i = 1; i < times.length; i++) step = Math.min(step, times[i] - times[i - 1]);
  let segment = [];
  times.forEach((time, i) => {
    if (i && time - times[i - 1] > step * 1.5) { segments.push(segment); segment = []; }
    segment.push([time, result.pdf_values[i]]);
  });
  segments.push(segment);
  return (group, x, y) => {
    // Preserve the engine's trimmed gaps, and always fill to data zero, not the
    // moving viewport edge. The clip path handles zooming and vertical panning.
    for (const segment of segments) {
      const points = segment.map(([t, value]) => [x(t), y(baseline + value * scale)]);
      group.append(svgElement("path", {
        d: `${path([[points[0][0], y(baseline)], ...points, [points.at(-1)[0], y(baseline)]])} Z`, class: "density-fill",
      }));
      group.append(svgElement("path", { d: path(points), class: "data-line" }));
      if (points.length === 1) group.append(svgElement("circle", { cx: points[0][0], cy: points[0][1], r: 2 }));
    }
  };
}

function curveRows(curve) {
  return curve.calbp.map((time, i) => ({ time, mean: -curve.c14bp[i], error: curve.c14_sigma[i] }));
}
function visibleCurveRows(rows, domain) {
  // Include neighbours outside the viewport: narrow zooms must still show the
  // line crossing the viewport, even between two supplied curve points.
  let first = rows.findIndex(row => row.time >= domain[0]);
  if (first === -1) return [];
  first = Math.max(0, first - 1);
  let last = rows.findIndex(row => row.time > domain[1]);
  if (last === -1) last = rows.length - 1;
  if (last < first) return [];
  return rows.slice(first, last + 1);
}
function curveView(rows, domain) {
  const visible = visibleCurveRows(rows, domain);
  const fit = visible.length ? visible : rows;
  const high = Math.max(...fit.map(row => row.mean + row.error));
  const low = Math.min(...fit.map(row => row.mean - row.error));
  const padding = Math.max((high - low) * .08, 1);
  return { x: domain, y: [low - padding, high + padding] };
}

function drawCurveLayer(group, rows, x, y, domain, overlay = false) {
  const visible = visibleCurveRows(rows, domain);
  if (visible.length < 2) return;
  const upper = visible.map(row => [x(row.time), y(row.mean + row.error)]);
  const lower = visible.map(row => [x(row.time), y(row.mean - row.error)]).reverse();
  group.append(svgElement("path", { d: `${path([...upper, ...lower])} Z`, class: overlay ? "overlay-curve-band" : "curve-band" }));
  group.append(svgElement("path", { d: path(visible.map(row => [x(row.time), y(row.mean)])), class: overlay ? "overlay-curve-line" : "data-line" }));
}

function createStackedPlot(container, data) {
  // Means are supplied by the scientific engine. Only sorting, peak-height
  // scaling, and vertical offsets belong to this visualization layer.
  if (!data.results.every(result => Number.isFinite(result.posterior_mean))) {
    container.append(element("p", "stacked-description stacked-error", "Posterior means are unavailable. Recalibrate with the updated local API to enable the stacked view."));
    return null;
  }
  const ordered = data.results.map((result, index) => ({ result, index }))
    .sort((a, b) => a.result.posterior_mean - b.result.posterior_mean || a.index - b.index);
  const series = ordered.map(({ result, index }, rank) => {
    const peak = Math.max(...result.pdf_values);
    if (!(peak > 0)) throw new Error("A determination has no positive values to display in the stacked plot.");
    const baseline = ordered.length - rank - 1;
    return { result, index, baseline, draw: distributionRenderer(result, { baseline, scale: .8 / peak }) };
  });
  const tails = [
    Math.min(...series.map(({ result }) => result.t_values[0])),
    Math.max(...series.map(({ result }) => result.t_values.at(-1))),
  ];
  const fullView = { x: tails, y: [-.15, ordered.length - .05] };
  container.append(element("p", "stacked-description", "Ordered by posterior mean, oldest at top. Each density has the same peak height and a vertical offset; heights do not represent relative probability mass. Expand rows to inspect a crowded stack."));
  const plot = new InteractivePlot(container, {
    title: "Stacked determinations",
    subtitle: `${ordered.length} determinations · ${(data.curves ?? [data.curve]).join(" / ")} · Posterior-mean order, oldest at top · Equal peak heights`,
    exportNote: "Chronologer · Each density scaled to its own maximum, then vertically offset · Display scaling only",
    label: "Peak-scaled shapes",
    base: fullView, height: 520,
    rowTicks: series.map(({ result, baseline }) => ({
      value: baseline, label: result.id,
      detail: `${result.id} · ${result.curve ?? data.curve} · ${number(result.age)} ± ${number(result.error)} BP · Posterior mean ${number(-result.posterior_mean)} cal BP`,
    })),
    domainApplied: domain => plot.setBase({ x: domain, y: fullView.y }, "Custom domain"),
    fitAll: () => plot.setBase(fullView, "All returned tails"),
    draw: (group, x, y) => {
      for (const seriesItem of series) {
        const layer = svgElement("g", { "data-sample-index": seriesItem.index, "data-sample-id": seriesItem.result.id, "data-layer": "determination" });
        layer.append(svgElement("title", {}, seriesItem.result.id));
        seriesItem.draw(layer, x, y);
        group.append(layer);
      }
    },
  });
  plot.resetLabel = "All returned tails";
  plot.status.textContent = plot.resetLabel;
  return plot;
}

export function createPlotWorkspace(resultContainer, curveContainer) {
  let data = null, curve = null, curvePlot = null, stackedPlot = null;
  let plots = [], globalDomain = null;
  const stackedContainer = document.getElementById("stacked-plot");
  const viewTabs = [...document.querySelectorAll('.result-tabs > [role="tab"]')];
  function activateView(tab) {
    for (const item of viewTabs) {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute("aria-controls")).hidden = !selected;
    }
    if (tab.id === "stacked-view-tab") stackedPlot?.render();
    else plots.forEach(plot => plot.render());
  }
  viewTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateView(tab));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? viewTabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + viewTabs.length) % viewTabs.length;
      activateView(viewTabs[next]);
      viewTabs[next].focus();
    });
  });
  const toolbar = element("div", "global-domain-toolbar");
  toolbar.append(element("h3", "", "Shared calendar domain"));
  const globalControls = domainControls("All determinations", domain => {
    globalDomain = domain;
    applyGlobal();
  }, "Apply to all");
  globalControls.add(button("Auto domain", () => { globalDomain = null; applyGlobal(); }));
  globalControls.add(button("Reset all views", () => {
    plots.forEach(plot => plot.reset());
    curvePlot?.reset();
    stackedPlot?.reset();
  }));
  for (const [label, open] of [["Collapse all", false], ["Expand all", true]]) {
    globalControls.add(button(label, () => {
      resultContainer.querySelectorAll("details.sample-plot").forEach(section => { section.open = open; });
    }, `${label} individual sample plots`));
  }
  toolbar.append(globalControls.node, element("p", "help", "Applied to every determination initially. Apply to all replaces individual domains. Drag to pan both axes; scroll or pinch to zoom. Reset restores configured limits."));
  resultContainer.parentElement.querySelector(".empty-state").before(toolbar);

  function sharedDomain() { return globalDomain ?? (data ? resultDomain(data.results) : null); }
  function sharedY() { return [0, Math.max(...data.results.map(result => Math.max(...result.pdf_values))) * 1.1]; }
  function applyGlobal() {
    const domain = sharedDomain();
    globalControls.set(domain);
    if (!data) return;
    plots.forEach(plot => plot.setBase({ x: domain, y: sharedY() }, "Global domain"));
  }
  function updateCurve() {
    curvePlot?.dispose();
    curvePlot = null;
    curveContainer.replaceChildren();
    if (!curve) return;
    const rows = curveRows(curve);
    const matching = data?.results.filter(result => (result.curve ?? data.curve) === curve.id) ?? [];
    const domain = matching.length ? resultDomain(matching) : [rows[0].time, rows.at(-1).time];
    curvePlot = new InteractivePlot(curveContainer, {
      title: `${curve.id} calibration curve`, label: "Radiocarbon age · BP",
      subtitle: `${curve.id} · Curve mean and ±1σ uncertainty`,
      base: curveView(rows, domain), height: 280,
      domainApplied: domain => curvePlot.setBase(curveView(rows, domain), "Custom domain"),
      draw: (group, x, y, domain) => drawCurveLayer(group, rows, x, y, domain),
    });
    curveContainer.append(element("p", "help", "Calendar age · cal BP (before AD 1950) · Older ← → Younger. Drag to pan; scroll or pinch to zoom."));
  }
  return {
    clearResults() {
      data = null;
      globalDomain = null;
      plots.forEach(plot => plot.dispose());
      plots = [];
      resultContainer.replaceChildren();
      stackedPlot?.dispose();
      stackedPlot = null;
      stackedContainer.replaceChildren();
      document.getElementById("stacked-empty").hidden = false;
      globalControls.set(null);
      updateCurve();
    },
    setResults(results, curves = {}) {
      data = results;
      plots.forEach(plot => plot.dispose());
      plots = [];
      resultContainer.replaceChildren();
      globalControls.set(sharedDomain());
      for (const result of data.results) {
        const curveId = result.curve ?? data.curve;
        const matchingCurve = curves[curveId] ?? (curve?.id === curveId ? curve : null);
        const section = element("details", "sample-plot");
        section.open = true;
        const caption = element("summary", "sample-caption");
        caption.append(element("strong", "sample-name", result.id),
          element("span", "radiocarbon-text", `Uncalibrated: ${number(result.age)} ± ${number(result.error)} ¹⁴C BP (mean ± SD)`),
          element("span", "collapsed-calibrated-summary", calibratedSummary(result)));
        section.append(caption);
        const body = element("div", "sample-plot-body");
        body.append(element("p", "help radiocarbon-text", `Calibration curve: ${curveId}`));
        section.append(body);
        resultContainer.append(section);
        const plot = new InteractivePlot(body, {
          title: result.id, label: data.value_label,
          subtitle: `${number(result.age)} ± ${number(result.error)} BP · ${curveId}`,
          overlayRows: matchingCurve ? curveRows(matchingCurve) : null,
          determination: result,
          base: { x: sharedDomain(), y: sharedY() },
          height: data.results.length === 1 ? 310 : 210,
          draw: distributionRenderer(result),
          domainApplied: domain => plot.setBase({ x: domain, y: sharedY() }, "Custom domain"),
          useGlobal: () => plot.setBase({ x: sharedDomain(), y: sharedY() }, "Global domain"),
        });
        plot.resetLabel = "Global domain";
        plot.status.textContent = "Global domain";
        section.addEventListener("toggle", () => { if (section.open) plot.render(); });
        plots.push(plot);
      }
      stackedPlot?.dispose();
      stackedContainer.replaceChildren();
      document.getElementById("stacked-empty").hidden = true;
      stackedPlot = createStackedPlot(stackedContainer, data);
      updateCurve();
    },
    setCurve(value) { curve = value; updateCurve(); },
  };
}

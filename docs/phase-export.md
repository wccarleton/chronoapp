# Schematic phase map export

Use **Export phase map SVG** in the Phase builder to download the entire model,
including nodes outside the visible canvas. Export uses stored canvas positions;
pan, zoom, collapsed cards and inference results do not affect the diagram.

Each phase is a distribution silhouette with its name inscribed and its selected
quantile anchors marked. Uniform endpoints are exact icon limits. Normal anchors
use standardized normal quantiles; finite tails are schematic, extending to
include extreme anchors. The shapes reuse the builder's distribution profiles.
Increasing quantiles run upwards: older below, younger above.

Explicit edges connect the source's younger (or sole) anchor to the target's older
(or sole) anchor. Disabled connections are dashed and labelled inactive. Layout
does not define ordering; no automatic graph layout changes the user's arrangement.
Shapes, positions, sizes and spacings express no fitted dates, durations or gaps.
Invalid anchors must be corrected before exporting.

The SVG is standalone, with explicit colors and no external assets. Its timeline,
connections, phases, labels and anchor marks are separate editable groups. Each
phase group retains its stable ID in `data-phase-id`; edges retain `data-source`
and `data-target`. Metadata records the phase specs, edges and enabled state.
Open it in a vector editor to isolate portions or arrange them across pages.

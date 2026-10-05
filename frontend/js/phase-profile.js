// Presentation-only distribution silhouettes, shared by cards and SVG export.
export const profiles = {
  uniform: { label: 'Uniform', width: () => 1 },
  normal: { label: 'Gaussian / Normal', width: t => Math.exp(-.5 * ((t - .5) / .15) ** 2) },
};
export function profilePath(type, { x = 12, y = 10, width = 75, height = 100, extent = 10 / 3 } = {}) {
  const points = Array.from({ length: 121 }, (_, i) => {
    const t = i / 120;
    const density = type === 'normal' ? Math.exp(-.5 * ((2 * t - 1) * extent) ** 2) : 1;
    return `${(x + width * density).toFixed(3)},${(y + t * height).toFixed(3)}`;
  });
  return `M${x},${y} L${points.join(' L')} L${x},${y + height} Z`;
}

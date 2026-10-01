# Local export assets

PDF export uses the pinned browser distributions of
[jsPDF](https://github.com/parallax/jsPDF) (4.2.1) and
[svg2pdf.js](https://github.com/yWorks/svg2pdf.js) (2.8.1).
Both are MIT licensed; their license files are included here. These prebuilt
scripts load only when exporting PDF. There is no Node/npm installation, build
step, or runtime CDN request.

DejaVu Sans regular and bold fonts are copied from the development environment's
Matplotlib distribution. Their redistribution license is `LICENSE_DEJAVU`.
SVG embeds the fonts with editable text elements; PDF embeds subsets with text
operators. PNG is rasterized at three times the figure's SVG dimensions.

`manifest.json` records exact upstream package versions, archive integrity, and
SHA-256 hashes of the bundled files. To reproduce the assets, run:

```powershell
conda run -n chronoapp python scripts/vendor_export_assets.py
```

The script downloads the pinned npm release archives directly, checks registry
integrity, and reads only the required named files. It does not run package code
or invoke npm. Font files are taken from the active Matplotlib installation.

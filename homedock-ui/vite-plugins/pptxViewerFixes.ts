// homedock-ui/vite-plugins/pptxViewerFixes.ts
// Copyright © 2023-2026 Banshee, All Rights Reserved
// See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
// https://www.banshee.pro

import type { Plugin } from "vite";

const NAME = "homedock:pptx-viewer-fixes";

const TARGET = /[\\/]pptx-viewer[\\/]dist[\\/][^\\/]+\.js$/;

const REPLACEMENTS: [string, string][] = [
  ["if (l.includes(i) || i.includes(l))", 'if (l.split("/").pop() === i.split("/").pop())'],
  ["f = lr(l, t.themeColors), p = Ee(l, t.themeColors)", "f = lr(l, t.themeColors) ?? mr(l, t), p = Ee(l, t.themeColors)"],
  [
    'i.setAttribute("href", t.src), i.setAttribute("width", "100%"), i.setAttribute("height", "100%"), i.setAttribute("preserveAspectRatio", "xMidYMid slice"), s.appendChild(i)',
    's.setAttribute("patternContentUnits", "objectBoundingBox"), i.setAttribute("href", t.src), i.setAttribute("x", String(t.fillRect?.l ?? 0)), i.setAttribute("y", String(t.fillRect?.t ?? 0)), i.setAttribute("width", String(1 - (t.fillRect?.l ?? 0) - (t.fillRect?.r ?? 0))), i.setAttribute("height", String(1 - (t.fillRect?.t ?? 0) - (t.fillRect?.b ?? 0))), i.setAttribute("preserveAspectRatio", "none"), t.opacity != null && i.setAttribute("opacity", String(t.opacity)), s.appendChild(i)',
  ],
  [
    'mode: "cover"',
    'mode: "cover",\n              opacity: gr(i),\n              fillRect: ((st) => (st = st && h(st, "fillRect")) ? { l: C(st, "l", 0) / 1e5, t: C(st, "t", 0) / 1e5, r: C(st, "r", 0) / 1e5, b: C(st, "b", 0) / 1e5 } : null)(h(s, "stretch"))',
  ],
  ["return At(s) / 16;", "return -At(s);"],
  ["const o = e.lineSpacing * (1 - n.lineSpacingReduction);", "const o = Math.abs(e.lineSpacing) * (1 - n.lineSpacingReduction);"],
  ["r.style.lineHeight = String(Math.max(o, 0.8));", "r.style.lineHeight = e.lineSpacing < 0 ? `${o}px` : String(Math.max(o, 0.8));"],
];

interface PatchContext {
  warn(message: string): void;
}

function patch(this: PatchContext, code: string, id: string) {
  if (!TARGET.test(id)) return null;

  let patched = code;

  for (const [from, to] of REPLACEMENTS) {
    if (!patched.includes(from)) {
      this.warn(`${id} no longer contains "${from}"; check whether ${NAME} still applies after the pptx-viewer upgrade.`);
      continue;
    }
    patched = patched.split(from).join(to);
  }

  return patched === code ? null : { code: patched, map: null };
}

export default function pptxViewerFixes(): Plugin {
  return {
    name: NAME,
    enforce: "pre",
    config() {
      return {
        optimizeDeps: {
          rolldownOptions: {
            plugins: [{ name: NAME, transform: patch }],
          },
        },
      };
    },
    transform: patch,
  };
}

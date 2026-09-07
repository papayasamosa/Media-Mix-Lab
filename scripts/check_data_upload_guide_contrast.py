"""Small Playwright accessibility check for the self-contained upload guide.

Usage:
    python scripts/check_data_upload_guide_contrast.py http://127.0.0.1:8765/Ancestry_MMM_Data_Upload_Guide.html

The check intentionally audits rendered text, not just the CSS source. It
walks transparent ancestors to find an effective solid background, treats
opaque gradients conservatively, and reports every rendered text failure.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from playwright.async_api import async_playwright


AUDIT_JS = r"""
() => {
  const ignored = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'PATH']);
  const clamp = value => Math.max(0, Math.min(1, value));
  const parseColor = value => {
    const match = value.match(/rgba?\(([^)]+)\)/i);
    if (!match) return null;
    const parts = match[1].split(',').map(part => part.trim());
    if (parts.length < 3) return null;
    const channel = part => part.endsWith('%') ? Number(part.slice(0, -1)) * 2.55 : Number(part);
    return {r: channel(parts[0]), g: channel(parts[1]), b: channel(parts[2]), a: parts[3] === undefined ? 1 : Number(parts[3])};
  };
  const composite = (front, back) => {
    const a = clamp(front.a);
    return {r: front.r * a + back.r * (1 - a), g: front.g * a + back.g * (1 - a), b: front.b * a + back.b * (1 - a), a: 1};
  };
  const effectiveBackground = element => {
    let node = element;
    let result = {r: 255, g: 255, b: 255, a: 1};
    const chain = [];
    while (node && node.nodeType === 1) {
      const style = getComputedStyle(node);
      const color = parseColor(style.backgroundColor);
      if (color && color.a > 0) chain.push(color);
      node = node.parentElement;
    }
    for (let index = chain.length - 1; index >= 0; index -= 1) result = composite(chain[index], result);
    return result;
  };
  const luminance = color => {
    const channel = value => { const v = value / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
  };
  const contrast = (foreground, background) => {
    const light = Math.max(luminance(foreground), luminance(background));
    const dark = Math.min(luminance(foreground), luminance(background));
    return (light + 0.05) / (dark + 0.05);
  };
  const selector = element => {
    if (element.id) return `#${element.id}`;
    const classes = [...element.classList].slice(0, 2).map(name => `.${name}`).join('');
    return element.tagName.toLowerCase() + classes;
  };
  const entries = [];
  for (const element of document.querySelectorAll('body *')) {
    if (ignored.has(element.tagName)) continue;
    const style = getComputedStyle(element);
    const box = element.getBoundingClientRect();
    const directText = [...element.childNodes].filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join(' ').replace(/\s+/g, ' ').trim();
    if (!directText || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0 || box.width === 0 || box.height === 0) continue;
    const foreground = parseColor(style.color);
    if (!foreground) continue;
    const background = effectiveBackground(element);
    const ratio = contrast(foreground, background);
    const fontSize = Number.parseFloat(style.fontSize);
    const large = fontSize >= 24 || (fontSize >= 18.66 && Number.parseInt(style.fontWeight, 10) >= 700);
    const threshold = large ? 3 : 4.5;
    entries.push({selector: selector(element), sample: directText.slice(0, 120), ratio: Number(ratio.toFixed(2)), threshold, foreground: style.color, background: `rgb(${Math.round(background.r)}, ${Math.round(background.g)}, ${Math.round(background.b)})`, fontSize, large});
  }
  const anchors = [...document.querySelectorAll('a[href^="#"]')].map(link => link.getAttribute('href').slice(1));
  const missingAnchors = [...new Set(anchors.filter(id => id && !document.getElementById(id)))];
  const ids = [...document.querySelectorAll('[id]')].map(element => element.id);
  const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
  return {failures: entries.filter(entry => entry.ratio < entry.threshold), audited: entries.length, missingAnchors, duplicateIds};
}
"""


async def run(url: str) -> dict[str, Any]:
    console_errors: list[str] = []
    page_errors: list[str] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on(
            "console",
            lambda message: (
                console_errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        await page.goto(url, wait_until="networkidle")
        audit = await page.evaluate(AUDIT_JS)
        details = page.locator("#faq details").first
        await details.click()
        faq_open = await details.evaluate("element => element.open")
        search = page.locator("#guideSearch")
        await search.fill("outcome completeness")
        search_works = (
            await page.locator("#outcomes").is_visible()
            and not await page.locator("#activity").is_visible()
        )
        viewport_results = []
        for width, height in [(1440, 900), (1280, 720), (390, 844)]:
            await page.set_viewport_size({"width": width, "height": height})
            await page.reload(wait_until="networkidle")
            overflow = await page.evaluate(
                "document.documentElement.scrollWidth > window.innerWidth"
            )
            viewport_results.append(
                {"width": width, "height": height, "horizontal_overflow": overflow}
            )
        await browser.close()
    return {
        "audit": audit,
        "console_errors": console_errors,
        "page_errors": page_errors,
        "faq_open": faq_open,
        "search_works": search_works,
        "viewports": viewport_results,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "usage: python scripts/check_data_upload_guide_contrast.py URL",
            file=sys.stderr,
        )
        return 2
    result = asyncio.run(run(sys.argv[1]))
    print(json.dumps(result, indent=2))
    audit = result["audit"]
    failed = bool(
        audit["failures"]
        or audit["missingAnchors"]
        or audit["duplicateIds"]
        or result["console_errors"]
        or result["page_errors"]
        or not result["faq_open"]
        or not result["search_works"]
        or any(item["horizontal_overflow"] for item in result["viewports"])
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

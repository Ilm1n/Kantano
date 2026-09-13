import assert from "node:assert/strict";
import { readFile, access } from "node:fs/promises";
import { JSDOM } from "jsdom";

const html = await readFile("dist/index.html", "utf8");
const document = new JSDOM(html).window.document;
assert.equal(document.querySelectorAll("h1").length, 1);
assert.match(document.querySelector("h1").textContent, /Свои задачи/);
for (const id of ["features", "scenarios", "pricing", "faq"])
  assert.ok(document.getElementById(id));
assert.equal(document.querySelectorAll("#faq details").length, 6);
assert.equal(
  document.querySelector('link[rel="canonical"]').href,
  "https://kantano.ru/",
);
assert.ok(document.querySelector('link[rel="stylesheet"]'));
assert.ok(document.querySelector('a[href="/register"]'));
assert.doesNotMatch(
  html,
  /aggregateRating|ratingCount|FAQPage|SELECTEL|AVITO|OZON|1,000|Умные теги|1200|490₽/,
);
for (const script of document.querySelectorAll(
  'script[type="application/ld+json"]',
))
  JSON.parse(script.textContent);
for (const element of document.querySelectorAll(
  'img[src], source[srcset], script[src], link[rel="stylesheet"]',
)) {
  const url = element.getAttribute("src") ?? element.getAttribute("srcset") ?? element.getAttribute("href");
  if (url?.startsWith("/")) await access(`dist${url}`);
}
const app = await readFile("dist/app.html", "utf8");
assert.match(app, /noindex/);
assert.doesNotMatch(app, /canonical|application\/ld\+json|og:description/);
console.log("Landing HTML and SPA metadata contract verified.");

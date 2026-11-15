/* GenUI DSL 渲染测试入口：读取 stdin 的 {source,state}，输出 {html|error} */
'use strict';
const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '..', '..', 'ui', 'web-minimal', 'plugins', 'builtin', 'builtin-history', 'genui');
const files = [
  'core.js', 'functions.js', 'render.js', 'media.js', 'components-common.js',
  'components-text.js', 'components-input.js', 'components-data.js',
  'components-chart.js', 'components-draw.js', 'index.js'
];
files.forEach((name) => require(path.join(dir, name)));

const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const G = globalThis.PurrCatGenUI;
const result = {};
try {
  if (Array.isArray(payload.media)) {
    result.media = payload.media.map((src) => {
      const kind = G.media.kind(src);
      return {
        kind,
        local: G.media.isLocal(src),
        url: G.media.resolve(src),
        html: G.media.embedHTML('', src, kind),
        genui: G.media.genuiHTML('', src)
      };
    });
  } else {
    result.html = G.renderHTML(payload.source, payload.state || {});
  }
} catch (err) {
  result.error = String((err && err.message) || err);
}
process.stdout.write(JSON.stringify(result));

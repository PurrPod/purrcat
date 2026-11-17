/* Note 插件纯逻辑测试入口：读取 stdin 的 {op,args}，输出调用结果 */
'use strict';
const fs = require('fs');
const path = require('path');

const core = require(path.join(
  __dirname, '..', '..', 'ui', 'web-minimal', 'plugins', 'builtin', 'builtin-note', 'core.js'
));

const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const fn = core[payload.op];
let result;
try {
  if (typeof fn !== 'function') throw new Error('未知 op: ' + payload.op);
  result = fn.apply(null, payload.args || []);
} catch (err) {
  result = { error: String((err && err.message) || err) };
}
process.stdout.write(JSON.stringify(result));

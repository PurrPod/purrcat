#!/usr/bin/env node
// 从 node_modules 生成内置插件共享运行时（ui/web-minimal/shared），
// 由 postinstall 自动触发；shared 目录本身不进版本库。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const modules = path.join(root, 'node_modules');
const sharedDir = path.join(root, 'ui', 'web-minimal', 'shared');

function versionOf(pkg) {
  const file = path.join(modules, pkg, 'package.json');
  if (!fs.existsSync(file)) {
    throw new Error(`缺少 ${pkg}：请先运行 npm install`);
  }
  return JSON.parse(fs.readFileSync(file, 'utf8')).version;
}

function copyFile(from, to) {
  if (!fs.existsSync(from)) {
    throw new Error(`缺少源文件：${from}`);
  }
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
}

const markedVersion = versionOf('marked');
const katexVersion = versionOf('katex');
const highlightVersion = versionOf('@highlightjs/cdn-assets');

const markedSource = path.join(modules, 'marked', 'lib', 'marked.umd.js');
const katexSource = path.join(modules, 'katex', 'dist');
const highlightSource = path.join(modules, '@highlightjs', 'cdn-assets');

for (const file of [
  markedSource,
  path.join(katexSource, 'katex.min.js'),
  path.join(katexSource, 'katex.min.css'),
  path.join(highlightSource, 'highlight.min.js'),
  path.join(highlightSource, 'styles', 'github.min.css'),
]) {
  if (!fs.existsSync(file)) {
    throw new Error(`缺少源文件：${file}`);
  }
}

fs.rmSync(sharedDir, { recursive: true, force: true });
fs.mkdirSync(sharedDir, { recursive: true });

const markedDir = path.join(sharedDir, 'marked', markedVersion);
copyFile(markedSource, path.join(markedDir, 'marked.min.js'));

const katexDir = path.join(sharedDir, 'katex', katexVersion);
copyFile(path.join(katexSource, 'katex.min.js'), path.join(katexDir, 'katex.min.js'));
copyFile(path.join(katexSource, 'katex.min.css'), path.join(katexDir, 'katex.min.css'));
for (const font of fs.readdirSync(path.join(katexSource, 'fonts'))) {
  if (font.endsWith('.woff2')) {
    copyFile(path.join(katexSource, 'fonts', font), path.join(katexDir, 'fonts', font));
  }
}

const highlightDir = path.join(sharedDir, 'highlight', highlightVersion);
copyFile(
  path.join(highlightSource, 'highlight.min.js'),
  path.join(highlightDir, 'highlight.min.js')
);
copyFile(
  path.join(highlightSource, 'styles', 'github.min.css'),
  path.join(highlightDir, 'github.min.css')
);

const manifest = {
  marked: { version: markedVersion, base: `/minimal/shared/marked/${markedVersion}` },
  katex: { version: katexVersion, base: `/minimal/shared/katex/${katexVersion}` },
  highlight: {
    version: highlightVersion,
    base: `/minimal/shared/highlight/${highlightVersion}`,
  },
};
fs.writeFileSync(
  path.join(sharedDir, 'manifest.json'),
  `${JSON.stringify(manifest, null, 2)}\n`,
  'utf8'
);

console.log(`[sync-vendor] 共享运行时已生成：${path.relative(root, sharedDir)}`);

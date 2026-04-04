import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const AGENT_VM_DIR = path.join(process.cwd(), '../agent_vm');

function buildTree(dirPath: string, relativePath: string = '') {
  const tree: any[] = [];
  try {
    if (!fs.existsSync(dirPath)) fs.mkdirSync(dirPath, { recursive: true });
    const items = fs.readdirSync(dirPath);
    for (const item of items.sort()) {
      if (item.startsWith('.') || item === '__pycache__' || item === 'miniconda3' || item === 'node_modules') continue;
      const fullPath = path.join(dirPath, item);
      const itemRelPath = path.join(relativePath, item).replace(/\\/g, '/');
      
      let isDir: boolean;
      try {
        isDir = fs.statSync(fullPath).isDirectory();
      } catch {
        continue;
      }

      if (isDir) {
        tree.push({
          name: item,
          type: 'folder',
          path: `/agent_vm/${itemRelPath}`,
          children: buildTree(fullPath, itemRelPath)
        });
      } else {
        tree.push({
          name: item,
          type: 'file',
          path: `/agent_vm/${itemRelPath}`
        });
      }
    }
  } catch (e) {
    console.error("Error building tree:", e);
  }
  return tree;
}

export async function GET(req: NextRequest) {
  if (!fs.existsSync(AGENT_VM_DIR)) {
    fs.mkdirSync(AGENT_VM_DIR, { recursive: true });
  }

  const children = buildTree(AGENT_VM_DIR);
  const data = [{
    name: 'agent_vm',
    type: 'folder',
    path: '/agent_vm',
    children
  }];

  return NextResponse.json(data);
}

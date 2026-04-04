import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';

const AGENT_VM_DIR = path.join(process.cwd(), '../agent_vm');
const MAX_FILE_SIZE = 5 * 1024 * 1024;

function isBinaryFile(buffer: Buffer): boolean {
  for (let i = 0; i < Math.min(8192, buffer.length); i++) {
    if (buffer[i] === 0) return true;
  }
  return false;
}

export async function GET(req: NextRequest) {
  const filePath = req.nextUrl.searchParams.get('path');
  if (!filePath || !filePath.startsWith('/agent_vm/')) {
    return NextResponse.json({ error: 'Invalid path' }, { status: 400 });
  }

  const relativePath = filePath.replace(/^\/agent_vm\//, '');
  const fullPath = path.join(AGENT_VM_DIR, relativePath);

  try {
    const stats = await fs.stat(fullPath);
    if (stats.size > MAX_FILE_SIZE) {
      return NextResponse.json({ 
        content: `[文件过大，无法预览]\n文件大小: ${(stats.size / 1024 / 1024).toFixed(2)} MB\n限制: 5 MB`,
        truncated: true 
      });
    }

    const buffer = await fs.readFile(fullPath);
    if (isBinaryFile(buffer)) {
      return NextResponse.json({ 
        content: `[二进制文件，无法预览]\n文件大小: ${(stats.size / 1024).toFixed(2)} KB`,
        binary: true 
      });
    }

    const content = buffer.toString('utf-8');
    return NextResponse.json({ content });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  const { path: filePath, content } = await req.json();
  if (!filePath || !filePath.startsWith('/agent_vm/')) {
    return NextResponse.json({ error: 'Invalid path' }, { status: 400 });
  }

  const relativePath = filePath.replace(/^\/agent_vm\//, '');
  const fullPath = path.join(AGENT_VM_DIR, relativePath);

  try {
    await fs.mkdir(path.dirname(fullPath), { recursive: true });
    await fs.writeFile(fullPath, content, 'utf-8');
    return NextResponse.json({ status: 'success' });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

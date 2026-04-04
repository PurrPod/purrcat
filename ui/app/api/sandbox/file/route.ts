import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';

const AGENT_VM_DIR = path.join(process.cwd(), '../agent_vm');

export async function GET(req: NextRequest) {
  const filePath = req.nextUrl.searchParams.get('path');
  if (!filePath || !filePath.startsWith('/agent_vm/')) {
    return NextResponse.json({ error: 'Invalid path' }, { status: 400 });
  }

  const relativePath = filePath.replace(/^\/agent_vm\//, '');
  const fullPath = path.join(AGENT_VM_DIR, relativePath);

  try {
    const content = await fs.readFile(fullPath, 'utf-8');
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

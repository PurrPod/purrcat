// 宿主与后端 webmin 接口的共享类型（仅类型，运行时不产出任何代码）

export type PluginRoot = 'builtin' | 'sandbox' | 'user' | '';

export interface SlotSize {
  w?: string | number;
  h?: string | number;
}

export interface SlotDef {
  type?: 'fixed' | 'panel' | 'float' | 'modal' | string;
  area?: string;
  size?: SlotSize;
  center?: boolean;
  [key: string]: unknown;
}

export interface ConfigFieldOption {
  label?: string;
  value?: unknown;
  [key: string]: unknown;
}

export interface ConfigField {
  key: string;
  label?: string;
  type?: 'switch' | 'range' | 'select' | 'text' | 'number' | 'textarea' | 'json' | 'action' | string;
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
  options?: Array<ConfigFieldOption | string>;
  hint?: string;
  placeholder?: string;
  unit?: string;
  [key: string]: unknown;
}

export interface PluginDependency {
  type: string;
  id: string;
}

export interface PluginRequire {
  name: string;
  range?: string;
  version?: string;
  base?: string;
}

export interface PluginBackend {
  kind?: string;
  entry?: string;
  running?: boolean;
  [key: string]: unknown;
}

/** /api/webmin/manifest 返回的单条插件描述（后端已做归一化） */
export interface PluginDescriptor {
  id: string;
  name?: string;
  icon?: string;
  entry?: string;
  root?: PluginRoot;
  origin?: PluginRoot;
  rootOk?: boolean;
  builtin?: boolean;
  /** 归一化后的槽 id（fixed 区域名 / panel / float:xxx / modal） */
  slot?: string;
  slotDef?: SlotDef;
  configSchema?: ConfigField[];
  config?: Record<string, unknown>;
  backend?: PluginBackend | null;
  dependency?: PluginDependency[];
  requires?: PluginRequire[];
  dir?: string;
  [key: string]: unknown;
}

export interface SharedRuntime {
  version: string;
  base: string;
}

export interface RailState {
  stage: 0 | 1;
  hidden: Record<string, boolean>;
  opacity: number;
}

export interface PanelContainerStored {
  opacity?: number;
  width?: number | null;
  [key: string]: unknown;
}

export interface WebminManifest {
  plugins: PluginDescriptor[];
  shared?: Record<string, SharedRuntime>;
  rail?: RailState;
  panelContainer?: PanelContainerStored;
  active?: Record<string, string>;
}

/** iframe 实例：slot -> [ { iframe, pluginId, el } ] */
export interface PluginFrame {
  iframe?: HTMLIFrameElement;
  pluginId: string;
  el: HTMLElement;
  [key: string]: unknown;
}

export interface SessionSummary {
  id: string;
  title?: string;
  project_id?: string;
  branch_id?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface GroupState {
  activeSessionId: string;
  activeBranchId: string;
  sessions: SessionSummary[];
  empty: boolean;
  draft: boolean;
  draftParadigm: string;
  draftProjectId: string;
  plugins: PluginDescriptor[];
}

/** 动作来源：由 callAction 从 iframe 消息反查得到 */
export interface ActionOrigin {
  slot: string | null;
  pluginId: string | null;
  inst: HTMLElement | null;
  iframe: HTMLIFrameElement | null;
}

/** Electron preload 暴露的本地能力（普通浏览器下为 undefined） */
export interface PurrCatBridge {
  winMinimize?(): void;
  winToggleMaximize?(): void;
  winClose?(): void;
  onTabEvent?(cb: (evt: unknown) => void): void;
  onOpenUrl?(cb: (url: string) => void): void;
  openDialog?(opts: {
    directory?: boolean;
    properties?: string[];
    filters?: Array<{ name: string; extensions: string[] }>;
  }): Promise<unknown>;
  getPathForFile?(file: File): string;
  browserNewTab?(url: string): Promise<string>;
  browserSetBounds?(x: number, y: number, w: number, h: number, scale?: number): Promise<unknown>;
  browserHide?(): Promise<void>;
  browserCloseTab?(tabId: string, nextTabId?: string): Promise<void>;
  browserSwitchTab?(tabId: string): Promise<void>;
  browserNavigate?(tabId: string, url: string): Promise<void>;
  browserReload?(tabId: string): Promise<void>;
  browserGoBack?(tabId: string): Promise<void>;
  browserGoForward?(tabId: string): Promise<void>;
  browserPickStart?(tabId: string): Promise<unknown>;
  browserPickEnd?(tabId: string): Promise<void>;
  browserLocate?(tabId: string, x: number, y: number): Promise<unknown>;
  browserCdpPickElement?(tabId: string, x: number, y: number): Promise<unknown>;
  openExternal?(url: string): Promise<void>;
  [key: string]: unknown;
}

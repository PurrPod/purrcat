// 全局状态与常量（slot 索引、配置缓存、会话/图标栏状态）
import type {
  GroupState,
  PluginDescriptor,
  PluginFrame,
  RailState,
} from './types.js';

  export const HOST = window;

  // --- 状态 ---
  // slot 仅声明「窗口类型」，由各插件 plugin.json 的 slot 动态建立，host 不再写死槽位表：
  //   * fixed  —— 锚定单例，同 area 只取第一个插件生效（input/conversation/sidebar/background）
  //   * panel  —— 与聊天区并排的分栏面板：无面板插件则不占位；有则在右上角抽屉里切换显示
  //   * float  —— 弹窗，多插件各自独立、可拖拽可缩放
  //   slotMap[slotId]      -> 声明该窗口的插件列表
  //   pluginBySlot[slotId] -> slot -> primary descriptor（兼容既有读取点）
  //   frames[slotId]       -> slot -> [ {iframe, pluginId, el} ]
  //   slotByPluginId / frameByPluginId -> 由插件反查其所在槽/实例
  export const slotMap: Record<string, PluginDescriptor[]> = {};
  export const pluginBySlot: Record<string, PluginDescriptor> = {};
  export let frames: Record<string, PluginFrame[]> = {};
  export const configByPlugin: Record<string, Record<string, unknown>> = {};  // plugin_id -> 有效配置（默认值 ∪ 已存值）
  export const slotByPluginId: Record<string, string> = {};  // plugin_id -> slotId
  export const frameByPluginId: Record<string, HTMLIFrameElement> = {}; // plugin_id -> iframe element
  export const groupState: GroupState = {
    activeSessionId: '',
    activeBranchId: 'main',   // 当前查看的分支视图（main / 子代理分支），供输入框判定只读
    sessions: [],
    empty: true,
    // 草稿态：点「新建会话」后不落盘、不进列表，仅前端占位欢迎界面；
    // 首条消息发送时才按 draftParadigm 建会话并生成系统提示词。
    draft: false,
    draftParadigm: '',
    draftProjectId: '',       // 草稿态所属项目（从项目内新建时携带，用于注入 MEMORY.md 路径）
    plugins: [],              // manifest 注解后的插件列表（供设置面板使用）
  };
  // 最左图标栏状态：stage 0=仅图标 1=图标+文字；hidden=各插件隐藏开关（持久化）；opacity=白条透明度
  export const railState: RailState = { stage: 0, hidden: {}, opacity: 1 };
  export const railButtons: Record<string, HTMLElement> = {};   // plugin_id -> 图标栏按钮元素（供即时刷新高亮）
  // 单例槽当前选中的插件（fixed: {area: plugin_id}；panel 容器: {panel: plugin_id|'__none__'}）。
  // 由后端 webminConfig.active 持久化，重启后恢复用户上次的选择。
  export const activeBySlot: Record<string, string> = {};


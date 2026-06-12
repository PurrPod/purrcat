export interface PortDefinition {
  name: string;
  type: string;
  description?: string;
  required?: boolean;
}

export interface ConfigField {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'textarea';
  label: string;
  default?: string | number | boolean;
  options?: { label: string; value: string }[];
  placeholder?: string;
}

export interface NodeDefinition {
  type: string;
  name: string;
  label?: string;
  description?: string;
  color?: string;
  category?: string;
  inputs: PortDefinition[];
  outputs: PortDefinition[];
  config: ConfigField[];
}

export interface GraphNode {
  id: string;
  type: string;
  data: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  sourceHandle: string;
  targetHandle: string;
}

export interface GraphExport {
  version: string;
  name: string;
  description: string;
  global_schema: Record<string, any>;
  nodes: any[];
  edges: any[];
  dependencies?: {
    skills: string[];
    mcps: string[];
  };
}

export interface CatalogItem {
  type: string;
  name: string;
  label?: string;
  description?: string;
  color?: string;
  category?: string;
  inputs: PortDefinition[];
  outputs: PortDefinition[];
  config: ConfigField[];
  isCustom?: boolean;
}

export type NodeType = 'task_input' | 'task_output' | 'default';
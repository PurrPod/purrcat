import os
import sys
import pickle
import networkx as nx

# 添加项目根目录到 sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.memory.purrmemo.core.config import GRAPH_DATABASE_CONFIG
from src.utils.config import MEMORY_DIR


class GraphVisualizer:
    def __init__(self):
        self.graph_path = GRAPH_DATABASE_CONFIG['graph_path']
        self.graph = None
        self._load_graph()

    def _load_graph(self):
        """加载图谱"""
        try:
            if os.path.exists(self.graph_path):
                with open(self.graph_path, 'rb') as f:
                    self.graph = pickle.load(f)
                print(f"成功加载图谱，包含 {self.graph.number_of_nodes()} 个节点和 {self.graph.number_of_edges()} 条边")
            else:
                print("图谱文件不存在")
                self.graph = nx.DiGraph()
        except Exception as e:
            print(f"加载图谱失败: {e}")
            self.graph = nx.DiGraph()

    def visualize(self, output_file=None):
        """可视化图谱

        Args:
            output_file: 输出 HTML 文件路径，默认为 data/memo/output/graph_visualization.html
        """
        if output_file is None:
            output_file = os.path.join(MEMORY_DIR, "output", "graph_visualization.html")
        if not self.graph or self.graph.number_of_nodes() == 0:
            print("图谱为空，无法可视化")
            return
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        try:
            from pyvis.network import Network
            
            # 创建 pyvis 网络
            net = Network(
                notebook=False,
                directed=True,
                width="100%",
                height="800px",
                bgcolor="#ffffff",
                font_color="#333333"
            )
            
            # 添加节点
            for node_id in self.graph.nodes:
                node_data = self.graph.nodes[node_id]
                node_name = node_data.get('name', node_id)
                net.add_node(
                    node_id,
                    label=node_name,
                    title=f"节点: {node_name}",
                    color="#6495ED",
                    size=20
                )
            
            # 添加边
            for source, target, edge_data in self.graph.edges(data=True):
                relation = edge_data.get('relation_meaning', 'unknown')
                confidence = edge_data.get('confidence', 0.5)
                updated_at = edge_data.get('updated_at', 'unknown')
                
                # 根据置信度设置边的宽度和不透明度
                width = 1 + confidence * 3  # 宽度范围 1-4
                opacity = 0.3 + confidence * 0.7  # 不透明度范围 0.3-1.0
                
                net.add_edge(
                    source,
                    target,
                    label=relation,
                    title=f"关系: {relation}\n置信度: {confidence:.2f}\n更新时间: {updated_at}",
                    width=width,
                    opacity=opacity,
                    color="#8B4513"
                )
            
            # 设置布局
            net.set_options("""
            var options = {
              "nodes": {
                "shape": "circle",
                "font": {
                  "size": 14
                }
              },
              "edges": {
                "smooth": {
                  "type": "cubicBezier",
                  "forceDirection": "none",
                  "roundness": 0.4
                }
              },
              "physics": {
                "forceAtlas2Based": {
                  "gravitationalConstant": -100,
                  "centralGravity": 0.01,
                  "springLength": 100,
                  "springConstant": 0.08,
                  "damping": 0.4
                },
                "maxVelocity": 50,
                "minVelocity": 0.1,
                "solver": "forceAtlas2Based",
                "stabilization": {
                  "enabled": true,
                  "iterations": 1000,
                  "updateInterval": 100,
                  "onlyDynamicEdges": false,
                  "fit": true
                }
              }
            }
            """)
            
            # 生成 HTML 文件
            net.write_html(output_file, notebook=False)
            print(f"图谱可视化已生成到 {output_file}")
        except Exception as e:
            print(f"可视化错误: {e}")

if __name__ == "__main__":
    visualizer = GraphVisualizer()
    visualizer.visualize()
"""执行引擎 - 负责逻辑/物理映射与具体动作下发"""

import time
import hashlib
import io
import base64
import difflib
from PIL import Image, ImageDraw
from src.tool.computeruse.adapters.factory import get_platform_adapter
from src.tool.computeruse.exceptions import ExecutionFailedError
from src.utils.config import get_app_config

LOGICAL_WIDTH = 1280

# 状态缓存（用于 find_element, element_id 定位 和 拦截无脑重复截图）
_fused_elements_cache = []
_last_screenshot_hash = None


def _calculate_iou(boxA, boxB):
    """计算两个矩形框 [x1,y1,x2,y2] 的重叠比例"""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return interArea / float(boxAArea + boxBArea - interArea + 1e-5)


def _resolve_sandbox_path(path: str) -> str:
    """独立的路径映射工具：将 Agent 视角的 /agent_vm/... 映射为宿主机的真实绝对路径"""
    import os

    # 强制统一路径分隔符为 /，方便处理
    path = str(path).strip().replace("\\", "/")

    # 容错：有些 URL 解析后可能会变成 //agent_vm/
    if path.startswith("//agent_vm/"):
        path = path[1:]

    if path.startswith("/agent_vm/"):
        path = path.replace("/agent_vm/", "./agent_vm/", 1)
    elif path == "/agent_vm":
        path = "./agent_vm"

    return os.path.abspath(path)


def execute_action(
    action: str,
    coordinate: list = None,
    element_id: str = None,
    text: str = None,
    keep_apps: list = None,
    scroll_amount: int = 0,
    wait_time: float = 0.1,
) -> dict:
    global _fused_elements_cache, _last_screenshot_hash
    adapter = get_platform_adapter()

    phys_w, phys_h = adapter.get_screen_size()
    aspect_ratio = phys_w / phys_h
    logical_height = int(LOGICAL_WIDTH / aspect_ratio)
    scale_x = LOGICAL_WIDTH / phys_w
    scale_y = logical_height / phys_h

    try:
        # --- 增强版截图引擎 (数据融合 + SoM) ---
        if action == "screenshot":
            raw_img = adapter.get_screenshot_image()

            # 1. 严格哈希校验，防止死循环无效截图
            img_bytes = raw_img.tobytes()
            current_hash = hashlib.md5(img_bytes).hexdigest()
            if current_hash == _last_screenshot_hash:
                return {
                    "message": "⚠️ 警告：当前屏幕内容与上次截图【完全一致】（毫无变化）。请检查上一步操作是否生效，或增加 wait_time 等待加载，或尝试使用 scroll 滚动屏幕！",
                    "base64": "",
                    "ui_elements": "屏幕无变化，已拦截",
                }
            _last_screenshot_hash = current_hash

            # 2. 获取原始数据 (在高清原图上跑 OCR)
            import numpy as np

            ocr_elements = adapter.get_ocr_elements(np.array(raw_img))
            ui_elements = adapter.get_ui_tree_elements()

            # 3. 映射到逻辑坐标系
            for el in ocr_elements + ui_elements:
                px1, py1, px2, py2 = el["bbox"]
                el["logic_bbox"] = [
                    int(px1 * scale_x),
                    int(py1 * scale_y),
                    int(px2 * scale_x),
                    int(py2 * scale_y),
                ]
                el["logic_center"] = [
                    int((el["logic_bbox"][0] + el["logic_bbox"][2]) / 2),
                    int((el["logic_bbox"][1] + el["logic_bbox"][3]) / 2),
                ]

            # 4. 数据融合 (去重：如果 OCR 的字在 UI Button 里面，合体)
            fused = []
            for ui_el in ui_elements:
                matched_ocr = None
                for ocr_el in ocr_elements:
                    if _calculate_iou(ui_el["logic_bbox"], ocr_el["logic_bbox"]) > 0.4:
                        matched_ocr = ocr_el
                        break
                if matched_ocr:
                    ui_el["text"] = matched_ocr["text"]  # 补充UI缺失的文本
                    ocr_elements.remove(matched_ocr)
                fused.append(ui_el)
            fused.extend(ocr_elements)  # 加入剩余独立的纯文本
            _fused_elements_cache = fused

            # 5. 图像渲染：SoM 蒙版 + 稀疏坐标网格
            resized_img = raw_img.resize(
                (LOGICAL_WIDTH, logical_height), Image.Resampling.LANCZOS
            )
            # 使用 RGBA 模式以便支持透明度
            draw = ImageDraw.Draw(resized_img, "RGBA")

            # === 新增：绘制全局稀疏坐标网格 ===
            grid_spacing = 100  # 网格间距：每 100 逻辑像素一根线
            grid_color = (0, 255, 0, 50)  # 半透明绿色线 (极低透明度，防止花眼)
            text_color = (0, 255, 0, 150)  # 网格坐标数字的颜色

            # 画垂直线和 X 坐标标尺
            for x in range(0, LOGICAL_WIDTH, grid_spacing):
                draw.line([(x, 0), (x, logical_height)], fill=grid_color, width=1)
                if x > 0:  # 避开左上角 [0,0] 重叠
                    draw.text((x + 2, 2), str(x), fill=text_color)

            # 画水平线和 Y 坐标标尺
            for y in range(0, logical_height, grid_spacing):
                draw.line([(0, y), (LOGICAL_WIDTH, y)], fill=grid_color, width=1)
                if y > 0:
                    draw.text((2, y + 2), str(y), fill=text_color)
            # ==============================

            # === 继续绘制 SoM 元素蒙版与 ID ===
            legend_lines = []
            for idx, el in enumerate(fused):
                box = el["logic_bbox"]
                # 画半透明蒙版红框
                draw.rectangle(box, outline="red", width=2)
                # 画编号 ID 标签背景与文字 (红底白字)
                draw.rectangle(
                    [box[0], max(0, box[1] - 15), box[0] + 20, box[1]],
                    fill=(255, 0, 0, 200),
                )
                draw.text((box[0] + 2, max(0, box[1] - 15)), str(idx), fill="white")

                # ==========================================
                # 🔥 终极 Token 优化：采用紧凑的正则表达式友好格式
                # 格式示例：[0][Button]'确认'(500,300)
                # ==========================================
                c_type = el.get("type", "[Ele]")
                # 清理文本中的换行和冗余空格，防止破坏单行结构
                c_text = (
                    str(el.get("text", "")).replace("\n", " ").replace("\r", "").strip()
                )
                cx, cy = el["logic_center"]

                # 如果没有文字，就不显示单引号部分，进一步省 Token
                if c_text:
                    legend_lines.append(f"[{idx}]{c_type}'{c_text}'({cx},{cy})")
                else:
                    legend_lines.append(f"[{idx}]{c_type}({cx},{cy})")

            # 转 Base64
            buffered = io.BytesIO()
            resized_img.convert("RGB").save(buffered, format="PNG", optimize=True)

            # 将列表用逗号或者短空格连接（比每次换行更省 Token，但为了可读性，这里每 5 个换一行）
            compact_legend = ""
            for i in range(0, len(legend_lines), 5):
                compact_legend += "  ".join(legend_lines[i : i + 5]) + "\n"

            return {
                "base64": base64.b64encode(buffered.getvalue()).decode("utf-8"),
                "ui_elements": compact_legend.strip()
                if compact_legend
                else "未检测到可交互元素",
                "logical_width": LOGICAL_WIDTH,
                "logical_height": logical_height,
                "message": f"📸 融合截图就绪，逻辑尺寸 [{LOGICAL_WIDTH}, {logical_height}]",
            }

        # --- 元素搜索功能 (TopK) ---
        elif action == "find_element":
            if not _fused_elements_cache:
                return {"message": "缓存为空，请先执行 screenshot"}

            # 简单的文本包含匹配，返回 Top 3
            results = []
            for idx, el in enumerate(_fused_elements_cache):
                if text.lower() in el.get("text", "").lower():
                    results.append(
                        f"[{idx}]: '{el.get('text')}' 位于 {el['logic_center']}"
                    )

            if not results:
                return {
                    "message": f"🔍 未找到包含 '{text}' 的元素，请尝试使用别的关键词或滚动屏幕。"
                }
            return {
                "message": f"🔍 找到了 {len(results)} 个匹配项:\n"
                + "\n".join(results[:5])
            }

        # --- 其他底层映射操作 ---
        else:
            # SoM 智能 ID 映射：如果传了 element_id，直接查缓存覆盖 coordinate
            if element_id is not None and element_id.isdigit():
                idx = int(element_id)
                if 0 <= idx < len(_fused_elements_cache):
                    coordinate = _fused_elements_cache[idx]["logic_center"]
                else:
                    raise ExecutionFailedError(
                        action, f"无效的 element_id: {element_id}"
                    )

            # 隐式等待 (Agent自由控制)
            defer_sleep = wait_time

            if action == "scroll":
                adapter.scroll(scroll_amount)
                message = f"屏幕已滚动 {scroll_amount}"
            elif action == "hide_other_apps":
                hidden = adapter.hide_other_apps(keep_apps or [])
                message = f"清理了工作区，已隐藏应用: {', '.join(hidden)}"
            elif action == "type":
                adapter.type_via_clipboard(text)
                message = f"已成功键入: {text[:20]}..."
            elif action == "key":
                adapter.press_hotkey(text)
                message = f"已触发快捷键: {text}"
            elif action == "list_app":
                apps = get_app_config()
                if not apps:
                    message = "📂 应用白名单为空或未配置。请提示用户在项目根目录的 `.purrcat/app_config.json` 文件中配置 JSON 映射（例如：{'微信': 'D:\\WeChat\\WeChat.exe'}）。"
                else:
                    app_list = "\n".join([f"- {k}: {v}" for k, v in apps.items()])
                    message = f"📂 当前可用的应用白名单列表如下:\n{app_list}\n💡 请使用 launch_app 动作并传入上述名称进行唤起。"
            elif action == "launch_app":
                from urllib.parse import urlparse, unquote
                from urllib.request import url2pathname
                import os

                text_str = text.strip()
                text_lower = text_str.lower()

                # 1. 处理 Web URL (http/https)
                if text_lower.startswith(("http://", "https://")):
                    try:
                        adapter.launch_app(text_str)
                        message = f"🌐 已成功使用默认浏览器打开网页: {text_str}"
                    except Exception as e:
                        raise ExecutionFailedError(action, f"打开网页失败: {str(e)}")
                else:
                    # 2. 识别是否为文件路径 (拦截 file:// 协议，以及常见的绝对/相对/沙盒路径)
                    is_explicit_file = False
                    potential_path = text_str

                    # 拦截 file:// 协议，并进行 URL Decode 处理中文 (%E4...)
                    if text_lower.startswith("file://"):
                        is_explicit_file = True
                        parsed = urlparse(text_str)
                        # 将 URL 格式转回本地操作系统的正确路径
                        potential_path = url2pathname(unquote(parsed.path))

                    # 拦截明显的路径特征或文件后缀
                    elif (
                        potential_path.startswith("/agent_vm/")
                        or potential_path.startswith("./")
                        or os.path.isabs(potential_path)
                        or text_lower.endswith(
                            (
                                ".html",
                                ".htm",
                                ".pdf",
                                ".txt",
                                ".png",
                                ".jpg",
                                ".md",
                                ".json",
                                ".svg",
                            )
                        )
                    ):
                        is_explicit_file = True

                    # 如果确定意图是操作文件
                    if is_explicit_file:
                        # 转换沙盒路径到宿主机真实路径
                        mapped_path = _resolve_sandbox_path(potential_path)

                        if os.path.exists(mapped_path):
                            try:
                                adapter.launch_app(mapped_path)
                                message = f"🌐 已成功使用系统默认程序打开本地文件: {mapped_path}"
                            except Exception as e:
                                raise ExecutionFailedError(
                                    action, f"打开本地文件失败: {str(e)}"
                                )
                        else:
                            # 核心修复点：明确是文件意图但不存在，直接果断报错，禁止走白名单！
                            raise ExecutionFailedError(
                                action,
                                f"目标文件不存在，无法打开: {potential_path}\n(映射后的本地真实路径为: {mapped_path})",
                            )

                    # 3. 既不是 web url，也不像是文件路径，才走到应用白名单逻辑
                    else:
                        apps = get_app_config()
                        if not apps:
                            raise ExecutionFailedError(
                                action,
                                "应用白名单未配置，请提示用户先创建 .purrcat/app_config.json 文件",
                            )

                        matches = difflib.get_close_matches(
                            text_str, list(apps.keys()), n=1, cutoff=0.4
                        )

                        if matches:
                            target_name = matches[0]
                            target_path = apps[target_name]
                            try:
                                adapter.launch_app(target_path)
                                message = f"🚀 已成功尝试唤起应用: {target_name} ({target_path})"
                            except Exception as e:
                                raise ExecutionFailedError(
                                    action, f"唤起失败: {str(e)}"
                                )
                        else:
                            raise ExecutionFailedError(
                                action,
                                f"未在白名单中找到与 '{text_str}' 匹配的应用。请先使用 list_app 动作查看可用列表。",
                            )
            else:
                if not coordinate:
                    raise ExecutionFailedError(action, "缺少有效坐标或 element_id")
                # 逻辑坐标转物理坐标 (统一体系)
                logical_x, logical_y = coordinate
                phys_x = int((logical_x / LOGICAL_WIDTH) * phys_w)
                phys_y = int((logical_y / logical_height) * phys_h)

                if action == "mouse_move":
                    adapter.move_mouse(phys_x, phys_y)
                elif action == "left_click":
                    adapter.click(phys_x, phys_y, button="left", clicks=1)
                elif action == "right_click":
                    adapter.click(phys_x, phys_y, button="right", clicks=1)
                elif action == "middle_click":
                    adapter.click(phys_x, phys_y, button="middle", clicks=1)
                elif action == "double_click":
                    adapter.click(phys_x, phys_y, button="left", clicks=2)
                elif action == "left_click_drag":
                    if len(coordinate) == 4:
                        start_logical_x, start_logical_y = coordinate[0], coordinate[1]
                        end_logical_x, end_logical_y = coordinate[2], coordinate[3]

                        start_phys_x = int((start_logical_x / LOGICAL_WIDTH) * phys_w)
                        start_phys_y = int((start_logical_y / logical_height) * phys_h)

                        phys_x = int((end_logical_x / LOGICAL_WIDTH) * phys_w)
                        phys_y = int((end_logical_y / logical_height) * phys_h)

                        adapter.move_mouse(start_phys_x, start_phys_y)

                    adapter.drag_mouse(phys_x, phys_y)
                else:
                    raise ExecutionFailedError(action, "未知动作")
                message = f"鼠标操作 {action} 完成 (坐标: {logical_x},{logical_y})"

            # 执行 Agent 指定的等待期
            time.sleep(defer_sleep)

            # 🌟 新增：操作后自动抓取焦点状态，反馈给大模型，免去二次截图盲猜！
            focus_status = adapter.get_focused_element_info()
            if focus_status:
                message += f"\n💡 [系统自动反馈]: {focus_status}"

            return {"message": message}

    except Exception as e:
        raise ExecutionFailedError(action, str(e))

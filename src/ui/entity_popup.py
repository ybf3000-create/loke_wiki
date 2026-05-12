# src/ui/entity_popup.py
# 实体信息弹出窗 - 点击精灵/技能/属性名称时显示详情

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QSizePolicy,
)
from loguru import logger

from config.settings import FONT_FAMILY
from src.core.database import (
    query_spirit, query_skill, query_type_effectiveness,
    query_type_effectiveness_dual,
)
from src.ui.entity_registry import ATTRIBUTE_TYPES


def _font(size=10, bold=False):
    f = QFont(FONT_FAMILY if FONT_FAMILY in QFont().families() else "Microsoft YaHei", size)
    f.setBold(bold)
    return f


class EntityPopup(QFrame):
    """实体信息弹出气泡窗"""

    def __init__(self, entity_type: str, entity_name: str, parent=None):
        super().__init__(parent)
        self._entity_type = entity_type
        self._entity_name = entity_name
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 外层白色卡片
        card = QFrame()
        card.setObjectName("popupCard")
        card.setStyleSheet("""
            #popupCard {
                background-color: #FFFFFF;
                border: 1px solid #D5D5D5;
                border-radius: 10px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        # 标题
        type_labels = {"spirit": "🔮 精灵", "skill": "⚔️ 技能", "type": "🔥 属性"}
        type_label = type_labels.get(self._entity_type, "📦")
        title = QLabel(f"{type_label} · {self._entity_name}")
        title.setFont(_font(13, True))
        title.setStyleSheet("color: #333333; background: transparent;")
        card_layout.addWidget(title)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #E0E0E0; background: transparent;")
        sep.setFixedHeight(1)
        card_layout.addWidget(sep)

        # 内容
        content = self._build_content()
        content.setWordWrap(True)
        content.setFont(_font(10))
        content.setStyleSheet("color: #555555; background: transparent;")
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card_layout.addWidget(content)

        layout.addWidget(card)

        # 自适应大小后设置固定宽度（防止刷新变化）
        self.adjustSize()
        if self.width() < 260:
            self.setFixedWidth(260)
        if self.width() > 480:
            self.setFixedWidth(480)

    def _build_content(self) -> QLabel:
        label = QLabel()
        data_handlers = {
            "spirit": self._build_spirit_info,
            "skill": self._build_skill_info,
            "type": self._build_type_info,
        }
        handler = data_handlers.get(self._entity_type, self._build_fallback)
        label.setText(handler())
        return label

    def _build_spirit_info(self) -> str:
        data = query_spirit(self._entity_name)
        if not data:
            return f"未找到「{self._entity_name}」的数据"

        lines = [f"编号：{data.get('number', '未知')}"]
        types = [t for t in [data.get('type1', ''), data.get('type2', '')] if t]
        lines.append(f"属性：{' · '.join(types)}")

        # 特性
        ability = data.get('ability', '')
        if ability and ability != '无':
            effect = data.get('ability_effect', '')
            lines.append(f"特性：{ability}")
            if effect and effect != '无':
                lines.append(f"　　　{effect}")

        # 进化链
        evo = data.get('evolution_chain', '')
        if evo:
            lines.append(f"进化：{evo}")

        # 描述
        desc = data.get('description', '')
        if desc:
            lines.append(f"简介：{desc[:80]}{'...' if len(desc)>80 else ''}")

        return "<br>".join(lines)

    def _build_skill_info(self) -> str:
        data = query_skill(self._entity_name)
        if not data:
            return f"未找到「{self._entity_name}」的数据"

        lines = []
        if data.get('skill_type'):
            lines.append(f"类型：{data['skill_type']}")
        parts = []
        if data.get('power'):
            parts.append(f"威力 {data['power']}")
        if data.get('accuracy'):
            parts.append(f"命中 {data['accuracy']}")
        if data.get('pp'):
            parts.append(f"PP {data['pp']}")
        if parts:
            lines.append(" | ".join(parts))
        desc = data.get('description') or data.get('effect') or ''
        if desc:
            lines.append(f"效果：{desc[:120]}{'...' if len(desc)>120 else ''}")

        return "<br>".join(lines) if lines else "暂无详细数据"

    def _build_type_info(self) -> str:
        attr = self._entity_name
        if attr not in ATTRIBUTE_TYPES:
            return f"未知属性「{attr}」"

        atk_2x = []   # 攻击端 克制
        atk_05 = []   # 攻击端 抵抗
        atk_0 = []    # 攻击端 无效
        def_2x = []   # 防御端 被克
        def_05 = []   # 防御端 抵抗
        def_0 = []    # 防御端 免疫

        for def_type in ATTRIBUTE_TYPES:
            mult = query_type_effectiveness(attr, def_type)
            if mult is None:
                continue
            if mult == 2.0:
                atk_2x.append(def_type)
            elif mult == 0.5:
                atk_05.append(def_type)
            elif mult == 0.0:
                atk_0.append(def_type)

        for atk_type in ATTRIBUTE_TYPES:
            if atk_type == attr:
                continue
            mult = query_type_effectiveness(atk_type, attr)
            if mult is None:
                continue
            if mult == 2.0:
                def_2x.append(atk_type)
            elif mult == 0.5:
                def_05.append(atk_type)
            elif mult == 0.0:
                def_0.append(atk_type)

        lines = [f"<b>{attr}系</b> 克制关系"]
        lines.append("")

        # 攻击端
        parts = []
        if atk_2x:
            parts.append(f"克制 {' '.join(atk_2x)}")
        if atk_05:
            parts.append(f"抵抗 {' '.join(atk_05)}")
        if atk_0:
            parts.append(f"无效 {' '.join(atk_0)}")
        lines.append(f"<b>攻击端</b>：{'，'.join(parts) if parts else '无'}")

        # 防御端
        parts = []
        if def_2x:
            parts.append(f"被克 {' '.join(def_2x)}")
        if def_05:
            parts.append(f"抵抗 {' '.join(def_05)}")
        if def_0:
            parts.append(f"免疫 {' '.join(def_0)}")
        lines.append(f"<b>防御端</b>：{'，'.join(parts) if parts else '无'}")

        return "<br>".join(lines)

    def _build_fallback(self) -> str:
        return "暂无数据"


# 便捷函数：显示弹窗
_current_popup = None


def show_entity_popup(entity_type: str, entity_name: str, parent_widget=None):
    """在屏幕中央显示实体信息弹窗"""
    global _current_popup
    if _current_popup:
        _current_popup.close()
        _current_popup = None

    popup = EntityPopup(entity_type, entity_name)
    _current_popup = popup

    if parent_widget:
        # 居中显示在父窗口上方
        parent_rect = parent_widget.geometry()
        popup_width = max(260, min(480, popup.width()))
        popup_height = popup.height()
        x = parent_rect.x() + (parent_rect.width() - popup_width) // 2
        y = parent_rect.y() + (parent_rect.height() - popup_height) // 3
        popup.setGeometry(x, y, popup_width, popup_height)
    else:
        popup.move(400, 200)

    popup.show()
    popup.raise_()


def close_entity_popup():
    """关闭当前弹窗"""
    global _current_popup
    if _current_popup:
        _current_popup.close()
        _current_popup = None

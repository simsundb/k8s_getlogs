"""④ 页「管理运维项」对话框：新增 / 编辑 / 删除 / 启用停用 / 恢复默认。

预置运维命令原本写死在 OPS_COMMANDS，这里把这份清单开放给用户维护：
- 新增：添加自定义运维项（可含 {namespace} 占位符）
- 编辑 / 删除：修改或移除任意项
- 停用：active=False 后不出现在下拉中（即「不生效」）
- 恢复默认：还原为出厂预置清单
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ..ops import OPS_COMMANDS, OpsCommand

OPS_CATEGORIES = ["集群", "节点", "应用", "存储", "自定义"]


class OpsEditDialog(QDialog):
    """新增 / 编辑单个运维项的小表单。"""

    def __init__(self, command: OpsCommand | None,
                 others: list[OpsCommand], parent=None):
        super().__init__(parent)
        self._others = others
        self.setWindowTitle("新增运维项" if command is None else "编辑运维项")
        form = QFormLayout(self)

        self.cat_combo = QComboBox()
        self.cat_combo.setEditable(True)          # 允许输入自定义类别
        self.cat_combo.addItems(OPS_CATEGORIES)
        self.label_edit = QLineEdit()
        self.desc_edit = QLineEdit()
        self.cmd_edit = QPlainTextEdit()
        self.cmd_edit.setFixedHeight(60)
        self.need_ns = QCheckBox("命令包含 {namespace} 占位符（执行时替换为所选命名空间）")
        self.active_box = QCheckBox("启用（不勾选则不出现在下拉中）")
        self.active_box.setChecked(True)

        form.addRow("类别:", self.cat_combo)
        form.addRow("名称:", self.label_edit)
        form.addRow("说明:", self.desc_edit)
        form.addRow("命令:", self.cmd_edit)
        form.addRow("", self.need_ns)
        form.addRow("", self.active_box)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

        if command is not None:
            self.cat_combo.setCurrentText(command.category)
            self.label_edit.setText(command.label)
            self.desc_edit.setText(command.description)
            self.cmd_edit.setPlainText(command.command)
            self.need_ns.setChecked(command.needs_namespace)
            self.active_box.setChecked(command.active)

    def _validation_error(self) -> str | None:
        """校验失败返回原因，通过则返回 None（可独立测试，不弹模态框）。"""
        label = self.label_edit.text().strip()
        cmd = self.cmd_edit.toPlainText().strip()
        if not label:
            return "请填写运维项名称"
        if not cmd:
            return "请填写要执行的命令"
        if any(o.label == label for o in self._others):
            return f"运维项名称「{label}」已存在"
        return None

    def _validate_and_accept(self):
        err = self._validation_error()
        if err:
            QMessageBox.warning(self, "校验", err)
            return
        if "{namespace}" in self.cmd_edit.toPlainText():
            self.need_ns.setChecked(True)         # 含占位符自动勾选依赖命名空间
        self.accept()

    def command(self) -> OpsCommand:
        return OpsCommand(
            label=self.label_edit.text().strip(),
            category=self.cat_combo.currentText().strip() or "自定义",
            description=self.desc_edit.text().strip(),
            command=self.cmd_edit.toPlainText().strip(),
            needs_namespace=self.need_ns.isChecked(),
            active=self.active_box.isChecked(),
        )


class OpsManagerDialog(QDialog):
    """运维项管理主对话框：表格列出全部命令，支持新增/编辑/删除/启用停用/恢复默认。"""

    def __init__(self, commands: list[OpsCommand], parent=None):
        super().__init__(parent)
        self.setWindowTitle("管理运维项")
        self.resize(920, 520)
        self._commands = [OpsCommand(c.label, c.category, c.description,
                                     c.command, c.needs_namespace, c.active)
                          for c in commands]

        root = QVBoxLayout(self)
        hint = QLabel("维护「预置运维命令」清单：停用的项目不出现在下拉中；「恢复默认」还原出厂配置。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6a7380;")
        root.addWidget(hint)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["启用", "类别", "名称", "说明", "命令"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("新增")
        self.edit_btn = QPushButton("编辑")
        self.del_btn = QPushButton("删除")
        self.reset_btn = QPushButton("恢复默认")
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.edit_btn)
        btn_row.addWidget(self.del_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.reset_btn)
        root.addLayout(btn_row)

        close_row = QHBoxLayout()
        self.save_close_btn = QPushButton("保存并关闭")
        self.save_close_btn.setProperty("primary", True)
        self.cancel_btn = QPushButton("取消")
        close_row.addStretch(1)
        close_row.addWidget(self.save_close_btn)
        close_row.addWidget(self.cancel_btn)
        root.addLayout(close_row)

        self.add_btn.clicked.connect(self._add)
        self.edit_btn.clicked.connect(self._edit)
        self.del_btn.clicked.connect(self._delete)
        self.reset_btn.clicked.connect(self._reset)
        self.save_close_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.table.itemChanged.connect(self._on_item_changed)
        self._loading = False
        self._reload()

    # ---------- 公开/可测 API ----------
    def commands(self) -> list[OpsCommand]:
        return list(self._commands)

    def add_command(self, cmd: OpsCommand) -> None:
        self._commands.append(cmd)
        self._reload()

    def set_command(self, row: int, cmd: OpsCommand) -> None:
        if 0 <= row < len(self._commands):
            self._commands[row] = cmd
            self._reload()

    def delete_row(self, row: int) -> None:
        if 0 <= row < len(self._commands):
            del self._commands[row]
            self._reload()

    def reset_defaults(self) -> None:
        self._commands = [OpsCommand(c.label, c.category, c.description,
                                     c.command, c.needs_namespace, c.active)
                          for c in OPS_COMMANDS]
        self._reload()

    # ---------- 内部 ----------
    def _reload(self):
        self._loading = True
        self.table.setRowCount(len(self._commands))
        for r, c in enumerate(self._commands):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            chk.setCheckState(Qt.Checked if c.active else Qt.Unchecked)
            self.table.setItem(r, 0, chk)
            self.table.setItem(r, 1, QTableWidgetItem(c.category))
            self.table.setItem(r, 2, QTableWidgetItem(c.label))
            self.table.setItem(r, 3, QTableWidgetItem(c.description))
            self.table.setItem(r, 4, QTableWidgetItem(c.command))
        self._loading = False

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._loading or item.column() != 0:
            return
        r = item.row()
        if 0 <= r < len(self._commands):
            self._commands[r].active = item.checkState() == Qt.Checked

    def _selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _add(self):
        dlg = OpsEditDialog(None, self._commands, self)
        if dlg.exec() == QDialog.Accepted:
            self.add_command(dlg.command())

    def _edit(self):
        r = self._selected_row()
        if r < 0:
            QMessageBox.information(self, "提示", "请先在表格中选中一行")
            return
        others = [c for i, c in enumerate(self._commands) if i != r]
        dlg = OpsEditDialog(self._commands[r], others, self)
        if dlg.exec() == QDialog.Accepted:
            self.set_command(r, dlg.command())

    def _delete(self):
        r = self._selected_row()
        if r < 0:
            QMessageBox.information(self, "提示", "请先在表格中选中一行")
            return
        label = self._commands[r].label
        if QMessageBox.question(self, "确认删除",
                                f"删除运维项「{label}」？") != QMessageBox.Yes:
            return
        self.delete_row(r)

    def _reset(self):
        if QMessageBox.question(self, "恢复默认",
                                "将恢复出厂预置运维项，当前修改（新增/删除/停用）会全部丢失。继续？"
                                ) != QMessageBox.Yes:
            return
        self.reset_defaults()

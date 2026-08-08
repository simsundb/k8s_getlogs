# tests/test_ops_manager.py
"""④ 页「管理运维项」对话框：编辑表单校验、新增/编辑/删除、启用停用、恢复默认。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from src.ops import OPS_COMMANDS, OpsCommand
from src.ui.ops_manager import OpsEditDialog, OpsManagerDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _sample():
    return [OpsCommand("集群信息", "集群", "查看集群", "kubectl cluster-info"),
            OpsCommand("节点磁盘", "节点", "磁盘", "df -h")]


def test_edit_dialog_validation(app):
    """空名称/空命令/重复名称分别给出原因（不弹模态框）。"""
    dlg = OpsEditDialog(None, [], None)
    dlg.label_edit.setText("")
    dlg.cmd_edit.setPlainText("echo 1")
    assert dlg._validation_error() == "请填写运维项名称"

    dlg.label_edit.setText("新项")
    dlg.cmd_edit.setPlainText("")
    assert dlg._validation_error() == "请填写要执行的命令"

    dlg.cmd_edit.setPlainText("echo 1")
    dlg._others = [OpsCommand("新项", "集群", "", "x")]
    assert "已存在" in dlg._validation_error()
    dlg.deleteLater()


def test_edit_dialog_accepts_and_builds_command(app):
    dlg = OpsEditDialog(None, [], None)
    dlg.cat_combo.setCurrentText("存储")
    dlg.label_edit.setText("PV 检查")
    dlg.desc_edit.setText("查看持久卷")
    dlg.cmd_edit.setPlainText("kubectl get pv,pvc -A")
    dlg._validate_and_accept()                  # 无校验错误 → accept()
    assert dlg.result() == QDialog.Accepted
    cmd = dlg.command()
    assert cmd.label == "PV 检查"
    assert cmd.category == "存储"
    assert cmd.command == "kubectl get pv,pvc -A"
    assert cmd.active is True
    assert cmd.needs_namespace is False
    dlg.deleteLater()


def test_edit_dialog_placeholder_auto_marks_namespace(app):
    """命令含 {namespace} 自动勾选「需命名空间」。"""
    dlg = OpsEditDialog(None, [], None)
    dlg.label_edit.setText("Pod 列表")
    dlg.cmd_edit.setPlainText("kubectl get pods -n {namespace}")
    dlg._validate_and_accept()
    assert dlg.command().needs_namespace is True
    dlg.deleteLater()


def test_manager_add_and_commands(app):
    dlg = OpsManagerDialog(_sample(), None)
    try:
        assert len(dlg.commands()) == 2
        dlg.add_command(OpsCommand("自定义", "自定义", "d", "echo hi"))
        assert len(dlg.commands()) == 3
        assert dlg.commands()[-1].label == "自定义"
        assert dlg.table.rowCount() == 3
    finally:
        dlg.deleteLater()


def test_manager_set_and_delete(app):
    dlg = OpsManagerDialog(_sample(), None)
    try:
        dlg.set_command(0, OpsCommand("改名", "集群", "d", "kubectl version"))
        assert dlg.commands()[0].label == "改名"
        dlg.delete_row(0)
        assert [c.label for c in dlg.commands()] == ["节点磁盘"]
        assert dlg.table.rowCount() == 1
    finally:
        dlg.deleteLater()


def test_manager_toggle_active_column(app):
    dlg = OpsManagerDialog(_sample(), None)
    try:
        item = dlg.table.item(0, 0)              # 「启用」列
        assert dlg.commands()[0].active is True
        item.setCheckState(Qt.Unchecked)         # 模拟点击停用
        assert dlg.commands()[0].active is False
    finally:
        dlg.deleteLater()


def test_manager_reset_defaults(app):
    dlg = OpsManagerDialog([OpsCommand("仅剩", "集群", "", "x")], None)
    try:
        dlg.reset_defaults()
        assert [c.label for c in dlg.commands()] == [c.label for c in OPS_COMMANDS]
        assert all(c.active for c in dlg.commands())
    finally:
        dlg.deleteLater()

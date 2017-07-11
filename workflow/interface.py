import os
import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from workflow.Tree import TreeScene, NODES
import workflow.multi_func as worker
from workflow.MultiTree import MultiTreeScene


def count_cc(nodes, adj_list):
    """returns the number of CC and the CC as a map(node, label)"""
    labels = {}
    current_label = 0
    for node in nodes:
        labels[node] = -1

    def label_connected_component(labels, start_node, current_label):
        labels[start_node] = current_label
        for neighbor in adj_list[start_node]:
            if labels[neighbor] == -1:
                labels = label_connected_component(labels, neighbor, current_label)
        return labels

    for node in nodes:
        if labels[node] == -1:
            labels = label_connected_component(labels, node, current_label)
            current_label += 1
    return current_label, labels


class TreeView(QGraphicsView):
    def __init__(self, parent):
        super().__init__(TreeScene())
        self.parent = parent
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setAcceptDrops(True)
        self.current_node = None

    def resizeEvent(self, event):
        self.scene().setSceneRect(QRectF(0, 0, self.width()-10, self.height()-10))

    def dropEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            category, label = event.mimeData().text().split('|')
            node = NODES[category][label](self.scene().nb_nodes)
            pos = self.mapToScene(event.pos())
            self.scene().add_node(node, pos)
            event.accept()
        else:
            event.ignore()

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def select_node(self, node):
        self.current_node = node
        self.parent.enable_toolbar()

    def deselect_node(self):
        self.current_node = None
        self.parent.disable_toolbar()


class TreePanel(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.view = TreeView(self)

        self.toolbar = QToolBar()
        self.node_label = QLineEdit()
        self.save_act = QAction('Save\n(Ctrl+S)', self, triggered=self.save, shortcut='Ctrl+S')
        self.run_all_act = QAction('Run all\n(F5)', self, triggered=self.run_all, shortcut='F5')
        self.configure_act = QAction('Configure\n(Ctrl+C)', self, triggered=self.configure_node,
                                     enabled=False, shortcut='Ctrl+C')
        self.delete_act = QAction('Delete\n(Del)', self, triggered=self.delete_node, enabled=False, shortcut='Del')
        self.run_act = QAction('Run\n(Ctrl+R)', self, triggered=self.run_node, enabled=False, shortcut='Ctrl+R')
        self.init_toolbar()

        layout = QVBoxLayout()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.view)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def init_toolbar(self):
        for act in [self.save_act, self.run_all_act]:
            button = QToolButton(self)
            button.setFixedWidth(100)
            button.setMinimumHeight(30)
            button.setDefaultAction(act)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            self.toolbar.addWidget(button)
            self.toolbar.addSeparator()

        self.toolbar.addWidget(QLabel('   Selected node  '))
        self.toolbar.addWidget(self.node_label)
        self.node_label.setFixedWidth(150)
        self.node_label.setReadOnly(True)
        self.toolbar.addSeparator()
        for act in [self.configure_act, self.run_act, self.delete_act]:
            button = QToolButton(self)
            button.setFixedWidth(100)
            button.setMinimumHeight(30)
            button.setDefaultAction(act)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            self.toolbar.addWidget(button)

    def save(self):
        if not self.parent.save():
            QMessageBox.critical(None, 'Error',
                                 'You have duplicated suffix.',
                                 QMessageBox.Ok)

    def run_all(self):
        self.view.scene().run_all()
        self.view.scene().update()

    def configure_node(self):
        self.view.current_node.configure()
        if self.view.current_node.ready_to_run():
            self.run_act.setEnabled(True)
        self.view.scene().update()

    def delete_node(self):
        self.view.scene().handle_remove_node(self.view.current_node)
        self.view.deselect_node()
        self.view.scene().update()

    def run_node(self):
        self.view.current_node.run()
        self.view.scene().update()

    def enable_toolbar(self):
        self.node_label.setText(self.view.current_node.label)
        for act in [self.configure_act, self.delete_act]:
            act.setEnabled(True)
        if self.view.current_node.ready_to_run():
            self.run_act.setEnabled(True)
        else:
            self.run_act.setEnabled(False)

    def disable_toolbar(self):
        self.node_label.clear()
        for act in [self.configure_act, self.run_act, self.delete_act]:
            act.setEnabled(False)


class NodeTree(QTreeWidget):
    def __init__(self):
        super().__init__()
        for category in NODES:
            node = QTreeWidgetItem(self, [category])
            node.setExpanded(True)
            for node_text in NODES[category]:
                node.addChild(QTreeWidgetItem([node_text]))

        self.setDragEnabled(True)
        self.setMaximumWidth(230)
        self.setColumnCount(1)
        self.setHeaderLabel('Add Nodes')

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        current_item = self.currentItem()
        if current_item is None:
            return
        if current_item.parent() is not None:
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText('|'.join([self.currentItem().parent().text(0), self.currentItem().text(0)]))
            drag.setMimeData(mime_data)
            drag.exec(Qt.MoveAction | Qt.CopyAction)


class MonoTreeWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        tree = TreePanel(parent)
        node_list = NodeTree()
        self.scene = tree.view.scene()

        left_panel = QWidget()
        config_button = QPushButton('Global\nConfiguration')
        config_button.setMinimumHeight(40)
        config_button.setMaximumWidth(230)
        config_button.clicked.connect(tree.view.scene().global_config)

        vlayout = QVBoxLayout()
        vlayout.addWidget(config_button)
        vlayout.addWidget(node_list)
        vlayout.setContentsMargins(0, 0, 0, 0)
        left_panel.setLayout(vlayout)

        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(tree)
        splitter.setHandleWidth(10)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(1, 1)

        mainLayout = QHBoxLayout()
        mainLayout.addWidget(splitter)
        self.setLayout(mainLayout)


class MultiTreeView(QGraphicsView):
    def __init__(self, parent, table):
        super().__init__(MultiTreeScene(table))
        self.parent = parent
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setAcceptDrops(True)
        self.current_node = None

    def resizeEvent(self, event):
        self.scene().setSceneRect(QRectF(0, 0, self.width()-10, self.height()-10))


class MultiTreeTable(QTableWidget):
    def __init__(self):
        super().__init__()
        self.yellow = QColor(245, 255, 207, 255)
        self.green = QColor(180, 250, 165, 255)
        self.grey = QColor(211, 211, 211, 255)
        self.red = QColor(255, 160, 160, 255)

        self.setRowCount(1)
        self.setColumnCount(0)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setVerticalHeaderLabels(['Load Serafin'])

        self.input_columns = {}
        self.yellow_nodes = {}

    def reinit(self):
        self.setRowCount(1)
        self.setVerticalHeaderLabels(['Load Serafin'])
        self.setColumnCount(0)
        self.input_columns = {}
        self.yellow_nodes = {}

    def update_rows(self, nodes, ordered_nodes):
        self.setRowCount(len(ordered_nodes))
        self.setColumnCount(0)
        self.setVerticalHeaderLabels([nodes[u].name() for u in ordered_nodes])
        self.input_columns = {}
        self.yellow_nodes = {}

    def add_files(self, node_index, new_ids, downstream_nodes):
        self.input_columns[node_index] = []
        self.yellow_nodes[node_index] = downstream_nodes
        offset = self.columnCount()
        self.setColumnCount(offset + len(new_ids))

        new_labels = []
        for j in range(offset):
            new_labels.append(self.horizontalHeaderItem(j).text())
        new_labels.extend(new_ids)
        self.setHorizontalHeaderLabels(new_labels)

        for j in range(len(new_ids)):
            self.input_columns[node_index].append(offset+j)
            for i in range(self.rowCount()):
                item = QTableWidgetItem()
                self.setItem(i, offset+j, item)
                if i in downstream_nodes:
                    self.item(i, offset+j).setBackground(self.yellow)
                else:
                    self.item(i, offset+j).setBackground(self.grey)

    def update_files(self, node_index, new_ids):
        new_labels = []
        old_input_nodes = [u for u in self.input_columns.keys() if u != node_index]
        old_input_nb = {}
        for input_node in old_input_nodes:
            old_input_nb[input_node] = len(self.input_columns[input_node])
            for j in self.input_columns[input_node]:
                new_labels.append(self.horizontalHeaderItem(j).text())

        new_labels.extend(new_ids)   # modified input nodes always at end of the table
        self.input_columns = {}  # all columns could be shuffled

        self.setColumnCount(len(new_labels))
        self.setHorizontalHeaderLabels(new_labels)

        # rebuild the whole table
        offset = 0
        for input_node in old_input_nodes:
            self.input_columns[input_node] = []
            for j in range(old_input_nb[input_node]):
                self.input_columns[input_node].append(offset+j)
                for i in range(self.rowCount()):
                    item = QTableWidgetItem()
                    self.setItem(i, offset+j, item)
                    if i in self.yellow_nodes[input_node]:
                        self.item(i, offset+j).setBackground(self.yellow)
                    else:
                        self.item(i, offset+j).setBackground(self.grey)
            offset += old_input_nb[input_node]
        self.input_columns[node_index] = []
        for j in range(len(new_ids)):
            self.input_columns[node_index].append(offset+j)
            for i in range(self.rowCount()):
                item = QTableWidgetItem()
                self.setItem(i, offset+j, item)
                if i in self.yellow_nodes[node_index]:
                    self.item(i, offset+j).setBackground(self.yellow)
                else:
                    self.item(i, offset+j).setBackground(self.grey)


class MultiTreeWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.table = MultiTreeTable()
        self.view = MultiTreeView(self, self.table)
        self.scene = self.view.scene()

        self.toolbar = QToolBar()
        self.save_act = QAction('Save\n(Ctrl+S)', self, triggered=self.save, shortcut='Ctrl+S')
        self.run_act = QAction('Run\n(F5)', self, triggered=self.run, shortcut='F5')
        self.init_toolbar()

        self.message_box = QPlainTextEdit()
        self.message_box.setReadOnly(True)

        left_panel = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.view)
        layout.setContentsMargins(0, 0, 0, 0)
        left_panel.setLayout(layout)

        right_panel = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addWidget(self.message_box)
        layout.setContentsMargins(0, 0, 0, 0)
        right_panel.setLayout(layout)

        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setHandleWidth(10)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(1, 1)

        mainLayout = QHBoxLayout()
        mainLayout.addWidget(splitter)
        self.setLayout(mainLayout)

        self.worker = worker.Workers()

    def init_toolbar(self):
        for act in [self.save_act, self.run_act]:
            button = QToolButton(self)
            button.setFixedWidth(100)
            button.setMinimumHeight(30)
            button.setDefaultAction(act)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            self.toolbar.addWidget(button)
            self.toolbar.addSeparator()

    def save(self):
        if not self.scene.ready_to_run:
            QMessageBox.critical(None, 'Error',
                                 'Configure all input nodes before saving.',
                                 QMessageBox.Ok)
            return
        self.parent.save()

    def run(self):
        if not self.scene.ready_to_run:
            return

        self.setEnabled(False)
        # initial tasks
        init_tasks = []
        for node_id in self.view.scene().ordered_input_indices:
            paths, name, job_ids = self.view.scene().inputs[node_id]
            for path, job_id, fid in zip(paths, job_ids, self.table.input_columns[node_id]):
                init_tasks.append((worker.read_slf, (node_id, fid, os.path.join(path, name),
                                                     self.scene.language, job_id)))

        self.worker.start(init_tasks)
        nb_tasks = len(init_tasks)
        while not self.worker.stopped:
            success, node_id, fid, data, message = self.worker.done_queue.get()
            nb_tasks -= 1
            self.message_box.appendPlainText(message)

            if success:
                self.table.item(node_id, fid).setBackground(self.table.green)
                QApplication.processEvents()

                next_nodes = self.scene.adj_list[node_id]
                for next_node_id in next_nodes:
                    next_node = self.scene.nodes[next_node_id]

                    fun = worker.FUNCTIONS[next_node.name()]
                    self.worker.task_queue.put((fun, (next_node_id, fid, data, next_node.options)))
                    nb_tasks += 1
            else:
                self.table.item(node_id, fid).setBackground(self.table.red)
                QApplication.processEvents()

            if nb_tasks == 0:
                self.worker.stop()

        self.message_box.appendPlainText('Done!')
        self.setEnabled(True)
        self.worker = worker.Workers()


class ProjectDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.choice = None
        left_button = QPushButton('Create New\nProject')
        right_button = QPushButton('Load\nExisting\nProject')
        for bt in [left_button, right_button]:
            bt.setFixedSize(150, 200)

        left_button.clicked.connect(self.choose_left)
        right_button.clicked.connect(self.choose_right)

        vlayout = QHBoxLayout()
        vlayout.addWidget(left_button)
        vlayout.addWidget(right_button)
        self.setLayout(vlayout)
        self.setWindowTitle('TelTools')

        self.new = False
        self.filename = ''

    def choose_left(self):
        filename, _ = QFileDialog.getSaveFileName(None, 'Choose the project file name', '',
                                                  'All Files (*)',
                                                  options=QFileDialog.Options() | QFileDialog.DontUseNativeDialog)
        if not filename:
            return
        self.new = True
        self.filename = filename
        self.accept()

    def choose_right(self):
        filename, _ = QFileDialog.getOpenFileName(None, 'Choose the project file', '', 'All files (*)',
                                                  options=QFileDialog.Options() | QFileDialog.DontUseNativeDialog)
        if not filename:
            return
        self.filename = filename
        self.accept()


class MyMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.mono = MonoTreeWidget(self)
        self.multi = MultiTreeWidget(self)
        self.tab = QTabWidget()
        self.tab.setStyleSheet('QTabBar::tab { height: 40px; min-width: 150px; }')

        self.tab.addTab(self.mono, 'Mono')
        self.tab.addTab(self.multi, 'Multi')

        self.tab.currentChanged.connect(self.switch_tab)
        layout = QVBoxLayout()
        layout.addWidget(self.tab)
        self.setLayout(layout)

        self.filename = ''

    def load(self, filename):
        if not self.mono.scene.load(filename):
            return False
        if not self.multi.scene.load(filename):
            return False
        self.filename = filename
        return True

    def save(self):
        suffix = self.mono.scene.suffix_pool()
        if len(suffix) != len(set(suffix)):
            return False

        with open(self.filename, 'w') as f:
            for line in self.mono.scene.save():
                f.write(line)
                f.write('\n')
            for line in self.multi.scene.save():
                f.write(line)
                f.write('\n')
        return True

    def create_new(self, filename):
        self.filename = filename
        with open(self.filename, 'w') as f:
            for line in self.mono.scene.save():
                f.write(line)
                f.write('\n')

    def switch_tab(self, index):
        if index == 1:
            self.mono_to_multi()
        else:
            self.multi_to_mono()

    def mono_to_multi(self):
        if not self.save():
            self.tab.setCurrentIndex(0)
            QMessageBox.critical(None, 'Error',
                                 'You have duplicated suffix.',
                                 QMessageBox.Ok)
            return
        nb_cc, labels = count_cc(list(self.mono.scene.adj_list.keys()), self.mono.scene.adj_list)
        if nb_cc > 1:
            self.tab.setCurrentIndex(0)
            QMessageBox.critical(None, 'Error',
                                 'You have disconnected nodes.',
                                 QMessageBox.Ok)
            return
        self.load(self.filename)

    def multi_to_mono(self):
        self.save()

    def welcome(self):
        self.hide()
        while True:
            dlg = ProjectDialog()
            value = dlg.exec_()
            if value == QDialog.Accepted:
                if dlg.new:
                    self.mono.scene.reinit()
                    self.multi.scene.reinit()
                    self.create_new(dlg.filename)
                    self.showMaximized()
                    break
                elif self.load(dlg.filename):
                    self.tab.setCurrentIndex(0)
                    self.showMaximized()
                    break
                else:
                    QMessageBox.critical(None, 'Error',
                                         'The project file is not valid.',
                                         QMessageBox.Ok)
            else:
                sys.exit(0)

    def closeEvent(self, event):
        if not self.save():
            value = QMessageBox.question(None, 'Confirm exit', 'Are your sure to exit?\n'
                                         '(The project cannot be saved because it has duplicated suffix)',
                                         QMessageBox.Ok | QMessageBox.Cancel)
            if value == QMessageBox.Cancel:
                event.ignore()
                return
        self.welcome()
        event.ignore()


def exception_hook(exctype, value, traceback):
    """!
    @brief Needed for suppressing traceback silencing in newer version of PyQt5
    """
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)


if __name__ == '__main__':
    # suppress explicitly traceback silencing
    sys._excepthook = sys.excepthook
    sys.excepthook = exception_hook

    app = QApplication(sys.argv)

    widget = MyMainWindow()
    widget.welcome()
    app.exec_()





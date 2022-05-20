"""
The PyQt5 code used to build the analysis page for the program.
"""

__author__ = "Jacob Bumgarner <jrbumgarner@mix.wvu.edu>"
__license__ = "GPLv3 - GNU General Pulic License v3 (see LICENSE)"
__copyright__ = "Copyright 2022 by Jacob Bumgarner"
__webpage__ = "https://jacobbumgarner.github.io/VesselVio/"
__download__ = "https://jacobbumgarner.github.io/VesselVio/Downloads"


import json
import os
import sys

from library import helpers, qt_threading as QtTh

from library.annotation_processing import RGB_check

from library.gui import qt_objects as QtO
from library.gui.analysis_options_widget import AnalysisOptions
from library.gui.annotation_page import RGB_Warning
from library.gui.graph_options_widget import GraphOptions

from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QHeaderView,
    QLabel,
    QLayout,
    QMainWindow,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QWidget,
)


class mainWindow(QMainWindow):
    """A main window for development and testing of the analysis page only."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Annotation Testing")
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)
        layout = QtO.new_layout(None, "H", True, "None")
        self.centralWidget.setLayout(layout)

        annotationpage = AnalysisPage()

        layout.addWidget(annotationpage)

        self.show()


class AnalysisPage(QWidget):
    """The page used for batch processing and analysis of segmented vasculature
    datasets."""

    def __init__(self):
        super().__init__()
        self.analyzed = False
        ## This page is organized into to vertical sections.

        pageLayout = QtO.new_layout(self, "V", spacing=5, margins=20)

        ## Top section - file loading and processing
        self.Loading = LoadingWidget()
        self.Loading.loadButton.clicked.connect(self.load_files)

        ### Botom section - analysis and graph loading options
        # three column horizontal
        self.bottomWidget = QtO.new_widget()
        self.bottomWidget.setFixedHeight(250)
        bottomLayout = QtO.new_layout(self.bottomWidget, no_spacing=True)

        # Left column is a spacer
        spacer = QtO.new_widget(150)

        # Middle column is a tab widget
        self.analysisOptions = AnalysisOptions()
        self.graphOptions = GraphOptions(self.Loading.fileSheet)
        self.optionsTab = QTabWidget()
        self.optionsTab.addTab(self.analysisOptions, "Analysis Options")
        self.optionsTab.addTab(self.graphOptions, "Graph File Options")
        # Connect the loading filetype to the second options tab
        self.optionsTab.setTabEnabled(1, False)
        self.Loading.datasetType.currentIndexChanged.connect(self.update_table_view)

        # Bottom right column
        rightColumn = QtO.new_layout(orient="V", spacing=13)
        self.analyzeButton = QtO.new_button("Analyze", self.run_analysis)
        self.cancelButton = QtO.new_button("Cancel", self.cancel_analysis)
        self.cancelButton.setDisabled(True)
        QtO.add_widgets(rightColumn, [0, self.analyzeButton, self.cancelButton, 0])

        QtO.add_widgets(bottomLayout, [spacer, 0, self.optionsTab, rightColumn, 0])

        ## Add it all together
        QtO.add_widgets(pageLayout, [self.Loading, self.bottomWidget])

    ## File loading
    def load_files(self):
        """File loading. Manages loading segmented files, annotation files,
        and graph files for batch analysis."""
        dataset_type = self.Loading.datasetType.currentText()
        annotation = self.Loading.annotationType.currentText()
        graph_format = self.graphOptions.graphFormat.currentText()

        c1files, c2files = None, None
        if annotation == "None" and dataset_type == "Volume":
            c1files = helpers.load_volumes()
        elif dataset_type == "Graph" and graph_format != "CSV":
            c1files = helpers.load_graphs(graph_format)
        else:
            self.loader = FileLoader(dataset_type, annotation, graph_format)
            if self.loader.exec_():
                if self.loader.column1_files:
                    c1files = self.loader.column1_files
                if self.loader.column2_files:
                    c2files = self.loader.column2_files
            del self.loader

        if self.analyzed:
            self.Loading.clear_files()
            self.analyzed = False
        if c1files:
            self.Loading.column1_files += c1files
            self.Loading.add_column1_files()
        if c2files:
            self.Loading.column2_files += c2files
            self.Loading.add_column2_files()

        return

    # Analysis Processing
    def run_analysis(self):
        """Prepares and initiates the analysis of the loaded files, if there
        are any.

        Workflow:
        1. Check to ensure that the appropriate files have been loaded for the
        analysis.

        2. Connects the appropriate QThread to the appropriate buttons and
        selection signals.

        3. Starts the QThread
        """
        # If an analysis has already been run, make sure new files are loaded.
        if self.analyzed:
            self.analysis_warning()
            return

        # Make sure the appropriate files are loaded
        if not self.file_check():
            self.analysis_warning()
            return

        # Check for the loaded files and initialize the appropriate QThread
        if self.Loading.datasetType.currentText() == "Volume":
            self.initialize_volume_analysis()
        elif self.Loading.datasetType.currentText() == "Graph ":
            self.initialize_graph_analysis()

        self.a_thread.button_lock.connect(self.button_locking)
        self.a_thread.selection_signal.connect(self.Loading.update_row_selection)
        self.a_thread.analysis_status.connect(self.Loading.update_status)
        self.a_thread.start()
        self.analyzed = True
        return

    # Volume analysis
    def initialize_volume_analysis(self):
        """Creates an analysis thread for volume-based analysis. Loads and
        prepares the relevant volume analysis options."""
        analysis_options = self.analysisOptions.prepare_options(
            self.Loading.results_folder
        )
        analysis_options.annotation_type = self.Loading.annotationType.currentText()
        self.a_thread = QtTh.VolumeThread(
            analysis_options,
            self.Loading.column1_files,
            self.Loading.column2_files,
            self.Loading.annotation_data,
            self.disk_space_warning,
        )
        return

    def initialize_graph_analysis(self):
        """Creates an analysis thread for graph-based analysis. Loads and
        prepares the relevant graph analysis options."""
        analysis_options = self.analysisOptions.prepare_options(
            self.Loading.results_folder
        )
        graph_options = self.graphOptions.prepare_options()
        self.a_thread = QtTh.GraphThread(
            analysis_options,
            graph_options,
            self.Loading.column1_files,
            self.Loading.column2_files,
        )
        return

    def cancel_analysis(self):
        """Once called, triggers the analysis thread to stop the analysis at the
        next breakpoint."""
        # Disable the cancel button after the request is sent.
        self.cancelButton.setDisabled(True)
        self.a_thread.stop()
        return

    def button_locking(self, lock_state):
        """Toggles button disables for any relevant buttons or options during
        the analysis. Also serves to trigger any relevant log

        Parameters:
        lock_state : bool
            Enables/Disables the relevant buttons based on the lock state.
            Some buttons will be disabled, some will be enabled.
            The lock_state bool status is relevant for the 'setEnabled' or
            'setDisabled' call.
        """
        self.cancelButton.setEnabled(lock_state)
        self.Loading.loadingColumn.setDisabled(lock_state)
        self.Loading.changeFolder.setDisabled(lock_state)
        self.analyzeButton.setDisabled(lock_state)
        return

    def file_check(self):
        """Checks to ensure that the appropriate files have been loaded for
        the current analysis.

        Returns
        -------
        bool
            True if loaded correctly, False if incorrectly or incompletely
            loaded
        """
        if not self.Loading.column1_files:  # General file check
            return False

        if self.Loading.datasetType.currentText() == "Volume":  # Specific check
            if self.Loading.annotationType.currentText() != "None":
                if not self.column_file_check() or self.Loading.annotation_data:
                    return False
        if self.Loading.datasetType.currentText() == "Graph":
            if self.graphOptions.graphFormat.currentText() == "CSV":
                if not self.column_file_check():
                    return False
        return True

    def column_file_check(self):
        """Ensures that the column1_files and column2_files have the same number
        of loaded files.

        Returns
        -------
        bool
            True if the number of files match, False if they are different
        """
        file_check = len(self.Loading.column1_files) == len(self.Loading.column2_files)
        return file_check

    # Warnings
    def analysis_warning(self):
        """Creates a message box to indicate that the appropriate files have not
        been loaded."""
        msgBox = QMessageBox()
        message = "Load all files to run analysis."
        msgBox.setText(message)
        msgBox.exec_()

    def disk_space_warning(self, needed_space: float):
        """Creates a message box to indicate that at some point during the
        analysis, there was not enough disk space to conduct an annotation
        analysis."""
        msgBox = QMessageBox()
        msgBox.setWindowTitle("Disk Space Error")
        message = (
            "<center>During the analysis, one or more files were unable to be",
            "analyzed because of insufficient free disk memory.<br><br>",
            "<center>To analyze annotated volume datasets, VesselVio will need",
            f"at least <u>{needed_space:.1f} GB</u> of free space.",
        )
        msgBox.setText(message)
        msgBox.exec_()

    # Tab viewing
    def update_table_view(self):
        """Updates the view of the file loading table. If an annotation-based
        analysis or a CSV graph-based analysis are selected, an additional
        column is added for the relevant files."""
        active = False
        if self.Loading.datasetType.currentText() == "Graph":
            active = True
            if self.graphOptions.graphFormat.currentText() != "CSV":
                self.Loading.fileSheet.init_default()
            else:
                self.Loading.fileSheet.init_csv()
        elif self.Loading.annotationType.currentText() != "None":
            self.Loading.fileSheet.init_annotation()
        self.optionsTab.setTabEnabled(1, active)
        return


class LoadingWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.results_folder = helpers.load_results_dir()
        self.column1_files = []
        self.column2_files = []
        self.annotation_data = None

        self.setMinimumHeight(400)
        topLayout = QtO.new_layout(self, no_spacing=True)

        ## Loading column
        self.loadingColumn = QtO.new_widget(150)
        loadingLayout = QtO.new_layout(self.loadingColumn, orient="V")

        self.loadButton = QtO.new_button("Load Files", None)
        clearFile = QtO.new_button("Remove File", self.remove_file)
        clearAll = QtO.new_button("Clear Files", self.clear_files)

        # Line
        line = QtO.new_line("H", 100)

        # Volume Options
        typeHeader = QLabel("<b>Dataset Type:")
        self.datasetType = QtO.new_combo(
            ["Volume", "Graph"], connect=self.file_type_options
        )

        # Annotation options
        annHeader = QLabel("<b>Annotation Type:")
        self.annotationType = QtO.new_combo(
            ["None", "ID", "RGB"], connect=self.annotation_options
        )
        self.annotationType.currentIndexChanged.connect(self.update_JSON)

        # Load annotation
        self.loadAnnotationFile = QtO.new_widget()
        aFileLayout = QtO.new_layout(self.loadAnnotationFile, "V", margins=(0, 0, 0, 0))

        loadJSON = QtO.new_button("Load JSON", self.load_annotation_file)
        loadJSON.setToolTip(
            "Load annotation file created using the Annotation Processing tab."
        )
        loaded = QLabel("<center>Loaded JSON:")
        self.loadedJSON = QtO.new_line_edit("None", "Center", locked=True)
        self.JSONdefault = self.loadedJSON.styleSheet()
        self.loadAnnotationFile.setVisible(False)
        QtO.add_widgets(aFileLayout, [loadJSON, loaded, self.loadedJSON], "Center")

        QtO.add_widgets(
            loadingLayout,
            [
                40,
                self.loadButton,
                clearFile,
                clearAll,
                line,
                typeHeader,
                self.datasetType,
                annHeader,
                self.annotationType,
                self.loadAnnotationFile,
                0,
            ],
            "Center",
        )

        ## Top right - file list information
        # region
        topRight = QtO.new_widget()
        topRightLayout = QtO.new_layout(topRight, "V", no_spacing=True)
        self.fileSheet = FileSheet()
        self.fileSheet.setMinimumWidth(400)

        # Result export location
        folderLine = QtO.new_widget()
        folderLayout = QtO.new_layout(folderLine, margins=(0, 0, 0, 0))
        folderHeader = QLabel("Result Folder:")
        self.resultPath = QtO.new_line_edit(self.results_folder, locked=True)
        self.changeFolder = QtO.new_button("Change...", self.set_results_folder)
        QtO.add_widgets(
            folderLayout, [folderHeader, self.resultPath, self.changeFolder]
        )

        QtO.add_widgets(topRightLayout, [self.fileSheet, folderLine])
        # endregion

        QtO.add_widgets(topLayout, [self.loadingColumn, topRight])

    ## File management
    def add_column1_files(self):
        files = self.column1_files
        for i, file in enumerate(files):
            if i + 1 > self.fileSheet.rowCount():
                self.fileSheet.insertRow(self.fileSheet.rowCount())
            filename = os.path.basename(file)
            self.fileSheet.setItem(i, 0, QTableWidgetItem(filename))

        self.update_queue()
        return

    def add_column2_files(self):
        files = self.column2_files
        for i, file in enumerate(files):
            if i + 1 > self.fileSheet.rowCount():
                self.fileSheet.insertRow(self.fileSheet.rowCount())
            filename = os.path.basename(file)
            self.fileSheet.setItem(i, 1, QTableWidgetItem(filename))

        self.update_queue()
        return

    def remove_file(self):
        columns = self.fileSheet.columnCount()
        if self.fileSheet.selectionModel().hasSelection():
            index = self.fileSheet.currentRow()
            self.fileSheet.removeRow(index)
            if index < len(self.column1_files):
                del self.column1_files[index]
            if columns == 3:
                if index < len(self.column2_files):
                    del self.column2_files[index]
        return

    def clear_files(self):
        self.fileSheet.setRowCount(0)
        self.column1_files = []
        self.column2_files = []
        return

    ## Status management
    # Status is sent as a len(2) list with [0] as index
    # and [1] as status
    def update_status(self, status):
        column = self.fileSheet.columnCount() - 1
        self.fileSheet.setItem(status[0], column, QTableWidgetItem(status[1]))
        self.fileSheet.selectRow(status[0])

        if column == 3 and len(status) == 3:
            self.fileSheet.setItem(status[0], column - 1, QTableWidgetItem(status[2]))
        return

    def update_row_selection(self, row):
        self.fileSheet.selectRow(row)
        return

    def update_queue(self):
        last_column = self.fileSheet.columnCount() - 1
        for i in range(self.fileSheet.rowCount()):
            self.fileSheet.setItem(i, last_column, QTableWidgetItem("Queued..."))

        if self.fileSheet.columnCount() == 4:
            if self.annotation_data:
                count = len(self.annotation_data.keys())
                status = f"0/{count}"
            else:
                status = "Load JSON!"
            last_column -= 1
            for i in range(self.fileSheet.rowCount()):
                self.fileSheet.setItem(i, last_column, QTableWidgetItem(status))

        return

    ## JSON file loading
    def file_type_options(self):
        visible = False
        if self.datasetType.currentText() == "Graph":
            visible = True
        else:
            self.fileSheet.init_default()

        if self.annotationType.currentIndex():
            self.loadAnnotationFile.setVisible(not visible)

        self.annotationType.setDisabled(visible)
        self.clear_files()
        return

    def annotation_options(self):
        visible = False
        if self.annotationType.currentIndex():
            visible = True
            self.fileSheet.init_annotation()
        else:
            self.fileSheet.init_default()
            self.column2_files = []
        self.loadAnnotationFile.setVisible(visible)
        self.add_column1_files()
        return

    def load_annotation_file(self):
        loaded_file = helpers.load_JSON(helpers.get_dir("Desktop"))

        if loaded_file:
            with open(loaded_file) as f:
                annotation_data = json.load(f)
                if (
                    len(annotation_data) != 1
                    or "VesselVio Annotations" not in annotation_data.keys()
                ):
                    self.JSON_error("Incorrect filetype!")
                else:
                    # If loading an RGB filetype, make sure there's no duplicate colors.
                    if self.annotationType.currentText() == "RGB" and RGB_check(
                        annotation_data["VesselVio Annotations"]
                    ):
                        if RGB_Warning().exec_() == QMessageBox.No:
                            return

                    self.loadedJSON.setStyleSheet(self.JSONdefault)
                    filename = os.path.basename(loaded_file)
                    self.loadedJSON.setText(filename)
                    self.annotation_data = annotation_data["VesselVio Annotations"]
                    self.update_queue()
        return

    def JSON_error(self, warning):
        self.loadedJSON.setStyleSheet("border: 1px solid red;")
        self.loadedJSON.setText(warning)
        return

    def update_JSON(self):
        if self.annotationType.currentText() == "None":
            self.annotation_data = None
            self.loadedJSON.setText("None")
        return

    ## Results folder processing
    def set_results_folder(self):
        folder = helpers.set_results_dir()
        if folder:
            self.results_folder = folder
            self.resultPath.setText(folder)
        return


class FileSheet(QTableWidget):
    def __init__(self):
        super().__init__()
        self.setShowGrid(False)

        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)

        self.verticalHeader().hide()
        self.horizontalHeader().setMinimumSectionSize(100)

        self.setMinimumWidth(400)

        self.init_default()

        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setDefaultSectionSize(20)

    def init_default(self):
        header = ["File Name", "File Status"]
        self.set_format(2, [300, 200], header)
        return

    def init_annotation(self):
        header = [
            "File Name",
            "Annotation File Name",
            "Regions Processed",
            "File Status",
        ]
        self.set_format(4, [200, 200, 150, 200], header)
        return

    def init_csv(self):
        header = ["File Name - Vertices", "File Name - Edges", "File Status"]
        self.set_format(3, [200] * 3, header)
        return

    def set_format(self, column_count, widths, header):
        # Add columns, column info, and column size
        self.setColumnCount(0)
        self.setColumnCount(column_count)
        for i in range(column_count):
            self.setColumnWidth(i, widths[i])

        self.setHorizontalHeaderLabels(header)

        # Make sure status column is fixed size
        last = self.columnCount() - 1
        delegate = QtO.AlignCenterDelegate(self)
        self.setItemDelegateForColumn(last, delegate)

        self.horizontalHeader().setSectionResizeMode(last, QHeaderView.Fixed)
        if last == 3:
            last -= 1
            self.horizontalHeader().setSectionResizeMode(last, QHeaderView.Fixed)
            self.setItemDelegateForColumn(last, delegate)

        # Left align text for the file names
        delegate = QtO.AlignLeftDelegate(self)
        for i in range(last):
            self.setItemDelegateForColumn(i, delegate)
            self.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)

        return


## File loading
class FileLoader(QDialog):
    """The widget used to load datasets during batch analyses."""

    def __init__(self, dataset_type, annotation, graph_format):
        super().__init__()
        self.column1_files = []
        self.column2_files = []
        self.graph_format = graph_format
        self.annotation = annotation

        # Sizing

        windowLayout = QtO.new_layout(orient="V")
        self.setLayout(windowLayout)
        self.setWindowTitle("Dataset Loading")

        # Create volume loading buttons
        # Create load volume buttons
        loadingLayout = QtO.new_form_layout()
        if dataset_type == "Volume":
            volumeLabel = QLabel("Load binarized volumes:")
            loadButton = QtO.new_button("Load...", self.load_volumes)
            QtO.add_form_rows(loadingLayout, [[volumeLabel, loadButton]])
            if annotation == "RGB":
                annLabel = QLabel("Load RGB annotation parent folder:")
            else:
                annLabel = QLabel("Load volume annotations:")
            annButton = QtO.new_button("Load...", self.load_annotations)
            QtO.add_form_rows(loadingLayout, [[annLabel, annButton]])
            QtO.button_defaulting(loadButton, False)
            QtO.button_defaulting(annButton, False)

        else:
            vHeader = QLabel("Load CSV vertices files:")
            vButton = QtO.new_button("Load...", self.load_csv_vertices)
            eHeader = QLabel("Load CSV edges files:")
            eButton = QtO.new_button("Load", self.load_csv_edges)
            QtO.add_form_rows(loadingLayout, [[vHeader, vButton], [eHeader, eButton]])
            QtO.button_defaulting(vButton, False)
            QtO.button_defaulting(eButton, False)

        cancel = QtO.new_button("Cancel", self.cancel_load)
        QtO.button_defaulting(cancel, False)
        QtO.add_widgets(windowLayout, [loadingLayout, cancel], "Center")

        self.layout().setSizeConstraint(QLayout.SetFixedSize)

    def load_csv_vertices(self):
        """Load CSV files containing information about the graph vertices."""
        files = self.init_dialog("csv (*.csv)", "Load CSV vertex files")
        if files:
            self.column1_files += files
            self.accept()
        return

    def load_csv_edges(self):
        """Load CSV files containing information about the graph edges."""
        files = self.init_dialog("csv (*.csv)", "Load CSV edge files")
        if files:
            self.column2_files += files
            self.accept()
        return

    def load_volumes(self):
        """Load volume files for the analysis."""
        file_filter = "Images (*.nii *.png *.bmp *.tif *.tiff *.jpg *.jpeg)"
        files = self.init_dialog(file_filter, "Load volume files")
        if files:
            self.column1_files += files
            self.accept()
        return

    # Format either is a folder or .nii files
    def load_annotations(self):
        """Load annotation files for the analysis."""
        files = None
        if self.annotation == "ID":
            file_filter = "Images (*.nii)"
            files = self.load_ID_annotations(
                file_filter, "Load .nii annotation volumes"
            )
        else:
            folder = self.load_RGB_annotation_parent_folder()
            if folder:
                files = [
                    os.path.join(folder, path)
                    for path in os.listdir(folder)
                    if os.path.isdir(os.path.join(folder, path))
                ]

        if files:
            self.column2_files += files
            self.accept()
        return

    def cancel_file_loading(self):
        """Close the opened file loading widget."""
        self.reject()

    def load_ID_annotations(self, file_filter, message):
        """Return the file paths of ID annotation .nii files."""
        files = QFileDialog.getOpenFileNames(
            self, message, helpers.get_dir("Desktop"), file_filter
        )
        return files[0]

    def load_RGB_annotation_parent_folder(self):
        """Return the parent folder of RGB annotation sub-folders."""
        results_dir = QFileDialog.getExistingDirectory(
            self,
            "Select parent folder of RGB annotation folders",
            helpers.get_dir("Desktop"),
        )
        return results_dir


###############
### Testing ###
###############
if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = mainWindow()
    sys.exit(app.exec_())

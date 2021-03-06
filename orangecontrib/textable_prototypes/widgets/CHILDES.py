"""
Class Childes
Copyright 2019 University of Lausanne
-----------------------------------------------------------------------------
This file is part of the Orange3-Textable-Prototypes package.

Orange3-Textable-Prototypes is free software: you can redistribute it
and/or modify it under the terms of the GNU General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Orange3-Textable-Prototypes is distributed in the hope that it will be
useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Orange-Textable-Prototypes. If not, see
<http://www.gnu.org/licenses/>.
"""

__version__ = u"0.0.1"
__author__ = "Aris Xanthos"
__maintainer__ = "Aris Xanthos"
__email__ = "aris.xanthos@unil.ch"


import os
import io
import pickle
import inspect
import zipfile

import requests
from bs4 import BeautifulSoup

from Orange.widgets import widget, gui, settings

from LTTL.Segmentation import Segmentation
from LTTL.Input import Input
import LTTL.Segmenter as Segmenter

from _textable.widgets.TextableUtils import (
    OWTextableBaseWidget, VersionedSettingsHandler, pluralize,
    InfoBox, SendButton, ProgressBar
)


class Childes(OWTextableBaseWidget):
    """Textable widget for importing data in XML format from the CHILDES
    database (https://childes.talkbank.org/data-xml/).
    """

    #----------------------------------------------------------------------
    # Widget's metadata...

    name = "CHILDES"
    description = "Import XML data from the CHILDES database"
    icon = "icons/CHILDES.svg"
    priority = 12

    #----------------------------------------------------------------------
    # Channel definitions (NB: no input in this case)...

    inputs = []
    outputs = [("XML data", Segmentation)]

    #----------------------------------------------------------------------
    # Settings...

    settingsHandler = VersionedSettingsHandler(
        version=__version__.rsplit(".", 1)[0]
    )

    importedCorpus = settings.Setting(None)
    autoSend = settings.Setting(False)

    #----------------------------------------------------------------------
    # Other class variables...
    
    base_url = "https://childes.talkbank.org/data-xml/"
    cache_filename = "cache_childes"

    want_main_area = False

    def __init__(self):
        """Widget creator."""

        super().__init__()

        # Other (non-setting) attributes...
        self.segmentation = None
        self.displayedFolderLabels = list()
        self.currentFolder = self.__class__.base_url
        self.database = None
        self.selectedItems = list()

        # Next two instructions are helpers from TextableUtils. Corresponding
        # interface elements are declared here and actually drawn below (at
        # their position in the UI)...
        self.infoBox = InfoBox(widget=self.controlArea)
        self.sendButton = SendButton(
            widget=self.controlArea,
            master=self,
            callback=self.sendData,
            infoBoxAttribute="infoBox",
        )

        # User interface...

        # Browse database box
        browseBox = gui.widgetBox(
            widget=self.controlArea,
            box="Browse database",
            orientation="vertical",
            addSpace=False,
        )

        upwardNavBox = gui.widgetBox(
            widget=browseBox,
            box=False,
            orientation="horizontal",
        )
        self.homeRefreshButton = gui.button(
            widget=upwardNavBox,
            master=self,
            label="Home",
            callback=self.homeRefreshPressed,
            tooltip="Return to database root.",
            # tooltip="Connect to CHILDES website and refresh corpus list.",
        )
        self.backButton = gui.button(
            widget=upwardNavBox,
            master=self,
            label="Back",
            callback=self.backPressed,
            tooltip="View parent folder.",
        )

        gui.separator(widget=browseBox, height=3)

        self.currentFolderLabel = gui.label(
            widget=browseBox,
            master=self,
            label="Current folder: /",
            tooltip="This is the currently displayed folder.",
        )

        gui.separator(widget=browseBox, height=3)

        displayedFolderListbox = gui.listBox(
            widget=browseBox,
            master=self,
            value="selectedItems", 
            labels="displayedFolderLabels",
            callback=self.corpusSelected,
            tooltip="Select an item to open or import.",
        )
        displayedFolderListbox.setMinimumHeight(150)
        displayedFolderListbox.setSelectionMode(1)
        displayedFolderListbox.doubleClicked.connect(self.listBoxDoubleClicked)

        self.importedCorpusLabel = gui.label(
            widget=browseBox,
            master=self,
            label="No corpus imported yet.",
            tooltip="This is the currently imported corpus.",
        )

        gui.separator(widget=browseBox, height=3)

        downwardNavBox = gui.widgetBox(
            widget=browseBox,
            box=False,
            orientation="horizontal",
        )
        self.openButton = gui.button(
            widget=downwardNavBox,
            master=self,
            label="Open",
            callback=self.openPressed,
            tooltip="View selected folder's contents.",
        )
        self.importButton = gui.button(
            widget=downwardNavBox,
            master=self,
            label="Import",
            callback=self.importPressed,
            tooltip="Import selected item's contents.",
        )

        gui.separator(widget=browseBox, height=3)

        gui.rubber(self.controlArea)

        # Now Info box and Send button must be drawn...
        self.sendButton.draw()
        self.infoBox.draw()

        # This initialization step needs to be done after infoBox has been
        # drawn (because we may need to display an error message).
        self.loadDatabaseCache()

        # Send data if autoSend.
        self.sendButton.sendIf()

        self.setMinimumWidth(350)
        self.adjustSizeWithTimer()

    def sendData(self):
        """Compute result of widget processing and send to output"""
        if not self.importedCorpus:
            self.infoBox.setText(
                "Please select a corpus to import.",
                "warning"
            )
            self.send("XML data", None, self)
            return
        progressBar = ProgressBar(self, iterations=1)
        response = requests.get(self.importedCorpus)
        myZip = zipfile.ZipFile(io.BytesIO(response.content))
        for file in myZip.infolist():
            print(file.filename, len(myZip.read(file)))
        progressBar.advance()
        progressBar.finish()

        corpus = self.displayedFolderLabels[self.selectedItems[0]]
        self.importedCorpusLabel.setText("Corpus %s correctly imported." % corpus)
        self.infoBox.setText("All good!")
        self.sendButton.resetSettingsChangedFlag()

    def homeRefreshPressed(self):
        """Refresh database file tree"""
        self.currentFolder = self.__class__.base_url
        self.updateDisplayedFolders()

    def backPressed(self):
        """Display parent folder's contents"""
        self.currentFolder = "/".join(self.currentFolder[:-1].split("/")[:-1])
        self.currentFolder += "/"
        self.updateDisplayedFolders()        

    def corpusSelected(self):
        """Import selected corpus"""
        self.updateBrowseBoxButtons()

    def openPressed(self):
        """Display selected folder's contents"""
        self.currentFolder += self.displayedFolderLabels[self.selectedItems[0]]
        self.updateDisplayedFolders()

    def importPressed(self):
        """Import selected corpus"""
        # TODO: handle exceptions
        corpus = self.displayedFolderLabels[self.selectedItems[0]]
        self.importedCorpus = self.currentFolder + corpus
        self.importButton.setDisabled(True)
        self.importedCorpusLabel.setText("Corpus %s ready to import." % corpus)
        self.sendButton.settingsChanged()

    def listBoxDoubleClicked(self):
        """Reroute to 'openPressed' or 'importPressed' as needed"""
        if self.displayedFolderLabels[self.selectedItems[0]].endswith(".zip"):
            self.importPressed()
        else:
            self.openPressed()

    def loadDatabaseCache(self):
        """Load the cached database"""
        # Try to open saved file in this module"s directory...
        path = os.path.dirname(
            os.path.abspath(inspect.getfile(inspect.currentframe()))
        )
        try:
            file = open(os.path.join(path, self.__class__.cache_filename),"rb")
            self.database = pickle.load(file)
            file.close()
        # Else try to rebuild cache from CHILDES website...
        except IOError:
            self.database = self.rebuildCacheFromWebsite()

        self.currentFolder = self.__class__.base_url
        self.updateDisplayedFolders()

    def updateDisplayedFolders(self):
        """Refresh state of displayed folder listbox"""
        # Current folder label...
        currentFolder = self.currentFolder[len(self.__class__.base_url)-1:]
        self.currentFolderLabel.setText("Current folder: " + currentFolder)
        
        # Populate listbox...
        folderContent = self.database[self.__class__.base_url]
        steps = currentFolder[:-1].split("/")[1:]
        for idx, _ in enumerate(steps):
            path = self.__class__.base_url + "/".join(steps[:idx+1]) + "/"
            folderContent = folderContent[path]
        displayedFolderLabels = list()
        for item in folderContent.keys():
            if item.endswith(".zip"):
                displayedFolderLabels.append(item)
            else:
                displayedFolderLabels.append(item.split("/")[-2] + "/")
        self.displayedFolderLabels = displayedFolderLabels
        
        # Imported corpus label...
        if self.importedCorpus:
            self.importedCorpusLabel.setText(
                "Corpus %s ready to import." 
                % self.importedCorpus.split("/")[-1]
            )

        # Buttons.
        self.updateBrowseBoxButtons()
            
    def updateBrowseBoxButtons(self):
        """Refresh state of Browse box buttons"""
        currentFolder = self.currentFolder[len(self.__class__.base_url)-1:]
        self.homeRefreshButton.setDisabled(currentFolder == "/")
        self.backButton.setDisabled(currentFolder == "/")
        self.openButton.setDisabled(
            len(self.selectedItems) == 0 or 
            self.displayedFolderLabels[self.selectedItems[0]].endswith(".zip")
        )
        self.importButton.setDisabled(
            len(self.selectedItems) == 0 or 
            self.displayedFolderLabels[self.selectedItems[0]].endswith("/")
        )

    # The following method need to be copied (without any change) in
    # every Textable widget...

    def setCaption(self, title):
        if 'captionTitle' in dir(self):
            changed = title != self.captionTitle
            super().setCaption(title)
            if changed:
                self.sendButton.settingsChanged()
        else:
            super().setCaption(title)


if __name__ == "__main__":
    import sys
    from PyQt4.QtGui import QApplication
    myApplication = QApplication(sys.argv)
    myWidget = Childes()
    myWidget.show()
    myApplication.exec_()
    #myWidget.saveSettings()

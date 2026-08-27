# -*- coding: utf-8 -*-

"""Script to export all worksheets as CSV files, based on `export_as_csvs.py` from
https://gist.github.com/noirbizarre/ (minus unicode stuff), with a few tweaks
"""

import os.path

from com.sun.star.beans import PropertyValue

def csv_properties():
    """Build the dialog parameter for UTF-8 CSV
    """
    p1 = PropertyValue()
    p1.Name = 'FilterName'
    p1.Value = 'Text - txt - csv (StarCalc)'

    p2 = PropertyValue()
    p2.Name = 'FilterOptions'
    # `0` for token 12 means export current sheet only
    p2.Value = '44,34,76,1,,0,false,true,true,false,,0'

    return p1, p2

def export_sheets_to_csv():
    """Iterate over each sheet and save it as CSV file
    """
    doc = XSCRIPTCONTEXT.getDocument()
    cntrl = doc.getCurrentController()
    cursheet = cntrl.getActiveSheet()
    docroot = os.path.splitext(doc.URL)[0]
    props = csv_properties()

    for i, sheet in enumerate(doc.Sheets):
        cntrl.setActiveSheet(sheet)
        # just use sheet number in file name
        filename = f"{docroot}-{i+1}.csv"
        doc.storeToURL(filename, props)

    cntrl.setActiveSheet(cursheet)

g_exportedScripts = export_sheets_to_csv,

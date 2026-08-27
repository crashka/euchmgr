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
    # `-1` for token 12 means export all sheets
    p2.Value = '44,34,76,1,,0,false,true,true,false,,-1'

    return p1, p2

def export_sheets_to_csv():
    """Export each sheet as a CSV file (with sheet name appended)"""
    doc = XSCRIPTCONTEXT.getDocument()
    docroot = os.path.splitext(doc.URL)[0]
    filename = f"{docroot}.csv"
    doc.storeToURL(filename, csv_properties())

g_exportedScripts = export_sheets_to_csv,

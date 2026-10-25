"""Native history window: searchable list of past dictations, double-click to copy."""

import time

import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSMakeRect,
    NSPasteboard,
    NSPasteboardTypeString,
    NSScrollView,
    NSSearchField,
    NSTableColumn,
    NSTableView,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject

import history

_controller = None  # kept alive so the window and its data survive between opens


class _HistoryController(NSObject):
    def initWithEntries_(self, entries):
        self = objc.super(_HistoryController, self).init()
        if self is None:
            return None
        self.all_entries = entries
        self.entries = entries
        self.window = None
        self.tableView = None
        return self

    @objc.python_method
    def refresh(self, entries):
        self.all_entries = entries
        self.entries = entries
        self.tableView.reloadData()

    def numberOfRowsInTableView_(self, tableView):
        return len(self.entries)

    def tableView_objectValueForTableColumn_row_(self, tableView, column, row):
        entry = self.entries[row]
        if column.identifier() == "time":
            return time.strftime("%b %d, %I:%M %p", time.localtime(entry["ts"]))
        text = entry["cleaned"] or entry["raw"]
        return text.replace("\n", " ")

    def search_(self, sender):
        query = sender.stringValue().strip().lower()
        if query:
            self.entries = [
                e
                for e in self.all_entries
                if query in (e["cleaned"] or "").lower()
                or query in (e["raw"] or "").lower()
            ]
        else:
            self.entries = self.all_entries
        self.tableView.reloadData()

    def copySelected_(self, sender):
        row = self.tableView.clickedRow()
        if row < 0 or row >= len(self.entries):
            return
        text = self.entries[row]["cleaned"] or self.entries[row]["raw"]
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, NSPasteboardTypeString)
        self.window.setTitle_("Dictation History — Copied!")
        self.performSelector_withObject_afterDelay_("resetTitle:", None, 1.0)

    def resetTitle_(self, _sender):
        self.window.setTitle_("Dictation History")


def show_history_window():
    global _controller
    entries = history.fetch_entries()

    if _controller is not None and _controller.window is not None:
        _controller.refresh(entries)
        _controller.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        return

    frame = NSMakeRect(0, 0, 640, 480)
    style = (
        NSWindowStyleMaskTitled
        | NSWindowStyleMaskClosable
        | NSWindowStyleMaskResizable
        | NSWindowStyleMaskMiniaturizable
    )
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame, style, NSBackingStoreBuffered, False
    )
    window.setTitle_("Dictation History")
    window.setMinSize_((420, 300))
    content = window.contentView()

    search_field = NSSearchField.alloc().initWithFrame_(NSMakeRect(12, 448, 616, 24))
    search_field.setAutoresizingMask_(NSViewWidthSizable)
    content.addSubview_(search_field)

    scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(12, 12, 616, 428))
    scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
    scroll.setHasVerticalScroller_(True)

    table = NSTableView.alloc().initWithFrame_(scroll.bounds())
    table.setUsesAlternatingRowBackgroundColors_(True)
    table.setRowHeight_(20)

    col_time = NSTableColumn.alloc().initWithIdentifier_("time")
    col_time.setTitle_("When")
    col_time.setWidth_(150)
    table.addTableColumn_(col_time)

    col_text = NSTableColumn.alloc().initWithIdentifier_("text")
    col_text.setTitle_("Transcript (double-click to copy)")
    col_text.setWidth_(440)
    table.addTableColumn_(col_text)

    scroll.setDocumentView_(table)
    content.addSubview_(scroll)

    controller = _HistoryController.alloc().initWithEntries_(entries)
    controller.window = window
    controller.tableView = table

    table.setDataSource_(controller)
    table.setTarget_(controller)
    table.setDoubleAction_("copySelected:")

    search_field.setTarget_(controller)
    search_field.setAction_("search:")

    window.setReleasedWhenClosed_(False)
    window.center()
    window.makeKeyAndOrderFront_(None)
    NSApp.activateIgnoringOtherApps_(True)

    _controller = controller

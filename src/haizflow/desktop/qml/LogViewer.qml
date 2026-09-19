import QtQuick
import QtQuick.Controls.Basic
import "."

Rectangle {
    id: root

    property string text: ""
    property string emptyText: qsTr("Chưa có log.")
    property string query: ""
    property string levelFilter: "all"
    property bool compact: false
    readonly property string renderedText: formatLogText(text)
    readonly property int lineCount: text.length > 0 ? String(text).split(/\r?\n/).length : 0
    readonly property int filteredLineCount: countFilteredLines(text)

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
    }

    function displayTime(timestamp) {
        const raw = String(timestamp || "")
        // Activity files are deliberately stored in UTC so they remain
        // unambiguous when copied between machines.  Display them in the
        // machine's current time zone instead of slicing the UTC clock text.
        const parsed = new Date(raw)
        if (!isNaN(parsed.getTime()))
            return Qt.formatTime(parsed, "HH:mm:ss")
        const match = raw.match(/T(\d\d:\d\d:\d\d)/)
        return match ? match[1] : raw.slice(0, 8)
    }

    function levelColor(level) {
        if (level === "ERROR")
            return Theme.danger
        if (level === "WARN")
            return Theme.warning
        if (level === "DEBUG")
            return Theme.textSubtle
        return Theme.success
    }

    function formatLogText(rawText) {
        if (!rawText)
            return ""
        const expression = /^\[([^\]]+)\]\s*(?:\[([A-Z]+)\]\s*)?(?:\[([A-Z_]+)\]\s*)?(.*)$/
        const fontSize = compact ? 11 : 12
        const rendered = []
        for (const rawLine of String(rawText).split(/\r?\n/)) {
            const match = rawLine.match(expression)
            const level = match && match[2] ? match[2] : "INFO"
            if (levelFilter !== "all" && level !== levelFilter)
                continue
            if (query.trim().length > 0
                    && rawLine.toLocaleLowerCase().indexOf(query.trim().toLocaleLowerCase()) < 0)
                continue
            if (!match) {
                rendered.push("<span style=\"color:" + Theme.textMuted + ";\">" + escapeHtml(rawLine) + "</span>")
                continue
            }
            const timestamp = displayTime(match[1])
            const component = match[3] || "APP"
            const message = escapeHtml(match[4])
            rendered.push(
                "<span style=\"font-family:'Cascadia Mono';font-size:" + fontSize + "px;color:" + Theme.textSubtle + ";\">" + timestamp + "</span>" +
                " <span style=\"font-family:'Cascadia Mono';font-size:" + fontSize + "px;color:" + levelColor(level) + ";font-weight:600;\">[" + level + "]</span>" +
                " <span style=\"font-family:'Cascadia Mono';font-size:" + fontSize + "px;color:" + Theme.interactive + ";\">[" + component + "]</span>" +
                " <span style=\"font-family:'Cascadia Mono';font-size:" + fontSize + "px;color:" + Theme.codeText + ";\">" + message + "</span>"
            )
        }
        return rendered.join("<br>")
    }

    function countFilteredLines(rawText) {
        if (!rawText)
            return 0
        const expression = /^\[([^\]]+)\]\s*(?:\[([A-Z]+)\]\s*)?/
        let count = 0
        for (const rawLine of String(rawText).split(/\r?\n/)) {
            const match = rawLine.match(expression)
            const level = match && match[2] ? match[2] : "INFO"
            if (levelFilter !== "all" && level !== levelFilter)
                continue
            if (query.trim().length > 0
                    && rawLine.toLocaleLowerCase().indexOf(query.trim().toLocaleLowerCase()) < 0)
                continue
            count += 1
        }
        return count
    }

    function copyAll() {
        logText.selectAll()
        logText.copy()
        logText.select(0, 0)
    }

    radius: Theme.radiusSmall
    color: Theme.codeSurface
    border.color: Theme.outline
    border.width: 1

    Flickable {
        id: flick

        property bool followTail: true
        property bool programmaticScroll: false

        anchors.fill: parent
        anchors.margins: root.compact ? 10 : 14
        clip: true
        contentWidth: width
        contentHeight: Math.max(height, logText.paintedHeight)
        boundsBehavior: Flickable.StopAtBounds

        function scrollToBottom() {
            programmaticScroll = true
            contentY = Math.max(0, contentHeight - height)
            programmaticScroll = false
        }

        onMovementStarted: followTail = false
        onContentYChanged: {
            if (!programmaticScroll)
                followTail = contentY >= contentHeight - height - 8
        }
        onContentHeightChanged: {
            if (followTail)
                Qt.callLater(scrollToBottom)
        }

        TextEdit {
            id: logText

            width: flick.width
            readOnly: true
            selectByMouse: true
            text: root.renderedText.length > 0 ? root.renderedText : root.emptyText
            wrapMode: TextEdit.WrapAtWordBoundaryOrAnywhere
            color: root.renderedText.length > 0 ? Theme.codeText : Theme.textSubtle
            selectedTextColor: Theme.textOnAccent
            selectionColor: Theme.interactive
            font.family: "Cascadia Mono"
            font.pixelSize: root.compact ? 11 : 12
            textFormat: root.renderedText.length > 0 ? TextEdit.RichText : TextEdit.PlainText
        }

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }
    }
}

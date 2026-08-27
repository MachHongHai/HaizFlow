pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Item {
    id: root

    property var projectModel: null
    signal newProjectRequested(string projectType)
    signal recentProjectRequested(int index, string projectType)

    function typeLabel(type) {
        if (type === "manual") return I18n.t("Manual")
        if (type === "batch") return I18n.t("Batch")
        if (type === "download") return I18n.t("Downloads")
        if (type === "publish") return I18n.t("Social publishing")
        return I18n.t("Single")
    }

    function statusLabel(status) {
        if (status === "done") return I18n.t("Complete")
        if (status === "processing") return I18n.t("Processing")
        if (status === "failed") return I18n.t("Failed")
        if (status === "paused") return I18n.t("Paused")
        if (status === "awaiting_review") return I18n.t("Review needed")
        return I18n.t("Ready")
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: homeContent.implicitHeight + Theme.space32
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        ColumnLayout {
            id: homeContent
            width: parent.width
            spacing: Theme.space16

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Home")
                    color: Theme.text
                    font.pixelSize: Theme.h1
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Choose a workspace or continue a recent project.")
                    color: Theme.textMuted
                    font.pixelSize: Theme.body
                    textFormat: Text.PlainText
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: width < 920 ? 1 : 2
                columnSpacing: Theme.space12
                rowSpacing: Theme.space12

                WorkspaceCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 154
                    titleText: I18n.t("Automatic processing")
                    detailText: I18n.t("Translate, create voice and export one video automatically.")
                    actionText: I18n.t("New automatic project")
                    glyph: "\uE945"
                    toneColor: Theme.blue
                    toneSurface: Theme.blueSurface
                    onActivated: root.newProjectRequested("single")
                }

                WorkspaceCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 154
                    titleText: I18n.t("Manual")
                    detailText: I18n.t("Control translation, visuals, voice and audio independently.")
                    actionText: I18n.t("New manual project")
                    glyph: "\uE70F"
                    toneColor: Theme.violet
                    toneSurface: Theme.violetSurface
                    onActivated: root.newProjectRequested("manual")
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space12

                CompactWorkspaceCard {
                    Layout.fillWidth: true
                    titleText: I18n.t("Batch")
                    glyph: "\uE8FD"
                    onActivated: root.newProjectRequested("batch")
                }
                CompactWorkspaceCard {
                    Layout.fillWidth: true
                    titleText: I18n.t("Downloads")
                    glyph: "\uE896"
                    onActivated: root.newProjectRequested("download")
                }
                CompactWorkspaceCard {
                    Layout.fillWidth: true
                    titleText: I18n.t("Social publishing")
                    glyph: "\uE789"
                    onActivated: root.newProjectRequested("publish")
                }
            }

            Panel {
                Layout.fillWidth: true
                title: I18n.t("Recent projects")
                contentPadding: 0
                contentSpacing: 0

                ListView {
                    id: recentList
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(6, count) * 62
                    model: root.projectModel
                    interactive: false
                    clip: true

                    delegate: Rectangle {
                        id: recentRow
                        required property int index
                        required property string projectName
                        required property string projectType
                        required property string status
                        required property int progress
                        required property string thumbnailSource

                        width: recentList.width
                        height: index < 6 ? 62 : 0
                        visible: index < 6
                        color: recentHover.hovered ? Theme.surfaceMuted : "transparent"
                        Accessible.role: Accessible.Button
                        Accessible.name: projectName
                        activeFocusOnTab: visible

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: Theme.space12
                            anchors.rightMargin: Theme.space12
                            spacing: Theme.space12

                            Rectangle {
                                Layout.preferredWidth: 64
                                Layout.preferredHeight: 42
                                radius: Theme.radiusTiny
                                color: Theme.video
                                clip: true

                                Image {
                                    anchors.fill: parent
                                    source: recentRow.thumbnailSource
                                    sourceSize.width: 128
                                    sourceSize.height: 84
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1

                                Text {
                                    Layout.fillWidth: true
                                    text: recentRow.projectName
                                    color: Theme.text
                                    font.pixelSize: Theme.body
                                    font.weight: Font.DemiBold
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: root.typeLabel(recentRow.projectType)
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.label
                                    textFormat: Text.PlainText
                                }
                            }

                            Text {
                                text: root.statusLabel(recentRow.status)
                                color: recentRow.status === "failed" ? Theme.danger
                                    : recentRow.status === "done" ? Theme.success : Theme.textMuted
                                font.pixelSize: Theme.caption
                                textFormat: Text.PlainText
                            }

                            Text {
                                visible: recentRow.status === "processing"
                                text: qsTr("%1%").arg(recentRow.progress)
                                color: Theme.interactive
                                font.pixelSize: Theme.caption
                                textFormat: Text.PlainText
                            }

                            AppIcon {
                                Layout.preferredWidth: 18
                                Layout.preferredHeight: 18
                                glyph: "\uE72A"
                                iconColor: Theme.textMuted
                                iconSize: Theme.iconSmall
                            }
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: Theme.divider
                        }

                        HoverHandler { id: recentHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: root.recentProjectRequested(recentRow.index, recentRow.projectType)
                        }
                        Keys.onReturnPressed: root.recentProjectRequested(recentRow.index, recentRow.projectType)
                        Keys.onSpacePressed: root.recentProjectRequested(recentRow.index, recentRow.projectType)
                    }
                }

                Text {
                    Layout.fillWidth: true
                    Layout.margins: Theme.space20
                    visible: recentList.count === 0
                    text: I18n.t("No projects yet")
                    color: Theme.textMuted
                    font.pixelSize: Theme.body
                    horizontalAlignment: Text.AlignHCenter
                    textFormat: Text.PlainText
                }
            }
        }
    }

    component WorkspaceCard: Rectangle {
        id: card
        required property string titleText
        required property string detailText
        required property string actionText
        required property string glyph
        required property color toneColor
        required property color toneSurface
        signal activated()

        radius: Theme.radius
        color: cardHover.hovered ? Theme.surfaceMuted : toneSurface
        border.width: activeFocus ? 2 : 1
        border.color: activeFocus ? Theme.focus : cardHover.hovered ? toneColor : Theme.outline
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: titleText

        RowLayout {
            anchors.fill: parent
            anchors.margins: Theme.space20
            spacing: Theme.space20

            Rectangle {
                Layout.preferredWidth: 58
                Layout.preferredHeight: 58
                radius: Theme.radius
                color: card.toneColor

                AppIcon {
                    anchors.centerIn: parent
                    width: 28
                    height: 28
                    glyph: card.glyph
                    iconColor: Theme.textOnAccent
                    iconSize: 28
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    Layout.fillWidth: true
                    text: card.titleText
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
                Text {
                    Layout.fillWidth: true
                    text: card.detailText
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                }
                Text {
                    text: card.actionText + "  →"
                    color: card.toneColor
                    font.pixelSize: Theme.body
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }
        }

        HoverHandler { id: cardHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: card.activated() }
        Keys.onReturnPressed: card.activated()
        Keys.onSpacePressed: card.activated()
    }

    component CompactWorkspaceCard: Rectangle {
        id: compactCard
        required property string titleText
        required property string glyph
        signal activated()

        Layout.preferredHeight: 58
        radius: Theme.radiusSmall
        color: compactHover.hovered ? Theme.surfaceMuted : Theme.surface
        border.width: activeFocus ? 2 : 1
        border.color: activeFocus ? Theme.focus : Theme.outline
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: titleText

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.space16
            anchors.rightMargin: Theme.space16
            spacing: Theme.space12

            AppIcon {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                glyph: compactCard.glyph
                iconColor: Theme.interactive
                iconSize: Theme.icon
            }
            Text {
                Layout.fillWidth: true
                text: compactCard.titleText
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
            AppIcon {
                Layout.preferredWidth: 16
                Layout.preferredHeight: 16
                glyph: "\uE72A"
                iconColor: Theme.textMuted
                iconSize: Theme.iconSmall
            }
        }

        HoverHandler { id: compactHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: compactCard.activated() }
        Keys.onReturnPressed: compactCard.activated()
        Keys.onSpacePressed: compactCard.activated()
    }
}

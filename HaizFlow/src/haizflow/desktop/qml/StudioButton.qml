import "."

AppButton {
    property string variant: "secondary"
    property string iconName: ""

    compact: true
    tone: variant
    iconGlyph: IconCatalog.glyph(iconName)
}

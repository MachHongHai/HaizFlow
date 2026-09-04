pragma Singleton
import QtQuick

QtObject {
    function asset(name, accent) {
        const variant = accent ? "accent" : "muted"
        switch (name) {
        case "home": return Qt.resolvedUrl("icons/home-" + variant + ".svg")
        case "projects": return Qt.resolvedUrl("icons/projects-" + variant + ".svg")
        case "download": return Qt.resolvedUrl("icons/download-" + variant + ".svg")
        case "settings": return Qt.resolvedUrl("icons/settings-" + variant + ".svg")
        case "share": return Qt.resolvedUrl("icons/share-" + variant + ".svg")
        case "publish": return Qt.resolvedUrl("icons/share-" + variant + ".svg")
        case "play": return Qt.resolvedUrl("icons/play-" + variant + ".svg")
        case "edit": return Qt.resolvedUrl("icons/edit-" + variant + ".svg")
        default: return ""
        }
    }

    function glyph(name) {
        switch (name) {
        case "home": return "\uE80F"
        case "back": return "\uE72B"
        case "forward": return "\uE72A"
        case "projects": return "\uE8B7"
        case "folder": return "\uE8B7"
        case "download": return "\uE896"
        case "publish": return "\uE789"
        case "share": return "\uE789"
        case "send": return "\uE789"
        case "settings": return "\uE713"
        case "add": return "\uE710"
        case "search": return "\uE721"
        case "close": return "\uE711"
        case "more": return "\uE712"
        case "play": return "\uE768"
        case "pause": return "\uE769"
        case "stop": return "\uE71A"
        case "refresh": return "\uE72C"
        case "delete": return "\uE74D"
        case "open": return "\uE8A7"
        case "link": return "\uE71B"
        case "info": return "\uE946"
        case "warning": return "\uE7BA"
        case "error": return "\uEA39"
        case "success": return "\uE73E"
        case "filter": return "\uE71C"
        case "sort": return "\uE8CB"
        case "chevronDown": return "\uE70D"
        case "chevronUp": return "\uE70E"
        case "video": return "\uE714"
        case "audio": return "\uE8D6"
        case "volume": return "\uE767"
        case "muted": return "\uE74F"
        case "fullscreen": return "\uE740"
        case "edit": return "\uE70F"
        case "show": return "\uE890"
        case "hide": return "\uED1A"
        case "batch": return "\uE8FD"
        default: return ""
        }
    }
}

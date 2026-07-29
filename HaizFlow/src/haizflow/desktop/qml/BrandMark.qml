import QtQuick

Image {
    source: "../assets/branding/haizflow-mark.png"
    fillMode: Image.PreserveAspectFit
    sourceSize: Qt.size(Math.max(1, Math.round(width * 2)), Math.max(1, Math.round(height * 2)))
    smooth: true
    mipmap: true
    asynchronous: true
    Accessible.ignored: true
}

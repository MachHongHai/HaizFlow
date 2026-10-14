import QtQuick

Loader {
    id: root

    active: false
    asynchronous: false

    property string pendingMethod: ""
    property var pendingArguments: []

    function invoke(method, args) {
        pendingMethod = method || "open";
        pendingArguments = args || [];
        active = true;
        flushPendingCall();
    }

    function flushPendingCall() {
        if (status !== Loader.Ready || item === null || pendingMethod.length === 0)
            return;
        const method = pendingMethod;
        const args = pendingArguments;
        pendingMethod = "";
        pendingArguments = [];
        if (typeof item[method] === "function")
            item[method].apply(item, args);
    }

    function release() {
        pendingMethod = "";
        pendingArguments = [];
        active = false;
    }

    onLoaded: flushPendingCall()
    onStatusChanged: flushPendingCall()
}

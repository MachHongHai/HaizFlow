import QtQuick

Item {
    id: root
    property int desiredPositionMs: 0
    property int scrubPositionMs: 0
    property bool scrubbing: false
    property bool pending: false
    property bool wasPlaying: false
    property int generation: 0
    signal seekRequested(int positionMs)
    signal pauseRequested()
    signal resumeRequested()

    function begin(position, playing) {
        wasPlaying = playing;
        scrubbing = true;
        pauseRequested();
        updatePosition(position);
    }
    function updatePosition(position) {
        desiredPositionMs = Math.max(0, Math.round(position));
        scrubPositionMs = desiredPositionMs;
        pending = true;
        if (!seekTimer.running)
            seekTimer.start();
    }
    function end(position) {
        seekTimer.stop();
        desiredPositionMs = Math.max(0, Math.round(position));
        scrubPositionMs = desiredPositionMs;
        pending = true;
        scrubbing = false;
        seekRequested(desiredPositionMs);
    }
    function observe(position) {
        if (scrubbing)
            return;
        if (pending) {
            if (Math.abs(position - desiredPositionMs) > 80)
                return;
            pending = false;
            if (wasPlaying) {
                wasPlaying = false;
                resumeRequested();
            }
        }
        desiredPositionMs = position;
        scrubPositionMs = position;
    }
    function sourceChanged() { generation += 1; pending = true; }
    function sourceReady() { seekRequested(desiredPositionMs); }
    Timer { id: seekTimer; interval: 75; onTriggered: root.seekRequested(root.desiredPositionMs) }
}

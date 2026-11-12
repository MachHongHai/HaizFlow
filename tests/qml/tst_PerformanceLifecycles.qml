import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 900
    height: 600
    Component {
        id: overlayComponent
        EditorOverlayLayer { videoRect: Qt.rect(0, 0, 800, 450) }
    }
    Component {
        id: timelineComponent
        SubtitleTimeline { width: 850; height: 400; duration: 60 }
    }
    Component {
        id: dialogLoaderComponent
        LazyDialogLoader {
            sourceComponent: Component {
                Item {
                    property int calls: 0
                    property string value: ""
                    function showValue(next) { value = next; ++calls; }
                }
            }
        }
    }
    TestCase {
        name: "PerformanceLifecycles"
        when: windowShown
        function test_track_edit_preserves_outer_delegate() {
            const view = createTemporaryObject(timelineComponent, root);
            verify(!!view);
            view.editorTracks = [{track_id: "music", name: "Music", kind: "music", visible: true}];
            tryVerify(() => !!findChild(view, "timelineTrack-music"));
            const original = findChild(view, "timelineTrack-music");
            for (let i = 0; i < 20; ++i) {
                view.editorTracks = [{track_id: "music", name: "Music " + i, kind: "music", visible: true}];
                view.editorClips = [{clip_id: "audio", track_id: "music", kind: "audio", start_ms: i * 10, duration_ms: 1000}];
                compare(findChild(view, "timelineTrack-music"), original);
            }
            view.editorTracks = [];
            tryVerify(() => !findChild(view, "timelineTrack-music"));
        }
        function test_hidden_overlay_cannot_own_video_playback() {
            const view = createTemporaryObject(overlayComponent, root);
            verify(!!view);
            compare(view.liveMediaActive, true);
            view.visible = false;
            compare(view.liveMediaActive, false);
            view.visible = true;
            view.mediaActive = false;
            compare(view.liveMediaActive, false);
        }
        function test_animation_updates_retain_overlay_delegate() {
            const view = createTemporaryObject(overlayComponent, root);
            verify(!!view);
            function clip(x) {
                return {clip_id: "logo", kind: "image", asset: {},
                    transform: {position_x_percent: x, position_y_percent: 50}};
            }
            view.overlays = [clip(20)];
            tryVerify(() => !!findChild(view, "editorOverlay-logo"));
            const original = findChild(view, "editorOverlay-logo");
            const firstX = original.x;
            for (let x = 21; x <= 60; ++x)
                view.overlays = [clip(x)];
            compare(findChild(view, "editorOverlay-logo"), original);
            verify(original.x > firstX);
            view.overlays = [];
            tryVerify(() => !findChild(view, "editorOverlay-logo"));
        }
        function test_async_dialog_delivers_latest_request_once() {
            const loader = createTemporaryObject(dialogLoaderComponent, root);
            verify(!!loader);
            loader.invoke("showValue", ["first"]);
            loader.invoke("showValue", ["latest"]);
            tryCompare(loader, "status", Loader.Ready);
            compare(loader.item.value, "latest");
            compare(loader.item.calls, 1);
            loader.release();
            tryCompare(loader, "status", Loader.Null);
        }
        function test_closed_pending_dialog_never_replays() {
            const loader = createTemporaryObject(dialogLoaderComponent, root);
            loader.invoke("showValue", ["stale"]);
            loader.release();
            loader.invoke("showValue", ["new"]);
            tryCompare(loader, "status", Loader.Ready);
            compare(loader.item.value, "new");
            compare(loader.item.calls, 1);
        }
    }
}

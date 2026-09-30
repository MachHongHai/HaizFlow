pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml"

Item {
    id: root
    width: 600
    height: 500

    Component {
        id: settingsComponent
        MusicPlaybackSettings {
            width: 420
            height: 88
            onLoopEdited: function(value) { loopMusic = value; }
            onDuckingEdited: function(value) { ducking = value; }
        }
    }
    SignalSpy { id: musicRequiredSpy; signalName: "musicRequired" }
    SignalSpy { id: loopEditedSpy; signalName: "loopEdited" }
    SignalSpy { id: duckingEditedSpy; signalName: "duckingEdited" }

    TestCase {
        name: "MusicPlaybackSettingsTests"
        when: windowShown

        function test_noMusicShowsNoticeWithoutChangingSettings() {
            const settings = createTemporaryObject(settingsComponent, root);
            verify(!!settings, "Component exists");
            musicRequiredSpy.target = settings;
            musicRequiredSpy.clear();
            mouseClick(settings, settings.width - 24, 20);
            tryCompare(musicRequiredSpy, "count", 1);
            tryCompare(settings, "loopMusic", true);
            mouseClick(settings, settings.width - 24, 68);
            tryCompare(musicRequiredSpy, "count", 2);
            tryCompare(settings, "ducking", false);
        }

        function test_loopEditsAfterImport() {
            const settings = createTemporaryObject(settingsComponent, root, {hasMusic: true});
            verify(!!settings, "Component exists");
            loopEditedSpy.target = settings;
            loopEditedSpy.clear();
            mouseClick(settings, settings.width - 24, 20);
            tryCompare(loopEditedSpy, "count", 1);
            tryCompare(settings, "loopMusic", false);
        }

        function test_duckingEditsAfterImport() {
            const settings = createTemporaryObject(settingsComponent, root, {hasMusic: true});
            verify(!!settings, "Component exists");
            duckingEditedSpy.target = settings;
            duckingEditedSpy.clear();
            mouseClick(settings, settings.width - 24, 68);
            tryCompare(duckingEditedSpy, "count", 1);
            tryCompare(settings, "ducking", true);
        }
    }
}

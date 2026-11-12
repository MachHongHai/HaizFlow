import QtQuick
import QtTest
import "../../src/haizflow/desktop/qml/TimelineViewport.js" as TimelineViewport

TestCase {
    name: "TimelineViewportIndex"
    function test_snap_matches_original_order_and_ties() {
        const segments = [];
        for (let i = 0; i < 10000; ++i) segments.push({start: i / 10, end: i / 10 + .05});
        const clips = [{start_ms: 50, duration_ms: 100}, {start_ms: 20, duration_ms: 300}];
        const dynamic = [0, 1000, 1200, 3.5];
        const trailing = [3.55, 3.45];
        const ordered = dynamic.slice();
        for (const item of segments) ordered.push(item.start, item.end);
        for (const item of clips) ordered.push(item.start_ms / 1000, (item.start_ms + item.duration_ms) / 1000);
        for (const value of trailing) ordered.push(value);
        const indexed = TimelineViewport.buildSnapIndex(segments, clips);
        for (let step = 0; step < 300; ++step) {
            const value = step * 3.333 + .025;
            let expected = value, best = .16;
            for (const target of ordered) {
                const gap = Math.abs(value - target);
                if (gap <= best) { expected = target; best = gap; }
            }
            compare(TimelineViewport.snap(indexed, value, .16, dynamic, trailing), expected);
        }
    }
    function test_decisions_preserve_unsorted_overlap_and_gap_semantics() {
        const rows = [{sequence_start_ms: 3000, source_start_ms: 100, source_end_ms: 600},
            {sequence_start_ms: 0, source_start_ms: 0, source_end_ms: 2000},
            {sequence_start_ms: 1000, source_start_ms: 5000, source_end_ms: 6000}];
        const index = TimelineViewport.buildDecisionIndex(rows);
        for (let time = 0; time < 4000; time += 50) {
            compare(TimelineViewport.decisionAt(index, time), rows.findIndex(item => time >= item.sequence_start_ms
                && time < item.sequence_start_ms + item.source_end_ms - item.source_start_ms));
            compare(TimelineViewport.decisionAfter(index, time), rows.findIndex(item => item.sequence_start_ms > time));
        }
    }
    function test_overlap_and_unsorted_order() {
        const entries = [{start: 3, end: 6}, {start: 0, end: 9}, {start: 8, end: 10}];
        const indexed = TimelineViewport.buildIndex(entries, false);
        compare(TimelineViewport.subtitleAt(indexed, 4), 0);
        compare(TimelineViewport.subtitleAt(indexed, 6), 1);
        compare(TimelineViewport.subtitleAt(indexed, 10), 2);
        compare(TimelineViewport.subtitleAt(indexed, 11), -1);
        compare(TimelineViewport.intersect(indexed, 5, 8).length, 3);
    }
    function test_long_timeline_matches_reference() {
        const entries = [];
        for (let i = 0; i < 12000; ++i)
            entries.push({start: i * 2, end: i * 2 + 1});
        const indexed = TimelineViewport.buildIndex(entries, false);
        for (let i = 0; i < entries.length; i += 71) {
            compare(TimelineViewport.subtitleAt(indexed, i * 2 + 0.5), i);
            compare(TimelineViewport.subtitleAt(indexed, i * 2 + 1.5), -1);
            compare(TimelineViewport.intersect(indexed, i * 2, i * 2 + 1).length, 1);
        }
    }
    function test_clip_millisecond_units() {
        const indexed = TimelineViewport.buildIndex([{start_ms: 1000, duration_ms: 500}], true);
        compare(TimelineViewport.intersect(indexed, 1.2, 1.3).length, 1);
        compare(TimelineViewport.intersect(indexed, 1.6, 2).length, 0);
    }
}

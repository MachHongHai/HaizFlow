.pragma library

function buildIndex(entries, milliseconds) {
    const items = entries.map(function(entry, index) {
        const start = Number(milliseconds ? entry.start_ms || 0 : entry.start || 0) / (milliseconds ? 1000 : 1);
        const end = milliseconds ? start + Number(entry.duration_ms || 0) / 1000 : Number(entry.end || 0);
        return {entry: entry, index: index, start: start, end: end, maximumEnd: end};
    }).sort((a, b) => a.start - b.start || a.index - b.index);
    let maximumEnd = -Infinity;
    for (const item of items) {
        maximumEnd = Math.max(maximumEnd, item.end);
        item.maximumEnd = maximumEnd;
    }
    return {items: items, count: entries.length};
}

function matching(index, left, right) {
    const items = index ? index.items : [];
    let low = 0, high = items.length;
    while (low < high) {
        const middle = (low + high) >>> 1;
        if (items[middle].maximumEnd < left)
            low = middle + 1;
        else
            high = middle;
    }
    const result = [];
    for (let cursor = low; cursor < items.length && items[cursor].start <= right; ++cursor) {
        if (items[cursor].end >= left)
            result.push(items[cursor]);
    }
    return result.sort((a, b) => a.index - b.index);
}

function intersect(index, left, right) {
    return matching(index, left, right).map(item => item.entry);
}

function subtitleAt(index, seconds) {
    const time = Math.max(0, Number(seconds || 0));
    const candidates = matching(index, time, time);
    for (const candidate of candidates) {
        if (time < candidate.end || candidate.index === index.count - 1 && time <= candidate.end)
            return candidate.index;
    }
    return -1;
}

function tickInterval(pixelsPerSecond) {
    const steps = [0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
    for (let i = 0; i < steps.length; ++i) {
        if (steps[i] * pixelsPerSecond >= 56)
            return steps[i];
    }
    return Math.ceil(56 / Math.max(0.001, pixelsPerSecond) / 3600) * 3600;
}

function buildDecisionIndex(decisions) {
    const result = buildIndex(decisions.map(function(item) {
        return {start_ms: Number(item.sequence_start_ms || 0),
            duration_ms: Number(item.source_end_ms || 0) - Number(item.source_start_ms || 0)};
    }), true);
    let first = decisions.length;
    for (let i = result.items.length - 1; i >= 0; --i) {
        first = Math.min(first, result.items[i].index);
        result.items[i].firstAfter = first;
    }
    return result;
}

function decisionAt(index, milliseconds) {
    const seconds = milliseconds / 1000;
    const candidates = matching(index, seconds, seconds);
    for (const item of candidates) {
        if (seconds < item.end)
            return item.index;
    }
    return -1;
}

function decisionAfter(index, milliseconds) {
    const items = index.items;
    const seconds = milliseconds / 1000;
    let low = 0, high = items.length;
    while (low < high) {
        const middle = (low + high) >>> 1;
        if (items[middle].start <= seconds) low = middle + 1;
        else high = middle;
    }
    return low < items.length ? items[low].firstAfter : -1;
}

function buildSnapIndex(segments, clips) {
    const values = [];
    for (const segment of segments) {
        values.push({time: Number(segment.start || 0), order: values.length});
        values.push({time: Number(segment.end || 0), order: values.length});
    }
    for (const clip of clips) {
        const start = Number(clip.start_ms || 0) / 1000;
        values.push({time: start, order: values.length});
        values.push({time: start + Number(clip.duration_ms || 0) / 1000, order: values.length});
    }
    values.sort((a, b) => a.time - b.time || a.order - b.order);
    const unique = [];
    for (const item of values) {
        if (unique.length && unique[unique.length - 1].time === item.time)
            unique[unique.length - 1] = item;
        else unique.push(item);
    }
    return unique;
}

function snap(index, value, distance, dynamic, trailing) {
    let result = value, best = distance, priority = -1;
    function consider(time, order) {
        const gap = Math.abs(value - time);
        if (gap < best || gap === best && order >= priority) {
            result = time; best = gap; priority = order;
        }
    }
    for (let i = 0; i < dynamic.length; ++i) consider(dynamic[i], i);
    let low = 0, high = index.length;
    while (low < high) {
        const middle = (low + high) >>> 1;
        if (index[middle].time < value) low = middle + 1;
        else high = middle;
    }
    if (low > 0) consider(index[low - 1].time, dynamic.length + index[low - 1].order);
    if (low < index.length) consider(index[low].time, dynamic.length + index[low].order);
    for (let i = 0; i < trailing.length; ++i)
        consider(trailing[i], Infinity);
    return result;
}

function sync(model, entries) {
    const wanted = {};
    for (let i = 0; i < entries.length; ++i)
        wanted[entries[i].entryKey] = true;
    let row = model.count - 1;
    while (row >= 0) {
        if (wanted[model.get(row).entryKey]) {
            --row;
            continue;
        }
        const last = row;
        while (row >= 0 && !wanted[model.get(row).entryKey])
            --row;
        model.remove(row + 1, last - row);
    }
    for (let i = 0; i < entries.length; ++i) {
        const entry = entries[i];
        if (i >= model.count || model.get(i).entryKey !== entry.entryKey) {
            let found = i + 1;
            while (found < model.count && model.get(found).entryKey !== entry.entryKey)
                ++found;
            if (found < model.count)
                model.move(found, i, 1);
            else
                model.insert(i, entry);
        }
        if (model.get(i).entryIndex !== entry.entryIndex)
            model.setProperty(i, "entryIndex", entry.entryIndex);
    }
}

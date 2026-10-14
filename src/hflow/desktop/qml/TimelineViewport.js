.pragma library

function tickInterval(pixelsPerSecond) {
    const steps = [0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
    for (let i = 0; i < steps.length; ++i) {
        if (steps[i] * pixelsPerSecond >= 56)
            return steps[i];
    }
    return Math.ceil(56 / Math.max(0.001, pixelsPerSecond) / 3600) * 3600;
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

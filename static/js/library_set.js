function step(id, delta) {
    const el = document.getElementById(id);
    const v = Math.max(0, (parseInt(el.value, 10) || 0) + delta);
    el.value = v;
}

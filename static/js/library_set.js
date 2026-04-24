const csrfToken = document.querySelector('[name=csrf_token]').value;
let saveTimer = null;

function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
        const body = new URLSearchParams({
            csrf_token: csrfToken,
            straight: document.getElementById('straight').value,
            curve:    document.getElementById('curve').value,
            switch:   document.getElementById('switch').value,
            crossing: document.getElementById('crossing').value,
        });
        fetch('/library_set', {
            method: 'POST',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
            body,
        });
    }, 400);
}

function step(id, delta) {
    const el = document.getElementById(id);
    const v = Math.max(0, (parseInt(el.value, 10) || 0) + delta);
    el.value = v;
    save();
}

document.querySelectorAll('.stepper input').forEach(inp => {
    inp.addEventListener('change', save);
});

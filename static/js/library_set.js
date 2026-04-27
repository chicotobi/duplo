const csrfToken = document.querySelector('[name=csrf_token]').value;
let saveTimer = null;
let roomSaveTimer = null;

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

function saveRoom() {
    clearTimeout(roomSaveTimer);
    roomSaveTimer = setTimeout(() => {
        const body = new URLSearchParams({
            csrf_token: csrfToken,
            room_w: document.getElementById('room_w').value,
            room_h: document.getElementById('room_h').value,
        });
        fetch('/room_set', {
            method: 'POST',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
            body,
        });
    }, 400);
}

function step(id, delta) {
    const el = document.getElementById(id);
    const min = parseInt(el.min, 10);
    const max = parseInt(el.max, 10);
    let v = (parseInt(el.value, 10) || 0) + delta;
    if (!isNaN(min)) v = Math.max(min, v);
    if (!isNaN(max)) v = Math.min(max, v);
    el.value = v;
    if (id === 'room_w' || id === 'room_h') saveRoom();
    else save();
}

document.querySelectorAll('.lib-grid .stepper input').forEach(inp => {
    inp.addEventListener('change', save);
});
document.querySelectorAll('.room-form .stepper input').forEach(inp => {
    inp.addEventListener('change', saveRoom);
});

// Scenery layer: loads the pre-generated meadow tile and exposes it
// for tiling by the main editor.  The tile is drawn at 1/4 room size
// so it repeats several times across the visible area.
(function () {
    'use strict';

    const MM_PER_UNIT = window.TE.MM_PER_UNIT;
    const TILE_W = (window.EDITOR_ROOM_W || 6) * 1000 / MM_PER_UNIT / 2;
    const TILE_H = (window.EDITOR_ROOM_H || 4) * 1000 / MM_PER_UNIT / 2;

    const tileImg = new Image();
    tileImg.src = window.EDITOR_TILE_URL || '/static/tiles/meadow.png';

    window.TE.sceneryTile = tileImg;
    window.TE.TILE_W = TILE_W;
    window.TE.TILE_H = TILE_H;
})();
